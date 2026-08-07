from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREVIEW = ROOT / "phase3" / "chat-preview.html"


def html() -> str:
    return PREVIEW.read_text(encoding="utf-8")


def test_chat_preview_exists_and_is_review_only() -> None:
    text = html()
    assert 'data-jacc-chat-preview="v1"' in text
    assert "Review-only preview" in text
    assert "Production မဟုတ်ပါ" in text


def test_mobile_chat_structure_is_present() -> None:
    text = html()
    for marker in (
        'aria-label="Conversations"',
        'aria-label="Active conversation"',
        'id="messages"',
        'id="composer"',
        'id="messageInput"',
        'id="back"',
    ):
        assert marker in text
    assert "@media(max-width:720px)" in text


def test_entitlement_gate_is_explicit() -> None:
    text = html()
    assert "Premium App Member" in text
    assert "active Premium/App membership" in text
    assert "Signed-in profile" in text


def test_browser_payload_cannot_forge_server_transport_fields() -> None:
    text = html()
    assert "transport: 'app'" in text
    assert "external_message_id: null" in text
    assert "attachment_url: null" in text
    assert "client_message_id: crypto.randomUUID()" in text
    assert "CURRENT_PROFILE_ID_REQUIRED" in text
    assert "service-role" in text


def test_upload_controls_are_disabled_until_private_storage_task() -> None:
    text = html()
    assert 'disabled aria-label="Attachments disabled"' in text
    assert "Photo၊ Voice၊ Document upload မဖွင့်သေးပါ" in text
    assert "Private Storage security" in text


def test_preview_uses_safe_text_rendering() -> None:
    text = html()
    assert "node.textContent = String(value || '')" in text
    assert "escapeText(payload.body)" in text
    assert "maxlength=\"2000\"" in text


def test_existing_production_index_is_not_replaced() -> None:
    assert (ROOT / "index.html").is_file()
    assert PREVIEW.is_file()
    assert PREVIEW.name != "index.html"
