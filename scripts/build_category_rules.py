"""Build the browser's static rule module from the same data used on the server."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
 rules=json.loads((ROOT/'config/category-rules.json').read_text())
 (ROOT/'category-rules.js').write_text('// Generated from config/category-rules.json by scripts/build_category_rules.py.\nexport const categoryRules = '+json.dumps(rules,ensure_ascii=False,indent=2)+';\n')
