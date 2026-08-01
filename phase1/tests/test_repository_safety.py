from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Telegram bot token",
        re.compile(r"(?<![A-Za-z0-9])\d{8,12}:[A-Za-z0-9_-]{30,}(?![A-Za-z0-9])"),
    ),
    (
        "JWT/service-role token",
        re.compile(
            r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{20,}\."
            r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"
        ),
    ),
    (
        "OpenAI API key",
        re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    ),
    (
        "GitHub token",
        re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"),
    ),
)

_DESTRUCTIVE_SQL = re.compile(
    r"\b(?:drop\s+table|truncate\s+table|delete\s+from)\b",
    re.IGNORECASE,
)

_TEXT_SUFFIXES = {
    ".css",
    ".env",
    ".example",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sql",
    ".txt",
    ".yaml",
    ".yml",
}


def _tracked_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
    )
    return [ROOT / item.decode("utf-8") for item in output.split(b"\0") if item]


def _read_text(path: Path) -> str | None:
    if path.suffix.lower() not in _TEXT_SUFFIXES and path.name != "Procfile":
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def test_no_high_confidence_secrets_are_committed() -> None:
    findings: list[str] = []
    for path in _tracked_files():
        text = _read_text(path)
        if text is None:
            continue
        relative = path.relative_to(ROOT)
        for label, pattern in _SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: possible {label}")

    assert not findings, "Committed secret-like values detected:\n" + "\n".join(findings)


def test_phase1_migrations_do_not_contain_destructive_table_commands() -> None:
    findings: list[str] = []
    sql_root = ROOT / "phase1" / "sql"
    for path in sorted(sql_root.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        for match in _DESTRUCTIVE_SQL.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{path.relative_to(ROOT)}:{line}")

    assert not findings, (
        "Destructive table command found in Phase 1 migration; "
        "use an explicitly reviewed maintenance script instead:\n"
        + "\n".join(findings)
    )
