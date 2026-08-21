import ast
import datetime
import re
from pathlib import Path

source_path = Path('/home/ubuntu/jacc-ocr-sheet-link-20260821/legacy_bot.py')
source = source_path.read_text(encoding='utf-8')
tree = ast.parse(source)
needed = {
    'normalize_chassis_key', 'canonicalize_chassis', 'chassis_candidate_values',
    'normalize_year', '_gviz_cell', 'find_sheet_car_in_gviz_rows',
    'find_sheet_car_by_candidates_in_rows',
}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in needed]
assert {node.name for node in selected} == needed
namespace = {
    're': re,
    'datetime': datetime.datetime,
    'CHASSIS_PREFIX_MAP': {'GP1': 'FIT HYBRID', 'GP7': 'FIT SHUTTLE HYBRID'},
}
exec(compile(ast.Module(body=selected, type_ignores=[]), '<gp1-helpers>', 'exec'), namespace)

candidates = namespace['chassis_candidate_values']
resolve = namespace['find_sheet_car_by_candidates_in_rows']
assert candidates('GG7-106680') == ['GG7-106680', 'GP1-106680', 'GP7-106680']
assert candidates('GP1 106680') == ['GP1-106680', 'GG7-106680']

rows = [{
    'c': [
        {'v': '21/08/2026'}, {'v': 'GP1-106680'}, {'v': 'FIT HYBRID'},
        {'v': 'PEARL WHITE'}, {'v': 2014}, {'v': 78000}, {'v': 'MaeSot Freezone'},
        {'v': 'Admin'}, {'v': ''},
    ]
}]
row, source_name = resolve(rows, 'GG7-106680')
assert row is not None
assert source_name == 'sheet_candidate'
assert row['chassis'] == 'GP1-106680'
assert row['model'] == 'FIT HYBRID'
assert row['year'] == 2014
assert row['price'] == 78000.0

row, source_name = resolve([], 'GG7-106680')
assert row is None
assert source_name == 'none'

# No global GG7 -> GP1 replacement is allowed without persistent evidence.
assert 'replace("GG7", "GP1")' not in source
assert 'fill_{user_id}_chassis' in source
assert 'chassis_needs_review' in source
assert 'pdata["model"] = known_model' in source
assert 'known_model = guess_model_from_chassis(corrected_chassis)' in source
print('PASS: GG7 is converted to a GP1 candidate only when Sheet1 proves GP1-106680; no unsupported global rewrite; manual chassis review is wired.')
