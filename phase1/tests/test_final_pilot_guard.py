from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GUARD = (ROOT / "phase1_final_pilot_guard.py").read_text(encoding="utf-8")
RESTORE_CHAIN = (ROOT / "phase1_restore_latest.py").read_text(encoding="utf-8")


def test_guard_recognizes_dispatch_ambiguity() -> None:
    assert '"42702" in error_text' in GUARD
    assert '"request_id" in lowered and "ambiguous" in lowered' in GUARD
    assert "MIGRATION REQUIRED" in GUARD
    assert "008_fix_dispatch_offer_ambiguity.sql" in GUARD


def test_guard_replaces_final_pilot_router() -> None:
    assert "_pilot.phase1finalpilot_cmd = phase1finalpilot_cmd" in GUARD
    assert "_pilot.brokers_final_pilot_router = brokers_final_pilot_router" in GUARD


def test_guard_loads_after_final_pilot() -> None:
    pilot_import = RESTORE_CHAIN.index("import phase1_final_pilot as")
    guard_import = RESTORE_CHAIN.index("import phase1_final_pilot_guard as")
    assert pilot_import < guard_import
