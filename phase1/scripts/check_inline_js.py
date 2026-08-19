from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
html = (root / "index.html").read_text(encoding="utf-8")
scripts = re.findall(r"<script(?:\\s[^>]*)?>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
separator = chr(10) * 2
Path("/tmp/jacc-inline-scripts.js").write_text(separator.join(scripts), encoding="utf-8")
print(f"extracted {len(scripts)} inline script blocks")
