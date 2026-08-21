import ast
import datetime
import re
from pathlib import Path

source_path = Path('/home/ubuntu/jacc-ocr-sheet-link-20260821/legacy_bot.py')
source = source_path.read_text(encoding='utf-8')
tree = ast.parse(source)
needed = {
    'normalize_chassis_key', 'canonicalize_chassis', 'normalize_year',
    'stage_auction_list_rows', 'guess_model_from_chassis',
}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in needed]
assert {node.name for node in selected} == needed
namespace = {
    're': re,
    'datetime': datetime.datetime,
    'CHASSIS_PREFIX_MAP': {'GP1': 'FIT HYBRID', 'GRS200': 'CROWN'},
}
exec(compile(ast.Module(body=selected, type_ignores=[]), '<list-staging-helpers>', 'exec'), namespace)

stage = namespace['stage_auction_list_rows']
rows, duplicates, invalid = stage([
    {'chassis': 'GP1 106680', 'model': 'unknown', 'color': 'PEARL WHITE', 'year': 2014},
    {'chassis': 'GP1-106680', 'model': 'FIT HYBRID', 'color': 'WHITE', 'year': 2014},
    {'chassis': 'GRS200-0038906', 'model': 'CROWN', 'color': 'WHITE', 'year': 0},
    {'chassis': 'not a chassis', 'model': 'X', 'color': 'WHITE', 'year': 2014},
], 'MaeSot Freezone', existing_chassis=['GRS200-0038906'])
assert len(rows) == 1
assert rows[0]['chassis'] == 'GP1-106680'
assert rows[0]['model'] == 'FIT HYBRID'
assert rows[0]['year'] == 2014
assert rows[0]['location'] == 'MaeSot Freezone'
assert rows[0]['price'] == 0
assert len(duplicates) == 2
assert 'not a chassis' in invalid

# The staged helper must not call a write endpoint or mutate CARS.
assert 'SHEET_WEBHOOK' not in ast.get_source_segment(source, selected[-1])
assert 'CARS.append' not in ast.get_source_segment(source, selected[-1])
assert 'Admin Confirm & Save' in source
assert 'Re-read Sheet1 immediately before writing' in source
print('PASS: list rows are normalized/staged, existing and intra-list duplicates are rejected, invalid rows are held, and writes require Admin confirmation.')
