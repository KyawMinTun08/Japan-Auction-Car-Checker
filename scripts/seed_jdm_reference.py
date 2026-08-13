from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy_bot.py"
OUT = ROOT / "supabase/migrations/202608130002_seed_jdm_reference.sql"

# Keep the canonical manufacturer grouping aligned with the audited website map.
BRAND_MODELS = {
    "Toyota": [
        "CROWN", "CROWN HYBRID", "WISH", "ALPHARD", "VELLFIRE", "VOXY",
        "HIACE", "HIACE VAN", "HIACE WAGON", "SUCCEED", "SUCCEED VAN",
        "SUCCEED WAGON", "PROBOX", "VANGUARD", "LAND CRUISER",
        "LAND CRUISER PRADO", "PRIUS", "AQUA", "COROLLA", "CAMRY",
        "HARRIER", "YARIS", "FORTUNER", "ESTIMA", "NOAH", "SIENTA",
        "RUSH", "MARK X", "KLUGER", "HILUX", "HILUX SURF", "IQ", "BELTA",
        "BLADE", "CELSIOR", "COROLLA FIELDER", "PASSO", "RACTIS",
        "TOWNACE VAN", "VITZ", "SUPER CUSTOM", "PIXIS TRUCK", "PIXIS VAN",
    ],
    "Lexus": ["LEXUS LS"],
    "Nissan": [
        "AD VAN", "X-TRAIL", "JUKE", "NOTE", "SERENA", "ELGRAND", "TEANA",
        "VANETTE VAN", "VANETTE TRUCK", "LEAF", "GT-R", "MARCH", "DAYZ",
        "LAFESTA", "FUGA", "MINICAB TRUCK",
    ],
    "Honda": [
        "FIT", "FIT HYBRID", "FIT SHUTTLE HYBRID", "INSIGHT", "FREED",
        "STEPWGN", "ODYSSEY", "N-BOX", "JADE", "VEZEL", "GRACE", "STREAM",
        "CR-V",
    ],
    "Daihatsu": [
        "HIJET", "HIJET TRUCK", "HIJET VAN", "MOVE", "TANTO", "MIRA", "ROCKY",
        "BOON", "WAKE", "CAST", "THOR", "ATRAI",
    ],
    "Mitsubishi": [
        "PAJERO", "OUTLANDER", "DELICA", "ECLIPSE", "ECLIPSE CROSS", "GALANT",
        "TRITON", "COLT", "ASX", "RVR",
    ],
    "Subaru": [
        "IMPREZA", "SAMBAR", "SAMBAR TRUCK", "SAMBAR VAN", "FORESTER", "LEGACY",
        "OUTBACK", "XV", "WRX", "BRZ", "EXIGA",
    ],
    "Mazda": [
        "BONGO TRUCK", "ATENZA", "DEMIO", "CX-5", "CX-3", "AXELA", "FAMILIA",
        "BIANTE", "PREMACY", "SCRUM TRUCK",
    ],
    "Suzuki": [
        "ALTO", "EVERY", "CARRY", "CARRY TRUCK", "JIMNY", "SWIFT", "SOLIO",
        "SPACIA", "WAGON R", "HUSTLER", "IGNIS",
    ],
    "Hino": ["DUTRO", "RANGER", "PROFIA"],
    "Mitsubishi Fuso": [
        "CANTER", "CANTER GUTS", "FUSO", "FUSO TRUCK", "FUSO FIGHTER", "SUPER GREAT",
    ],
    "UD/Nissan Truck": ["CONDOR", "QUON", "UD", "BIG THUMB"],
}

BODY_TYPES = {
    "Sedan": {"CROWN", "CROWN HYBRID", "TEANA", "CAMRY", "COROLLA", "ATENZA", "LEGACY", "IMPREZA", "AXELA", "FUGA", "GRACE", "LAFESTA", "WRX", "LEXUS LS", "BELTA", "CELSIOR", "COROLLA FIELDER", "MARK X"},
    "SUV": {"X-TRAIL", "PAJERO", "OUTLANDER", "HARRIER", "VANGUARD", "FORESTER", "CX-5", "CX-3", "CR-V", "LAND CRUISER", "LAND CRUISER PRADO", "ROCKY", "XV", "FORTUNER", "ECLIPSE CROSS", "RUSH", "ASX", "VEZEL", "KLUGER", "HILUX SURF"},
    "Van": {"AD VAN", "HIACE", "HIACE VAN", "HIACE WAGON", "SUCCEED", "SUCCEED VAN", "DELICA", "EVERY", "PROBOX", "STREAM", "ATRAI", "TOWNACE VAN", "SUPER CUSTOM", "VANETTE VAN", "HIJET VAN", "PIXIS VAN", "SAMBAR VAN"},
    "Truck": {"HIJET", "HIJET TRUCK", "SAMBAR", "SAMBAR TRUCK", "BONGO TRUCK", "VANETTE TRUCK", "TRITON", "HILUX", "MINICAB TRUCK", "BIG THUMB", "CANTER", "CANTER GUTS", "FUSO", "FUSO TRUCK", "FUSO FIGHTER", "SUPER GREAT", "DUTRO", "RANGER", "QUON", "CONDOR", "UD", "PIXIS TRUCK", "CARRY", "CARRY TRUCK", "SCRUM TRUCK"},
    "Minivan": {"ALPHARD", "VELLFIRE", "VOXY", "SERENA", "STEPWGN", "FREED", "ELGRAND", "ODYSSEY", "JADE", "WISH", "NOAH", "SIENTA", "ESTIMA", "EXIGA", "BIANTE", "PREMACY"},
    "Wagon": {"FIT SHUTTLE HYBRID", "SUCCEED WAGON"},
    "Hatchback": {"FIT", "FIT HYBRID", "INSIGHT", "JUKE", "NOTE", "LEAF", "AQUA", "YARIS", "DEMIO", "ALTO", "BOON", "SWIFT", "MARCH", "MOVE", "TANTO", "MIRA", "N-BOX", "WAKE", "CAST", "DAYZ", "SPACIA", "WAGON R", "HUSTLER", "IGNIS", "THOR", "IQ", "VITZ", "PASSO", "BLADE", "RACTIS", "NEW BEETLE"},
}


