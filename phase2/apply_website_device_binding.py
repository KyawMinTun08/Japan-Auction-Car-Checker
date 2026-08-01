"""Deterministically integrate Phase 2 device binding into ``index.html``.

The production website is a large single-file static app. Keeping this
transformation explicit makes the security-sensitive edits reviewable and
repeatable without hand-editing unrelated chart/UI code.

This script is staged only. Run it in the Phase 2 release branch, review the
resulting index.html diff, and commit that generated diff before deployment.
"""

from __future__ import annotations

import argparse
from pathlib import Path


class WebsitePatchError(RuntimeError):
    """Raised when the expected current website contract has drifted."""


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if new in source and old not in source:
        return source
    count = source.count(old)
    if count != 1:
        raise WebsitePatchError(
            f"{label}: expected exactly one current-contract match, found {count}"
        )
    return source.replace(old, new, 1)


def apply_patch_text(source: str) -> str:
    marker = '<script src="phase2/website_device_binding.js" '
    if marker in source and "async function restoreSession()" in source:
        return source

    source = _replace_once(
        source,
        "</div>\n</div>\n\n<script>\nconst SHEET_ID",
        "</div>\n</div>\n\n"
        '<script src="phase2/website_device_binding.js" '
        'data-jacc-device-binding="v4"></script>\n'
        "<script>\nconst SHEET_ID",
        "device helper script tag",
    )

    source = _replace_once(
        source,
        "const SESSION_KEY = 'jan_session';\n"
        "const SESSION_VER = 'v3';\n"
        "const MAX_LOGIN_TRIES = 5;",
        "const SESSION_KEY = JACCDeviceBinding.SESSION_KEY;\n"
        "const SESSION_VER = JACCDeviceBinding.SESSION_VERSION;\n"
        "const MAX_LOGIN_TRIES = 5;",
        "session version",
    )

    source = _replace_once(
        source,
        "body:JSON.stringify({action:'verifyLogin',password:pw})",
        "body:JSON.stringify(JACCDeviceBinding.withDevice('verifyLogin',{password:pw}))",
        "verifyLogin device payload",
    )

    source = _replace_once(
        source,
        "      if(reason==='wrong_password'||reason.includes('password')){",
        "      if(JACCDeviceBinding.isDeviceError(result)){\n"
        "        err.textContent=JACCDeviceBinding.deviceErrorMessage(result);\n"
        "      }\n"
        "      else if(reason==='wrong_password'||reason.includes('password')){",
        "login device error",
    )

    source = _replace_once(
        source,
        "    SESSION={ver:SESSION_VER,token:result.token,userId:result.userId,username:result.username,package:result.package,expireDate:result.expireDate,loginTime:Date.now()};\n"
        "    localStorage.setItem(SESSION_KEY,JSON.stringify(SESSION));",
        "    SESSION=JACCDeviceBinding.saveSession({token:result.token,userId:result.userId,username:result.username,package:result.package,expireDate:result.expireDate,loginTime:Date.now()});",
        "save bound session",
    )

    old_session = """function checkSession(){
  try{
    const s=localStorage.getItem(SESSION_KEY);if(!s)return false;
    const parsed=JSON.parse(s);if(!parsed||!parsed.token)return false;
    if(parsed.ver!==SESSION_VER){localStorage.removeItem(SESSION_KEY);return false;}
    SESSION=parsed;return true;
  }catch(e){return false;}
}
"""
    new_session = """async function restoreSession(){
  window.JACC_SESSION_ERROR='';
  const restored=await JACCDeviceBinding.verifyStoredSession({webhook:WEBHOOK});
  if(restored.ok){SESSION=restored.session;return true;}
  if(restored.deviceError){
    window.JACC_SESSION_ERROR=JACCDeviceBinding.deviceErrorMessage(restored.response||{message:restored.reason});
  }else if(restored.reason==='backend_unavailable'){
    window.JACC_SESSION_ERROR='⚠️ Login server ကို ဆက်သွယ်မရပါ။ Internet စစ်ပြီး ပြန်ဖွင့်ပါ။';
  }
  return false;
}
"""
    source = _replace_once(
        source,
        old_session,
        new_session,
        "server-verified session restore",
    )

    source = _replace_once(
        source,
        "body:JSON.stringify({action:'getData',token:SESSION.token})",
        "body:JSON.stringify(JACCDeviceBinding.withDevice('getData',{token:SESSION.token,userId:SESSION.userId}))",
        "getData device payload",
    )

    source = _replace_once(
        source,
        "    if(result.status!=='ok')throw new Error(result.msg||'Data fetch failed');",
        "    if(result.status!=='ok'){\n"
        "      if(JACCDeviceBinding.isDeviceError(result)){\n"
        "        JACCDeviceBinding.clearSession();\n"
        "        throw new Error(JACCDeviceBinding.deviceErrorMessage(result));\n"
        "      }\n"
        "      throw new Error(result.msg||result.message||'Data fetch failed');\n"
        "    }",
        "getData device rejection",
    )

    old_startup = """window.addEventListener('DOMContentLoaded',function(){
  if(checkSession()){showApp();}
  else{document.getElementById('loginOverlay').style.display='flex';document.getElementById('loadingOverlay').style.display='none';}
});
"""
    new_startup = """window.addEventListener('DOMContentLoaded',async function(){
  const login=document.getElementById('loginOverlay');
  const loading=document.getElementById('loadingOverlay');
  loading.style.display='flex';
  if(await restoreSession()){showApp();return;}
  login.style.display='flex';loading.style.display='none';
  if(window.JACC_SESSION_ERROR){
    const err=document.getElementById('loginErr');
    err.textContent=window.JACC_SESSION_ERROR;err.style.display='block';
  }
});
"""
    source = _replace_once(
        source,
        old_startup,
        new_startup,
        "async startup revalidation",
    )

    return source


def patch_file(path: Path, *, check: bool = False) -> bool:
    source = path.read_text(encoding="utf-8")
    patched = apply_patch_text(source)
    changed = patched != source
    if check:
        if not changed and "data-jacc-device-binding=\"v4\"" not in source:
            raise WebsitePatchError("website patch produced no Phase 2 marker")
        return changed
    if changed:
        path.write_text(patched, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="index.html")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed = patch_file(Path(args.path), check=args.check)
    print("website device-binding patch: " + ("changes required" if changed else "already applied"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
