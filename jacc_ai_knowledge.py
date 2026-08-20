"""Verified JACC car-domain knowledge used to ground the JACC AI text planner.

This module contains no secrets and is safe to import from Railway code only. It
is intentionally conservative: it supplies vocabulary and known data boundaries,
not fabricated market prices, auction scores, or purchase recommendations.
"""

from __future__ import annotations

from typing import Any

JACC_AI_KNOWLEDGE_VERSION = "2026.08.19"

# Keep this vocabulary aligned with scripts/seed_jdm_reference.py. It is used
# only for model-name recognition and prompt grounding; it is not a price table.
JACC_MODEL_VOCABULARY: dict[str, tuple[str, ...]] = {
    "Toyota": (
        "CROWN", "CROWN HYBRID", "WISH", "ALPHARD", "VELLFIRE", "VOXY",
        "HIACE", "HIACE VAN", "HIACE WAGON", "SUCCEED", "SUCCEED VAN",
        "SUCCEED WAGON", "PROBOX", "VANGUARD", "LAND CRUISER",
        "LAND CRUISER PRADO", "PRIUS", "AQUA", "COROLLA", "CAMRY",
        "HARRIER", "YARIS", "FORTUNER", "ESTIMA", "NOAH", "SIENTA",
        "RUSH", "MARK X", "KLUGER", "HILUX", "HILUX SURF", "IQ", "BELTA",
        "BLADE", "CELSIOR", "COROLLA FIELDER", "PASSO", "RACTIS",
        "TOWNACE VAN", "VITZ", "SUPER CUSTOM", "PIXIS TRUCK", "PIXIS VAN",
    ),
    "Lexus": ("LEXUS LS",),
    "Nissan": (
        "AD VAN", "X-TRAIL", "JUKE", "NOTE", "SERENA", "CARAVAN", "CARAVANS", "ELGRAND", "TEANA",
        "VANETTE VAN", "VANETTE TRUCK", "LEAF", "GT-R", "MARCH", "DAYZ",
        "LAFESTA", "FUGA", "MINICAB TRUCK",
    ),
    "Honda": (
        "FIT", "FIT HYBRID", "FIT SHUTTLE HYBRID", "INSIGHT", "FREED",
        "STEPWGN", "ODYSSEY", "N-BOX", "JADE", "VEZEL", "GRACE", "STREAM",
        "CR-V",
    ),
    "Daihatsu": (
        "HIJET", "HIJET TRUCK", "HIJET VAN", "MOVE", "TANTO", "MIRA", "ROCKY",
        "BOON", "WAKE", "CAST", "THOR", "ATRAI",
    ),
    "Mitsubishi": (
        "PAJERO", "OUTLANDER", "DELICA", "ECLIPSE", "ECLIPSE CROSS", "GALANT",
        "TRITON", "COLT", "ASX", "RVR",
    ),
    "Subaru": (
        "IMPREZA", "SAMBAR", "SAMBAR TRUCK", "SAMBAR VAN", "FORESTER", "LEGACY",
        "OUTBACK", "XV", "WRX", "BRZ", "EXIGA",
    ),
    "Mazda": (
        "BONGO TRUCK", "ATENZA", "DEMIO", "CX-5", "CX-3", "AXELA", "FAMILIA",
        "BIANTE", "PREMACY", "SCRUM TRUCK",
    ),
    "Suzuki": (
        "ALTO", "EVERY", "CARRY", "CARRY TRUCK", "JIMNY", "SWIFT", "SOLIO",
        "SPACIA", "WAGON R", "HUSTLER", "IGNIS",
    ),
    "Hino": ("DUTRO", "RANGER", "PROFIA"),
    "Mitsubishi Fuso": (
        "CANTER", "CANTER GUTS", "FUSO", "FUSO TRUCK", "FUSO FIGHTER", "SUPER GREAT",
    ),
    "UD/Nissan Truck": ("CONDOR", "QUON", "UD", "BIG THUMB"),
}

JACC_BODY_TYPES: tuple[str, ...] = (
    "Sedan", "SUV", "Van", "Truck", "Minivan", "Wagon", "Hatchback",
)

JACC_CAR_DOMAIN_RULES: tuple[str, ...] = (
    "JACC AI is restricted to Japanese auction-car topics and JACC car records.",
    "JACC member records can contain model, year, price, location, chassis, date, and color.",
    "Use verified JACC chassis/model mappings for reference facts; do not invent missing fields.",
    "Factory Grade/Trim and Auction Condition Grade are different concepts.",
    "Never infer an exact auction grade, mileage, accident history, inspection result, or final landed cost from model/year alone.",
    "An exact auction condition grade requires a verified auction sheet or provider record.",
    "If a grade fact is unavailable, say it is not available and direct the member to JDM Grade lookup or an auction sheet.",
)


def prompt_context() -> str:
    """Return compact, non-secret context for the provider system message."""
    catalog = "; ".join(
        f"{make}: {', '.join(models)}" for make, models in JACC_MODEL_VOCABULARY.items()
    )
    rules = " ".join(JACC_CAR_DOMAIN_RULES)
    return f"Knowledge version {JACC_AI_KNOWLEDGE_VERSION}. Models: {catalog}. Body types: {', '.join(JACC_BODY_TYPES)}. Rules: {rules}"


def public_knowledge_payload() -> dict[str, Any]:
    """Return safe metadata for the frontend; never include private credentials."""
    return {
        "version": JACC_AI_KNOWLEDGE_VERSION,
        "scope": "verified JACC car knowledge",
        "grade_notice": (
            "Factory Grade/Trim နဲ့ Auction Condition Grade မတူပါ။ "
            "JACC မှာ exact auction grade ကို model/year တစ်ခုတည်းနဲ့ မခန့်မှန်းပါ။ "
            "Verified auction sheet/provider record သို့မဟုတ် JDM Grade lookup လိုအပ်ပါတယ်။"
        ),
        "missing_data_notice": (
            "မရှိတဲ့ chassis, grade, mileage, accident, inspection, ownership သို့မဟုတ် final cost ကို AI က မဖန်တီးပါ။"
        ),
    }
