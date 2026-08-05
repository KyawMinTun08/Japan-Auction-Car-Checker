#!/usr/bin/env python3
"""Guarded JACC Phase 3 app-chat UI integrator.

This transformer stages the chat tab inside the generated Phase 2 Web/PWA app.
It never deploys anything and it requires an explicit HTTPS Railway API base.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit


MARKER = 'data-jacc-app-chat="v1"'

SIDE_NAV_ANCHOR = (
    '    <div class="nav-item" id="nav-trends" '
    'onclick="switchTab(\'trends\')"><span class="icon">📊</span>Trends</div>'
)
SIDE_NAV_INSERT = (
    SIDE_NAV_ANCHOR
    + '\n    <div class="nav-item" id="nav-chat" '
      'onclick="switchTab(\'chat\')"><span class="icon">💬</span>'
      'Broker Chat<span class="nav-badge" id="jacc-chat-nav-badge" hidden>0</span></div>'
)

TOP_TAB_ANCHOR = (
    '    <div class="tab" onclick="switchTab(\'trends\')">📊 Trends</div>'
)
TOP_TAB_INSERT = (
    TOP_TAB_ANCHOR
    + '\n    <div class="tab" onclick="switchTab(\'chat\')">💬 Chat</div>'
)

DEVICE_SCRIPT = (
    '<script src="phase2/website_device_binding.js" '
    'data-jacc-device-binding="v4"></script>'
)

CONTENT_CLOSE_ANCHOR = (
    '    </div>\n\n'
    '  </div>\n'
    '</div>\n\n'
    + DEVICE_SCRIPT
)

TAB_LIST_OLD = "['dashboard','explorer','price','chassis','trends']"
TAB_LIST_NEW = "['dashboard','explorer','price','chassis','trends','chat']"

SWITCH_VISIBILITY_ANCHOR = (
    "  const navEl=document.getElementById('nav-'+name);"
    "if(navEl)navEl.classList.add('active');"
)
SWITCH_VISIBILITY_INSERT = (
    SWITCH_VISIBILITY_ANCHOR
    + "\n  if(window.JACCChatUISetVisible)"
      "window.JACCChatUISetVisible(name==='chat');"
)

CHAT_TAB = r'''

    <!-- PHASE 3 APP CHAT — STAGED -->
    <div class="tab-content" id="tab-chat" data-jacc-app-chat="v1">
      <section class="jacc-chat-shell" id="jacc-chat-shell" aria-label="Broker and customer chat">
        <aside class="jacc-chat-sidebar" aria-label="Conversation list">
          <div class="jacc-chat-sidebar-head">
            <div class="jacc-chat-title">Broker–Customer Chat</div>
            <div class="jacc-chat-subtitle">Request ID နဲ့ ချိတ်ထားတဲ့ လုံခြုံသော conversation များ</div>
            <div class="jacc-chat-open-row">
              <input class="jacc-chat-open-input" id="jacc-chat-request-code" type="text"
                     placeholder="A260805-000001" maxlength="32" autocomplete="off"
                     autocapitalize="characters" spellcheck="false" aria-label="Request ID">
              <button class="jacc-chat-open-button" id="jacc-chat-open-button" type="button">Open</button>
            </div>
          </div>
          <div class="jacc-chat-thread-list" id="jacc-chat-thread-list"></div>
          <div style="padding:8px">
            <button class="jacc-chat-refresh-button" id="jacc-chat-refresh-button" type="button">↻ Refresh conversations</button>
          </div>
        </aside>

        <div class="jacc-chat-main">
          <header class="jacc-chat-main-head">
            <button class="jacc-chat-back-button" id="jacc-chat-back-button" type="button" aria-label="Back to conversations">←</button>
            <div class="jacc-chat-counterpart">
              <div class="jacc-chat-counterpart-name" id="jacc-chat-counterpart-name">Conversation ရွေးပါ</div>
              <div class="jacc-chat-counterpart-meta" id="jacc-chat-counterpart-meta">Request ID မရွေးရသေးပါ</div>
            </div>
            <span class="jacc-chat-status closed" id="jacc-chat-status">Idle</span>
            <button class="jacc-chat-close-button" id="jacc-chat-close-button" type="button" hidden>Close Chat</button>
          </header>

          <div class="jacc-chat-notice" id="jacc-chat-notice" hidden role="status" aria-live="polite"></div>
          <div class="jacc-chat-placeholder" id="jacc-chat-placeholder">
            ဘယ်ဘက်က conversation တစ်ခုရွေးပါ။ Conversation မရှိသေးရင် Request ID ထည့်ပြီး ဖွင့်ပါ။
          </div>
          <div class="jacc-chat-messages" id="jacc-chat-messages" hidden aria-live="polite"></div>

          <div class="jacc-chat-composer" id="jacc-chat-composer" hidden>
            <textarea class="jacc-chat-textarea" id="jacc-chat-textarea" maxlength="4000"
                      placeholder="Message ရေးပါ…" aria-label="Chat message"></textarea>
            <button class="jacc-chat-send-button" id="jacc-chat-send-button" type="button">Send</button>
          </div>
        </div>
      </section>
    </div>'''


def parse_api_base(raw: str) -> tuple[str, str]:
    value = str(raw or "").strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("--api-base must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("--api-base must not contain credentials, query or fragment")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return value, origin


def require_once(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    if count != 1:
        raise RuntimeError(f"{label} expected once, found {count}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    require_once(text, old, label)
    return text.replace(old, new, 1)


def transform(source: str, api_base: str, api_origin: str) -> str:
    if MARKER in source:
        validate(source, api_base, api_origin)
        return source

    text = source
    text = replace_once(
        text,
        "</head>",
        '  <link rel="stylesheet" href="phase3/app_chat/ui.css" '
        'data-jacc-app-chat="v1">\n</head>',
        "head close",
    )
    text = replace_once(text, SIDE_NAV_ANCHOR, SIDE_NAV_INSERT, "sidebar trends item")
    text = replace_once(text, TOP_TAB_ANCHOR, TOP_TAB_INSERT, "top trends tab")

    integrated_close = CHAT_TAB + "\n\n" + CONTENT_CLOSE_ANCHOR
    text = replace_once(
        text,
        CONTENT_CLOSE_ANCHOR,
        integrated_close,
        "main content close",
    )

    config_script = (
        DEVICE_SCRIPT
        + "\n<script data-jacc-app-chat-config=\"v1\">"
          "window.JACC_CHAT_API_BASE="
        + json.dumps(api_base, ensure_ascii=True)
        + ";</script>"
        + "\n<script src=\"phase3/app_chat/client.js\" "
          "data-jacc-app-chat-client=\"v1\"></script>"
        + "\n<script src=\"phase3/app_chat/ui.js\" "
          "data-jacc-app-chat-ui=\"v1\"></script>"
    )
    text = replace_once(text, DEVICE_SCRIPT, config_script, "device binding script")

    if text.count(TAB_LIST_OLD) != 2:
        raise RuntimeError(
            "expected two tab allowlists before integration, found "
            f"{text.count(TAB_LIST_OLD)}"
        )
    text = text.replace(TAB_LIST_OLD, TAB_LIST_NEW)
    text = replace_once(
        text,
        SWITCH_VISIBILITY_ANCHOR,
        SWITCH_VISIBILITY_INSERT,
        "switchTab navigation hook",
    )

    csp_needle = "https://ipapi.co;"
    csp_replacement = f"https://ipapi.co {api_origin};"
    text = replace_once(text, csp_needle, csp_replacement, "CSP connect-src")

    validate(text, api_base, api_origin)
    return text


def validate(text: str, api_base: str, api_origin: str) -> None:
    checks = {
        "chat marker": MARKER,
        "chat stylesheet": 'href="phase3/app_chat/ui.css"',
        "chat sidebar": 'id="nav-chat"',
        "chat top tab": 'switchTab(\'chat\')">💬 Chat',
        "chat panel": 'id="tab-chat"',
        "chat client": 'src="phase3/app_chat/client.js"',
        "chat UI": 'src="phase3/app_chat/ui.js"',
        "chat API base": json.dumps(api_base, ensure_ascii=True),
        "chat CSP origin": api_origin + ";",
        "chat tab allowlist": TAB_LIST_NEW,
        "chat visibility hook": "JACCChatUISetVisible(name==='chat')",
    }
    for label, needle in checks.items():
        if needle not in text:
            raise RuntimeError(f"missing {label}")

    if text.count(MARKER) != 2:
        raise RuntimeError(
            "expected one stylesheet marker and one panel marker; "
            f"found {text.count(MARKER)}"
        )
    if text.count('id="nav-chat"') != 1 or text.count('id="tab-chat"') != 1:
        raise RuntimeError("chat navigation or panel duplicated")
    if text.count(TAB_LIST_NEW) != 2:
        raise RuntimeError("chat tab allowlists are incomplete")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    try:
        api_base, api_origin = parse_api_base(args.api_base)
        source = args.input.read_text(encoding="utf-8")
        if args.check:
            validate(source, api_base, api_origin)
            print("app chat UI integration: valid")
            return 0
        result = transform(source, api_base, api_origin)
        output = args.output or args.input
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result, encoding="utf-8")
        print(f"app chat UI integration written: {output}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"app chat UI integration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
