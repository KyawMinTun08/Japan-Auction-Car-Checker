from pathlib import Path


ROOT = Path(__file__).parent
legacy = (ROOT / "legacy_bot.py").read_text(encoding="utf-8")
patch = (ROOT / "membership_approval_patch.py").read_text(encoding="utf-8")

# Payment approval must not interpolate the generated/Sheet password into the
# admin-facing confirmation. It should show only a delivery notice.
slip_block = legacy.split('elif data.startswith("slip_ok_"):', 1)[1].split(
    'elif data.startswith("slip_no_"):', 1
)[0]
assert "Password: `{password}`" not in slip_block
assert "password_notice" in slip_block
assert "Password ကို Customer DM သို့ ပို့ပြီးပြီ" in slip_block

# The two other admin approval confirmations must also avoid exposing the value.
quick_block = legacy.split('elif data.startswith("qa_"):', 1)[1].split(
    'elif data.startswith("req_budget_"):', 1
)[0]
assert "Password: `{password}`" not in quick_block
assert "Password ကို Customer DM သို့ ပို့ပြီးပြီ" in quick_block

approve_block = legacy.split("async def approve_member", 1)[1].split(
    "async def members_list", 1
)[0]
assert "Password: <code>{password}</code>" not in approve_block
assert "Password ကို Customer DM သို့ ပို့ပြီးပြီ" in approve_block

# Production patch must preserve the single canonical password invariant:
# read from Sheet for the customer DM, rather than sending an unverified value.
assert "sheet_password = str(current.get(\"password\") or \"\").strip()" in patch
assert "verified_password = sheet_password" in patch
assert "verified_password = \"\"" in patch
assert "_last_membership_save[clean_user_id]" in patch
assert '"password": clean_password' in patch

print("PASS: admin confirmations hide password; customer DM uses Sheet password verification")
