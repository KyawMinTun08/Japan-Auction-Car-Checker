from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql" / "006_reliability_and_recovery.sql"
RUNBOOK = ROOT / "backup_recovery_runbook.md"


def migration_text() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_outbox_is_database_backed() -> None:
    sql = migration_text()
    assert "create table if not exists public.jacc_message_outbox" in sql
    assert "for update skip locked" in sql
    assert "jacc_claim_outbox_messages" in sql


def test_retry_schedule_matches_locked_policy() -> None:
    sql = migration_text()
    assert "interval '5 minutes'" in sql
    assert "interval '15 minutes'" in sql
    assert "interval '1 hour'" in sql
    assert "dead_letter" in sql


def test_stuck_processing_items_can_be_recovered() -> None:
    sql = migration_text()
    assert "jacc_recover_stuck_outbox" in sql
    assert "recovered after worker interruption" in sql


def test_audit_log_is_append_only() -> None:
    sql = migration_text()
    assert "before update or delete on public.jacc_audit_logs" in sql
    assert "audit logs are immutable" in sql


def test_backup_and_restore_runs_are_recorded() -> None:
    sql = migration_text()
    assert "create table if not exists public.jacc_backup_runs" in sql
    assert "create table if not exists public.jacc_restore_tests" in sql


def test_runbook_requires_restore_testing() -> None:
    text = RUNBOOK.read_text(encoding="utf-8").lower()
    assert "monthly restore test" in text
    assert "production ready" in text
    assert "secrets confirmed absent from github" in text
