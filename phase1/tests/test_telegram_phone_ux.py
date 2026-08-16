from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOT = (ROOT / "legacy_bot.py").read_text(encoding="utf-8")


def test_phone_first_main_menu_exists():
    assert "def build_main_menu(is_admin: bool = False)" in BOT
    assert 'InlineKeyboardButton("🆕 Membership ဝယ်ရန်"' in BOT
    assert 'InlineKeyboardButton("🔄 သက်တမ်းတိုး"' in BOT
    assert 'InlineKeyboardButton("🔑 Password"' in BOT
    assert 'InlineKeyboardButton("📢 Channel Link"' in BOT
    assert 'InlineKeyboardButton("❔ Help"' in BOT


def test_help_is_available_as_command_and_deep_link():
    assert "async def help_cmd" in BOT
    assert 'CommandHandler("help",        help_cmd)' in BOT
    assert 'BotCommand("help",          "❔ အသုံးပြုနည်း")' in BOT
    assert '"help": help_cmd' in BOT


def test_common_deep_links_route_to_existing_handlers():
    for action, handler in {
        "renew": "renew_cmd",
        "mypassword": "mypassword_cmd",
        "channel": "channel_cmd",
        "carrequest": "carrequest_cmd",
        "mystatus": "mystatus_cmd",
    }.items():
        assert f'"{action}": {handler}' in BOT
    assert "def bot_action_url(action: str)" in BOT


def test_admin_menu_adds_only_admin_shortcuts():
    assert 'InlineKeyboardButton("👥 Members"' in BOT
    assert 'InlineKeyboardButton("💾 Backup"' in BOT
    assert "is_admin" in BOT
