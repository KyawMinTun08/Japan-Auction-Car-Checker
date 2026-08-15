"""Dependency-free checks for the JACC Japan source handoff helpers."""

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from japan_source_check import is_valid_chassis, normalize_chassis, reply_text, source_links


def main() -> None:
    assert normalize_chassis(" \ufeff'agh30–0015779'\u200b ") == "AGH30-0015779"
    assert is_valid_chassis("AGH30-0015779")
    assert not is_valid_chassis("AGH30 0015779")
    assert not is_valid_chassis("AGH30")

    alphard_links = dict(source_links("AGH30-0015779"))
    assert alphard_links["↗ Goo-net Alphard"].endswith("/TOYOTA/ALPHARD/")

    generic_links = dict(source_links("NT32-504837"))
    assert generic_links["↗ Goo-net Catalog"] == "https://www.goo-net.com/catalog/"
    assert "AGH30-0015779" in reply_text("AGH30-0015779")
    print("japan_source_check tests: PASS")


if __name__ == "__main__":
    main()