def sql_text(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"


def extract_chassis_map() -> dict[str, str]:
    tree = ast.parse(LEGACY.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CHASSIS_PREFIX_MAP":
                    value = ast.literal_eval(node.value)
                    return {str(k).upper(): str(v).upper() for k, v in value.items()}
    raise RuntimeError("CHASSIS_PREFIX_MAP not found")


def canonical_model(raw: str) -> str:
    value = raw.strip().upper()
    replacements = {
        "ADVAN": "AD VAN",
        "CRV": "CR-V",
        "CX5": "CX-5",
        "FUSO TRUCK": "FUSO TRUCK",
        "DUTRO TRUCK": "DUTRO",
        "SK82VN": "VANETTE VAN",
    }
    return replacements.get(value, value)


def make_for_model(model: str) -> str | None:
    for make, models in BRAND_MODELS.items():
        if model in models:
            return make
    return None


def body_for_model(model: str) -> str | None:
    for body, models in BODY_TYPES.items():
        if model in models:
            return body
    return None


def main() -> None:
    raw_map = extract_chassis_map()
    chassis_map = {}
    for prefix, raw_model in raw_map.items():
        model = canonical_model(raw_model)
        if prefix == "SK82VN":
            model = "VANETTE VAN"
        make = make_for_model(model)
        if make:
            chassis_map[prefix] = model

    models = sorted({model for model in chassis_map.values()})
    lines = [
        "-- Generated from legacy_bot.py CHASSIS_PREFIX_MAP.",
        "-- Canonical corrections: VZNY12 -> AD VAN; SK82VN -> VANETTE VAN.",
        "-- This seed only creates reference mappings; it does not modify Sheet1 or Members.",
        "",
    ]

    for make, model_list in BRAND_MODELS.items():
        for model in model_list:
            if model not in models:
                continue
            body = body_for_model(model)
            lines.append(
                "insert into public.jacc_vehicle_models (make_id, canonical_name, body_type, vehicle_category) "
                f"select id, {sql_text(model)}, {sql_text(body)}, {sql_text(body)} "
                f"from public.jacc_vehicle_makes where make_key = {sql_text(make.lower().replace('/', '_').replace(' ', '_'))} "
                f"on conflict (make_id, canonical_name) do update set body_type = excluded.body_type, vehicle_category = excluded.vehicle_category, updated_at = now();"
            )

    for prefix, model in sorted(chassis_map.items()):
        make = make_for_model(model)
        body = body_for_model(model)
        lines.append(
            "insert into public.jacc_chassis_codes "
            "(model_id, chassis_prefix, chassis_prefix_normalized, body_type, source_id, confidence, verified, notes) "
            f"select vm.id, {sql_text(prefix)}, {sql_text(prefix)}, {sql_text(body)}, ds.id, 'manual', true, "
            f"'Imported from audited JACC mapping; source model={model}' "
            "from public.jacc_vehicle_models vm "
            "join public.jacc_vehicle_makes mk on mk.id = vm.make_id "
            "join public.jacc_data_sources ds on ds.source_key = 'jacc_manual_verified' "
            f"where mk.make_key = {sql_text(make.lower().replace('/', '_').replace(' ', '_'))} "
            f"and vm.canonical_name = {sql_text(model)} "
            "on conflict (chassis_prefix_normalized, model_id) do update set "
            "body_type = excluded.body_type, source_id = excluded.source_id, confidence = excluded.confidence, "
            "verified = excluded.verified, notes = excluded.notes, updated_at = now();"
        )

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"models": len(models), "chassis_prefixes": len(chassis_map), "output": str(OUT)}))


if __name__ == "__main__":
    main()
