"""Pure helpers for JACC's Telegram Japan source handoff command.

This module deliberately contains no Telegram, Google Sheets, Supabase or
environment-variable access so its input normalisation and source URLs can be
unit tested without touching production member data.
"""

from __future__ import annotations

import re


_INVISIBLE = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}
_OUTER_QUOTES = {"'", '"', "“", "”", "‘", "’"}
_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-", "‐": "-"})
_CHASSIS_PATTERN = re.compile(r"^[A-Z0-9]{2,12}-[A-Z0-9]{2,16}$")


def normalize_chassis(value: object) -> str:
    """Remove copy/paste artifacts without changing meaningful characters."""
    text = "".join(ch for ch in str(value or "") if ch not in _INVISIBLE)
    text = text.strip()
    if len(text) >= 2 and text[0] in _OUTER_QUOTES and text[-1] in _OUTER_QUOTES:
        text = text[1:-1].strip()
    return text.translate(_DASHES).upper()


def is_valid_chassis(value: str) -> bool:
    return bool(_CHASSIS_PATTERN.fullmatch(value))


def source_links(chassis: str) -> list[tuple[str, str]]:
    """Return user-selected external source pages; JACC does not scrape them."""
    prefix = chassis.split("-", 1)[0]
    links = [
        ("↗ SBT Japan", "https://www.sbtjapan.com/support/vehicle_inspection/chassis-check"),
        ("↗ Real Motor", "https://www.realmotor.jp/catalog"),
        ("↗ CAR VX", "https://carvx.jp/chassis-number"),
        ("↗ Free JDM Decoder", "https://www.ts-export.com/page.php?page=about_vin_decoders"),
    ]
    if prefix in {"AGH30", "AGH35", "GGH30", "GGH35", "AYH30"}:
        links.insert(
            1,
            ("↗ Goo-net Alphard", "https://www.goo-net.com/catalog/TOYOTA/ALPHARD/"),
        )
    else:
        links.insert(1, ("↗ Goo-net Catalog", "https://www.goo-net.com/catalog/"))
    return links


def reply_text(chassis: str) -> str:
    return (
        "🔎 *JACC Japan Source Check*\n\n"
        f"🔑 Chassis: `{chassis}`\n\n"
        "ဒီ chassis ကို Japan source page များမှာ ထပ်စစ်နိုင်ပါတယ်။\n"
        "📋 Copy chassis ကိုနှိပ်ပြီး source page မှာ paste လုပ်ပါ။\n\n"
        "⚠️ JACC က source content ကို auto မကူးပါ။ "
        "Source website ရဲ့ result၊ terms နဲ့ accuracy disclaimer အတိုင်း အသုံးပြုပါ။"
    )
