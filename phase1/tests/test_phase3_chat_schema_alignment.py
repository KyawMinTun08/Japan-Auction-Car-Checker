from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = (ROOT / "phase3" / "sql" / "010_chat_architecture.sql").read_text(encoding="utf-8").lower()
SEC = (ROOT / "phase3" / "sql" / "011_chat_security.sql").read_text(encoding="utf-8").lower()


def test_conversation_primary_key_contract_is_consistent() -> None:
    assert "conversation_id uuid primary key" in ARCH
    assert "where c.id = p_conversation_id" not in SEC
    assert "where c.id = new.conversation_id" not in SEC
    assert "jacc_chat_can_access_conversation(c.id)" not in SEC
    assert "jacc_chat_can_access_conversation(id)" not in SEC
    assert "where c.conversation_id = p_conversation_id" in SEC
    assert "where c.conversation_id = new.conversation_id" in SEC
    assert "jacc_chat_can_access_conversation(c.conversation_id)" in SEC
    assert "jacc_chat_can_access_conversation(conversation_id)" in SEC


def test_security_migration_stays_review_only() -> None:
    assert "review/staging only" in SEC
    assert "do not run against production" in SEC
