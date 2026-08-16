from __future__ import annotations

import ast
from pathlib import Path

from jdm_lookup_service import JdmGradeService


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "index.html"


def test_crown_model_year_query_expands_2013_families() -> None:
    assert JdmGradeService.model_year_query("Toyota Crown 2013") == ("CROWN", 2013)
    matches = JdmGradeService.crown_reference_matches(year=2013, model="CROWN")
    assert {row["chassis_prefix"] for row in matches} == {"GRS210", "GRS211", "GRS214"}


def test_crown_hybrid_2013_query_returns_aws210_and_gws214() -> None:
    assert JdmGradeService.model_year_query("Crown Hybrid 2013") == ("CROWN HYBRID", 2013)
    matches = JdmGradeService.crown_reference_matches(year=2013, model="CROWN HYBRID")
    assert {row["chassis_prefix"] for row in matches} == {"AWS210", "GWS214"}


def test_prefixed_chassis_candidates_use_real_family_prefix() -> None:
    service = object.__new__(JdmGradeService)
    assert service.chassis_prefix_candidates("DAA-AWS210-6015461") == ["AWS210", "DAA"]
    assert service.chassis_prefix_candidates("GRS211-1234567") == ["GRS211"]
    assert service.chassis_prefix_candidates("AWS2106015461")[0] == "AWS210"


def test_reference_rows_are_not_presented_as_auction_grades() -> None:
    row = JdmGradeService.crown_reference_matches(year=2013, model="CROWN")[0]
    assert row["confidence"] == "reference"
    assert row["verified"] is False
    assert "not an auction condition grade" in row["source_note"].lower()


def test_frontend_has_direct_chassis_and_authorized_provider_links() -> None:
    source = INDEX.read_text(encoding="utf-8")
    assert "https://carvx.jp/chassis-number" in source
    assert "japan-source-primary" in source
    assert '<details class="japan-source-more">' in source
    assert "autoparts.beforward.jp/vehicle/TOYOTA/?frame_no=" in source
    assert "jp-carparts.com/toyota/cartypelist.php?maker=toyota&type=3311D0" in source
    assert "auctiondatasearch.jp" in source
    assert "japanstat.com/en" in source
    assert "not auction result" in source
