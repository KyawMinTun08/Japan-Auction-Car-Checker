from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "phase2_production_launcher.py"


def _source() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_phase2_launcher_compiles() -> None:
    ast.parse(_source(), filename=str(LAUNCHER))


def test_phase2_launcher_installs_after_phase1_patches_before_main() -> None:
    source = _source()
    queue_import = source.index("import queue_launcher")
    phase2_install = source.index("PHASE2_RUNTIME = install_phase2_runtime()")
    telegram_main = source.index("asyncio.run(queue_launcher.main())")

    assert queue_import < phase2_install < telegram_main


def test_phase2_launcher_fails_closed_without_server_contract() -> None:
    source = _source()
    assert '_required_setting("SHEET_SERVER_KEY"' in source
    assert '"SHEET_WEBHOOK"' in source
    assert "phase2_install.install()" in source
    assert "os.environ.get(\"SHEET_SERVER_KEY\")" in source


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
