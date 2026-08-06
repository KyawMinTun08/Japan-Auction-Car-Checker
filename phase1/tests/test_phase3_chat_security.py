from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "phase3" / "sql" / "010_chat_architecture.sql"
SECURITY = ROOT / "phase3" / "sql" / "011_chat_security.sql"
DOC = ROOT / "phase3" / "chat_security.md"


def security_sql() -> str:
    return SECURITY.read_text(encoding="utf-8").lower()


def test_task5_files_are_stacked_on_task4_schema() -> None:
    assert ARCHITECTURE.is_file()
    assert SECURITY.is_file()
    sql = security_sql()
    for table in (
        "jacc_conversations",
        "jacc_conversation_participants",
        "jacc_messages",
        "jacc_message_attachments",
        "jacc_message_read_receipts",
        "jacc_conversation_events",
        "jacc_conversation_reports",
    ):
        assert f"public.{table}" in sql


def test_customer_entitlement_requires_active_premium_app_membership() -> None:
    sql = security_sql()
    block = sql.split(
        "create or replace function public.jacc_chat_customer_entitled", 1
    )[1].split("create or replace function", 1)[0]
    assert "p.account_active" in block
    assert "p.role = 'customer'" in block
    assert "m.plan = 'premium'" in block
    assert "m.service_channel = 'app'" in block
    assert "upper(coalesce(m.status, '')) = 'active'" in block
    assert "m.starts_at <= now()" in block
    assert "m.expires_at is null or m.expires_at >= now()" in block


def test_broker_entitlement_requires_active_or_probation_status() -> None:
    sql = security_sql()
    block = sql.split(
        "create or replace function public.jacc_chat_broker_entitled", 1
    )[1].split("create or replace function", 1)[0]
    assert "p.account_active" in block
    assert "p.role in ('broker', 'lead_broker')" in block
    assert "b.account_status in ('probation', 'active')" in block
    assert "accepting_requests" not in block


def test_security_helpers_are_definer_functions_with_fixed_search_path() -> None:
    sql = security_sql()
    helpers = (
        "jacc_chat_profile_is_admin",
        "jacc_chat_customer_entitled",
        "jacc_chat_broker_entitled",
        "jacc_chat_profile_entitled",
        "jacc_chat_can_access_conversation",
        "jacc_chat_can_send_to_conversation",
        "jacc_chat_sender_role_allowed",
        "jacc_chat_message_in_conversation",
        "jacc_chat_message_owned_by_current",
        "jacc_chat_participant_owned_by_current",
        "jacc_chat_report_target_valid",
    )
    for helper in helpers:
        block = sql.split(f"create or replace function public.{helper}", 1)[1]
        block = block.split("$$;", 1)[0]
        assert "security definer" in block, helper
        assert "set search_path = public" in block, helper
        assert f"revoke all on function public.{helper}" in sql, helper
        assert f"grant execute on function public.{helper}" in sql, helper


def test_anon_has_no_chat_table_or_sequence_privileges() -> None:
    sql = security_sql()
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
        assert f"revoke all on table public.{table} from anon, authenticated" in sql
    assert "to anon" not in sql
    assert "grant usage, select on sequence public.jacc_message_read_receipts_id_seq to authenticated" in sql


def test_authenticated_grants_are_least_privilege() -> None:
    sql = security_sql()
    assert "grant select on table public.jacc_conversations to authenticated" in sql
    assert "grant select on table public.jacc_conversation_participants to authenticated" in sql
    assert "grant select, insert on table public.jacc_messages to authenticated" in sql
    assert "grant update (delivered_at, read_at) on table public.jacc_message_read_receipts to authenticated" in sql
    assert "grant select on table public.jacc_conversation_events to authenticated" in sql
    assert "grant all" not in sql
    assert "grant update on table public.jacc_messages" not in sql
    assert "grant delete on table public.jacc_messages" not in sql
    assert "grant insert on table public.jacc_conversations" not in sql


def test_all_chat_tables_have_explicit_authenticated_policies() -> None:
    sql = security_sql()
    expected = {
        "jacc_chat_conversations_select",
        "jacc_chat_participants_select",
        "jacc_chat_messages_select",
        "jacc_chat_messages_insert_app",
        "jacc_chat_attachments_select",
        "jacc_chat_attachments_insert",
        "jacc_chat_receipts_select",
        "jacc_chat_receipts_insert",
        "jacc_chat_receipts_update",
        "jacc_chat_events_select",
        "jacc_chat_reports_select",
        "jacc_chat_reports_insert",
    }
    policies = {
        match.group(1)
        for match in re.finditer(r"create policy\s+([a-z0-9_]+)", sql)
    }
    assert expected <= policies
    assert sql.count("to authenticated") >= len(expected)


