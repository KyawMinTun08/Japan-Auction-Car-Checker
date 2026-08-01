from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[1]
    / "sql"
    / "008_fix_dispatch_offer_ambiguity.sql"
).read_text(encoding="utf-8").lower()


def test_dispatch_hotfix_qualifies_request_id_references() -> None:
    assert "a.request_id = p_request_id" in SQL
    assert "o.request_id = p_request_id" in SQL
    assert "r.id = p_request_id" in SQL
    assert "max(o.sequence_no)" in SQL


def test_dispatch_hotfix_replaces_existing_rpc() -> None:
    assert "create or replace function public.jacc_dispatch_next_offer" in SQL
    assert "security definer" in SQL
    assert "commit;" in SQL
