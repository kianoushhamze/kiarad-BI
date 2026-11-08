"""Export source catalog evidence for reviewing marketplace mappings; read only."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from db import engine

root = Path(__file__).resolve().parents[1]
with engine.connect() as conn:
    products = [dict(r) for r in conn.execute(text(
        "SELECT code, name FROM products WHERE is_active=1 ORDER BY name"
    )).mappings()]
    variants = [dict(r) for r in conn.execute(text(
        "SELECT dkp_id, title, holoo_code FROM digikala_variants ORDER BY dkp_id"
    )).mappings()]
target = root / "scripts" / "mapping_review_evidence.json"
target.write_text(json.dumps({"products": products, "variants": variants},
    ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(target)