def test_app_message_policy_blocks_transport_and_identity_forgery() -> None:
    sql = security_sql()
    block = sql.split("create policy jacc_chat_messages_insert_app", 1)[1]
    block = block.split("create policy", 1)[0]
    assert "sender_id = public.jacc_current_profile_id()" in block
    assert "public.jacc_chat_sender_role_allowed(sender_role)" in block
    assert "transport = 'app'" in block
    assert "external_message_id is null" in block
    assert "client_message_id is not null" in block
    assert "status = 'sent'" in block
    assert "failure_code is null" in block
    assert "edited_at is null" in block
    assert "deleted_at is null" in block
    assert "attachment_url is null" in block
    assert "message_type in ('text', 'photo', 'voice', 'document')" in block


def test_no_client_message_update_or_delete_policy_exists() -> None:
    sql = security_sql()
    message_policy_blocks = re.findall(
        r"create policy\s+([a-z0-9_]+)\s+on public\.jacc_messages\s+for\s+([a-z]+)",
        sql,
    )
    assert set(message_policy_blocks) == {
        ("jacc_chat_messages_select", "select"),
        ("jacc_chat_messages_insert_app", "insert"),
    }


def test_cross_table_integrity_triggers_are_present() -> None:
    sql = security_sql()
    required_errors = (
        "chat_customer_participant_mismatch",
        "chat_broker_participant_mismatch",
        "chat_admin_participant_mismatch",
        "chat_reply_conversation_mismatch",
        "chat_app_external_id_forbidden",
        "chat_telegram_external_id_required",
        "chat_sender_role_mismatch",
        "chat_sender_not_participant",
        "chat_attachment_conversation_mismatch",
        "chat_receipt_conversation_mismatch",
        "chat_report_request_mismatch",
        "chat_report_message_mismatch",
        "chat_report_target_mismatch",
        "chat_event_log_is_append_only",
    )
    for marker in required_errors:
        assert marker in sql

    triggers = (
        "trg_jacc_chat_validate_participant",
        "trg_jacc_chat_validate_message_security",
        "trg_jacc_chat_validate_attachment",
        "trg_jacc_chat_validate_receipt",
        "trg_jacc_chat_validate_report",
        "trg_jacc_chat_events_append_only",
    )
    for trigger in triggers:
        assert f"create trigger {trigger}" in sql


def test_receipt_and_report_policies_are_scoped_to_current_user() -> None:
    sql = security_sql()
    receipt = sql.split("create policy jacc_chat_receipts_insert", 1)[1]
    receipt = receipt.split("create policy", 1)[0]
    assert "jacc_chat_participant_owned_by_current" in receipt
    assert "jacc_chat_message_in_conversation" in receipt

    report = sql.split("create policy jacc_chat_reports_insert", 1)[1]
    report = report.split("function execution boundary", 1)[0]
    assert "reporter_id = public.jacc_current_profile_id()" in report
    assert "status = 'open'" in report
    assert "reviewed_by is null" in report
    assert "reviewed_at is null" in report
    assert "jacc_chat_report_target_valid" in report


def test_attachment_policy_requires_private_path_and_message_ownership() -> None:
    sql = security_sql()
    block = sql.split("create policy jacc_chat_attachments_insert", 1)[1]
    block = block.split("create policy", 1)[0]
    assert "attachment_url !~* '^https?://'" in block
    assert "status = 'pending'" in block
    assert "jacc_chat_message_owned_by_current" in block
    assert "jacc_chat_can_send_to_conversation" in block


def test_storage_upload_is_deliberately_not_activated_yet() -> None:
    doc = DOC.read_text(encoding="utf-8").lower()
    sql = security_sql()
    assert "does **not** create a supabase storage bucket" in doc
    assert "photo upload must remain disabled" in doc
    assert "storage.objects" not in sql
    assert "telegram proxy chat remains unchanged" in doc
    assert "no supabase migration has been run" in doc


def test_no_literal_credentials_or_customer_rows_are_committed() -> None:
    combined = SECURITY.read_text(encoding="utf-8") + "\n" + DOC.read_text(
        encoding="utf-8"
    )
    forbidden = (
        r"\bsk-[a-z0-9_-]{20,}\b",
        r"\baiza[0-9a-z_-]{20,}\b",
        r"\b\d{8,12}:[a-z0-9_-]{30,}\b",
        r"(?:jacc_server_key|sheet_server_key|bot_token)\s*[:=]\s*[\"'][^\"']{8,}[\"']",
    )
    for pattern in forbidden:
        assert not re.search(pattern, combined, flags=re.IGNORECASE)
