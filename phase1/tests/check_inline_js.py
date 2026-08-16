from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
html = (root / "index.html").read_text(encoding="utf-8")
blocks = re.findall(r"<script(?:\\s[^>]*)?>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
if not blocks:
    raise SystemExit("no inline scripts found")
for index, block in enumerate(blocks, 1):
    with tempfile.NamedTemporaryFile("w", suffix=f"-{index}.js", encoding="utf-8", delete=False) as handle:
        handle.write(block)
        path = handle.name
    result = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"inline script {index} failed\\n{result.stderr}")
print(f"{len(blocks)} inline scripts passed node --check")
