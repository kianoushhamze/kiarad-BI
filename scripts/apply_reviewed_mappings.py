"""Apply explicitly reviewed model matches without removing existing mappings."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from db import engine

matches = [
    ("73099990", "500001", "PDRN", "ELVATAN"),
    ("73103774", "300010", "HT2", "DERMALIST"),
]
with engine.begin() as conn:
    for variant, code, model, brand in matches:
        title = conn.execute(text("SELECT title FROM digikala_variants WHERE dkp_id::text=:v"), {"v": variant}).scalar_one()
        name = conn.execute(text("SELECT name FROM products WHERE code=:c AND is_active=1"), {"c": code}).scalar_one()
        if model.lower() not in title.lower() or model.lower() not in name.lower() or brand not in name:
            raise ValueError("reviewed_model_evidence_changed")
        previous = conn.execute(text("SELECT holoo_code FROM variant_map WHERE supplier_code=:v"), {"v": variant}).scalar_one_or_none()
        if previous and previous != code:
            raise ValueError("existing_mapping_conflict")
        if previous is None:
            conn.execute(text("INSERT INTO variant_map (supplier_code,holoo_code,note,updated_at) VALUES (:v,:c,:n,NOW())"), {"v": variant, "c": code, "n": "reviewed exact model " + model})
        conn.execute(text("UPDATE digikala_variants SET holoo_code=:c WHERE dkp_id::text=:v AND (holoo_code IS NULL OR holoo_code=:c)"), {"v": variant, "c": code})
print("reviewed_matches=2; marketplace_writes=false")
