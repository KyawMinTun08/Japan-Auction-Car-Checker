from japan_source_check import is_valid_chassis, normalize_chassis, reply_text, source_links


def test_normalize_chassis_removes_copy_paste_artifacts() -> None:
    assert normalize_chassis(" \ufeff'agh30–0015779'\u200b ") == "AGH30-0015779"


def test_validation_requires_prefix_and_serial() -> None:
    assert is_valid_chassis("AGH30-0015779")
    assert not is_valid_chassis("AGH30 0015779")
    assert not is_valid_chassis("AGH30")


def test_alphard_prefix_uses_specific_catalog_link() -> None:
    links = dict(source_links("AGH30-0015779"))
    assert links["↗ Goo-net Alphard"].endswith("/TOYOTA/ALPHARD/")
    assert "AGH30-0015779" in reply_text("AGH30-0015779")


def test_other_prefix_uses_generic_catalog_link() -> None:
    links = dict(source_links("NT32-504837"))
    assert links["↗ Goo-net Catalog"] == "https://www.goo-net.com/catalog/"
