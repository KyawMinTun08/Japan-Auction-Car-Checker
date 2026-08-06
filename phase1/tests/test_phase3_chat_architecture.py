from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "phase3" / "sql" / "010_chat_architecture.sql"
DOC = ROOT / "phase3" / "chat_architecture.md"


def migration_text() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_required_chat_tables_are_present() -> None:
    sql = migration_text().lower()
    required = {
        "public.jacc_conversations",
        "public.jacc_conversation_participants",
        "public.jacc_messages",
        "public.jacc_message_attachments",
        "public.jacc_message_read_receipts",
        "public.jacc_conversation_events",
        "public.jacc_conversation_reports",
    }
    assert required <= {
        match.group(1)
        for match in re.finditer(
            r"create table if not exists\s+(public\.jacc_[a-z_]+)", sql
        )
    }


def test_required_chat_fields_are_declared() -> None:
    sql = migration_text().lower()
    required_fields = {
        "conversation_id",
        "request_id",
        "customer_id",
        "broker_id",
        "sender_role",
        "message_type",
        "message_text",
        "attachment_url",
        "created_at",
        "read_at",
        "status",
        "closed_by",
    }
    for field in required_fields:
        assert re.search(rf"\b{re.escape(field)}\b", sql), field


def test_schema_links_to_existing_phase1_identity_and_request_tables() -> None:
    sql = migration_text().lower()
    assert "references public.jacc_service_requests(id)" in sql
    assert "references public.jacc_profiles(id)" in sql
    assert "references public.jacc_broker_profiles(user_id)" in sql
    assert "chat_customer_request_mismatch" in sql
    assert "chat_broker_assignment_mismatch" in sql
    assert "chat_child_request_mismatch" in sql


def test_cross_table_conversation_ownership_is_enforced() -> None:
    sql = " ".join(migration_text().lower().split())
    assert "foreign key (message_id, conversation_id) references public.jacc_messages(id, conversation_id)" in sql
    assert "foreign key (participant_id, conversation_id) references public.jacc_conversation_participants(id, conversation_id)" in sql
    assert "foreign key (last_message_id, conversation_id) references public.jacc_messages(id, conversation_id)" in sql
    assert "foreign key (last_read_message_id, conversation_id) references public.jacc_messages(id, conversation_id)" in sql


def test_task4_is_deny_by_default_without_task5_policies() -> None:
    sql = migration_text().lower()
    tables = (
        "jacc_conversations",
        "jacc_conversation_participants",
        "jacc_messages",
        "jacc_message_attachments",
        "jacc_message_read_receipts",
        "jacc_conversation_events",
        "jacc_conversation_reports",
    )
    for table in tables:
        assert f"alter table public.{table} enable row level security" in sql
    assert "create policy" not in sql


def test_message_and_telegram_deduplication_contracts_exist() -> None:
    sql = migration_text().lower()
    assert "client_message_id" in sql
    assert "external_message_id" in sql
    assert "uq_jacc_message_client_id" in sql
    assert "uq_jacc_message_external_id" in sql
    assert "transport" in sql


def test_v1_attachment_contract_is_private_and_bounded() -> None:
    sql = migration_text().lower()
    assert "attachment_url !~* '^https?://'" in sql
    assert "image/jpeg" in sql
    assert "image/png" in sql
    assert "image/webp" in sql
    assert "size_bytes <= 5242880" in sql
    assert "jacc-chat-attachments" in sql


def test_architecture_docs_preserve_telegram_and_production_boundaries() -> None:
    doc = DOC.read_text(encoding="utf-8").lower()
    assert "telegram proxy chat" in doc
    assert "no supabase migration has been run" in doc
    assert "no production service" in doc
    assert "task 5" in doc


def test_no_literal_credentials_or_customer_rows_are_committed() -> None:
    combined = migration_text() + "\n" + DOC.read_text(encoding="utf-8")
    forbidden = (
        r"\bsk-[a-z0-9_-]{20,}\b",
        r"\baiza[0-9a-z_-]{20,}\b",
        r"\b\d{8,12}:[a-z0-9_-]{30,}\b",
        r"(?:jacc_server_key|sheet_server_key|bot_token)\s*[:=]\s*[\"'][^\"']{8,}[\"']",
    )
    for pattern in forbidden:
        assert not re.search(pattern, combined, flags=re.IGNORECASE)
