from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "phase2_production_launcher.py"


def _source() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_phase2_launcher_compiles() -> None:
    ast.parse(_source(), filename=str(LAUNCHER))


def test_phase2_launcher_preserves_live_guards_before_phase2_and_main() -> None:
    source = _source()
    safe_import = source.index("import safe_queue_launcher as phase1_safe")
    queue_alias = source.index("queue_launcher = phase1_safe._queue")
    phase2_install = source.index("PHASE2_RUNTIME = install_phase2_runtime()")
    telegram_main = source.index("asyncio.run(queue_launcher.main())")

    assert safe_import < queue_alias < phase2_install < telegram_main


def test_phase2_launcher_fails_closed_without_server_contract() -> None:
    source = _source()
    assert '_required_setting("SHEET_SERVER_KEY"' in source
    assert '"SHEET_WEBHOOK"' in source
    assert "phase2_install.install()" in source
    assert "os.environ.get(\"SHEET_SERVER_KEY\")" in source


def test_phase2_launcher_reuses_safety_patched_queue_instance() -> None:
    source = _source()
    assert "import safe_queue_launcher as phase1_safe" in source
    assert "queue_launcher = phase1_safe._queue" in source
    assert "import queue_launcher" not in source


def test_phase2_launcher_never_logs_secret_values() -> None:
    tree = ast.parse(_source(), filename=str(LAUNCHER))
    secret_names = {"SHEET_SERVER_KEY", "SHEET_WEBHOOK"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in {
            "debug",
            "info",
            "warning",
            "error",
            "critical",
        }:
            continue
        rendered = ast.unparse(node)
        assert not any(name in rendered for name in secret_names)
