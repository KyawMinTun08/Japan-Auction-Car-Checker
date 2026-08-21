import ast
import datetime
import re
from pathlib import Path

source_path = Path('/home/ubuntu/jacc-ocr-sheet-link-20260821/legacy_bot.py')
source = source_path.read_text(encoding='utf-8')
tree = ast.parse(source)
needed = {
    'normalize_chassis_key', '_gviz_cell', 'normalize_year',
    'find_sheet_car_in_gviz_rows', 'extract_chassis_from_text',
}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in needed]
if {node.name for node in selected} != needed:
    raise AssertionError('sheet-link OCR helpers not found')

# Load only the pure helpers; no Telegram, API, or production mutation is performed.
namespace = {
    're': re,
    'datetime': datetime.datetime,
    'CHASSIS_PREFIX_MAP': {'GB3': 'FREED', 'NT32': 'X-TRAIL'},
}
exec(compile(ast.Module(body=selected, type_ignores=[]), '<sheet-link-helpers>', 'exec'), namespace)

normalize_chassis_key = namespace['normalize_chassis_key']
extract_chassis_from_text = namespace['extract_chassis_from_text']
find_sheet_car_in_gviz_rows = namespace['find_sheet_car_in_gviz_rows']

assert normalize_chassis_key('GB3-1604823') == normalize_chassis_key('gb3 1604823')
assert extract_chassis_from_text('windshield: GB3 1604823') == 'GB3-1604823'
assert extract_chassis_from_text('windshield: GB31604823') == 'GB3-1604823'

live_like_rows = [{
    'c': [
        {'v': '21/08/2026'}, {'v': 'GB3-1604823'}, {'v': 'HONDA FREED'},
        {'v': 'WHITE'}, {'v': 2014}, {'v': 43000}, {'v': 'MaeSot Freezone'},
        {'v': 'Christopher'}, {'v': ''},
    ]
}]
row = find_sheet_car_in_gviz_rows(live_like_rows, 'GB3 1604823')
assert row is not None
assert row['chassis'] == 'GB3-1604823'
assert row['model'] == 'HONDA FREED'
assert row['color'] == 'WHITE'
assert row['year'] == 2014
assert row['price'] == 43000.0
assert row['location'] == 'MaeSot Freezone'
assert row['source'] == 'sheet_exact'
assert find_sheet_car_in_gviz_rows(live_like_rows, 'GB3-999999') is None

for fragment in (
    'sheet_car, sheet_match_source = await lookup_sheet_car_by_candidates(chassis) if chassis else (None, "none")',
    'match_source = sheet_match_source if sheet_car',
    'source": "sheet_exact"',
    'Do not infer a year from the chassis prefix',
):
    if fragment not in source:
        raise AssertionError(f'missing exact-link guard: {fragment}')

print('PASS: handwritten chassis variants normalize; live GB3 sheet row links to model/color/year/location; unknown chassis does not match.')
