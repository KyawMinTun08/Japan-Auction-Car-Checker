from __future__ import annotations

from pathlib import Path

import pytest

from phase3.app_chat.apply_app_chat_ui import (
    MARKER,
    TAB_LIST_NEW,
    parse_api_base,
    transform,
    validate,
)


API_BASE = "https://jacc-chat.example.invalid"
API_ORIGIN = "https://jacc-chat.example.invalid"


def test_transform_integrates_chat_tab_into_current_phase2_app():
    source = Path("index.html").read_text(encoding="utf-8")
    result = transform(source, API_BASE, API_ORIGIN)

    validate(result, API_BASE, API_ORIGIN)
    assert result.count(MARKER) == 2
    assert result.count('id="nav-chat"') == 1
    assert result.count('id="tab-chat"') == 1
    assert result.count(TAB_LIST_NEW) == 2
    assert "JACCChatUISetVisible(name==='chat')" in result
    assert "https://ipapi.co https://jacc-chat.example.invalid;" in result
    assert "SUPABASE_SERVICE_ROLE_KEY" not in result


def test_transform_is_idempotent_after_first_application():
    source = Path("index.html").read_text(encoding="utf-8")
    once = transform(source, API_BASE, API_ORIGIN)
    twice = transform(once, API_BASE, API_ORIGIN)
    assert twice == once


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://chat.example.com",
        "javascript:alert(1)",
        "https://user:pass@chat.example.com",
        "https://chat.example.com?token=secret",
        "https://chat.example.com/#fragment",
    ],
)
def test_api_base_requires_clean_https_url(value):
    with pytest.raises(ValueError):
        parse_api_base(value)


def test_api_base_allows_https_path_and_returns_origin():
    base, origin = parse_api_base("https://chat.example.com/jacc/")
    assert base == "https://chat.example.com/jacc"
    assert origin == "https://chat.example.com"


def test_transform_fails_closed_on_source_drift():
    source = Path("index.html").read_text(encoding="utf-8")
    drifted = source.replace("📊 Trends</div>", "📊 Market</div>", 1)
    with pytest.raises(RuntimeError):
        transform(drifted, API_BASE, API_ORIGIN)


def test_chat_ui_files_do_not_embed_server_secrets_or_direct_supabase_access():
    client = Path("phase3/app_chat/client.js").read_text(encoding="utf-8")
    ui = Path("phase3/app_chat/ui.js").read_text(encoding="utf-8")
    css = Path("phase3/app_chat/ui.css").read_text(encoding="utf-8")
    combined = (client + ui + css).lower()

    assert "supabase_service_role_key" not in combined
    assert "service_role" not in combined
    assert "/rest/v1/" not in combined
    assert "textcontent" in ui.lower()
    assert "innerhtml" not in ui.lower()
    assert "maxlength=\"4000\"" in transform(
        Path("index.html").read_text(encoding="utf-8"),
        API_BASE,
        API_ORIGIN,
    )
