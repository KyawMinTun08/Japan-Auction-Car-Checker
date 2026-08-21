import ast
import datetime
import re
from pathlib import Path

source_path = Path('/home/ubuntu/jacc-ocr-fix-20260821/legacy_bot.py')
source = source_path.read_text(encoding='utf-8')
tree = ast.parse(source)
needed = {'normalize_model_label', 'choose_verified_model', 'normalize_year', 'choose_verified_year'}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in needed]
if {node.name for node in selected} != needed:
    raise AssertionError('trusted OCR helper functions not found')
namespace = {
    're': re,
    'datetime': datetime.datetime,
    'guess_model_from_chassis': lambda chassis: {
        'GB3-1604823': 'FREED',
        'NT32-024640': 'X-TRAIL',
    }.get(chassis.upper(), 'UNKNOWN'),
}
exec(compile(ast.Module(body=selected, type_ignores=[]), '<trusted-ocr-helpers>', 'exec'), namespace)

choose_verified_model = namespace['choose_verified_model']
normalize_year = namespace['normalize_year']
choose_verified_year = namespace['choose_verified_year']

assert choose_verified_model('GB3-1604823', 'FREED', 'CROWN') == ('FREED', 'database', False)
assert choose_verified_model('GB3-1604823', '', 'CROWN') == ('FREED', 'chassis_prefix', False)
assert choose_verified_model('ZZZ-123456', '', 'CROWN') == ('CROWN', 'vision_review', True)
assert choose_verified_model('ZZZ-123456', '', '') == ('UNKNOWN', 'manual', True)
assert normalize_year('2002') == 2002
assert choose_verified_year(0, 0, 0) == (0, 'manual')
assert choose_verified_year(0, 2014, 0) == (2014, 'database')
assert choose_verified_year(2013, 2014, 0) == (2013, 'caption')

required_fragments = [
    'if info.get("model_needs_review"):',
    'pdata["model_needs_review"] = False',
    '"model_needs_review": model_needs_review',
    'InlineKeyboardButton("✏️ Model ဖြည့်", callback_data=f"fill_{user_id}_model")',
]
for fragment in required_fragments:
    if fragment not in source:
        raise AssertionError(f'missing production guard: {fragment}')

print('PASS: verified model/prefix beats vision-only model; AI-only model/year require review; manual model clears review; model-review button remains reachable.')
