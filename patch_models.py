# -*- coding: utf-8 -*-
"""Adds the Holoo columns to models.py (safe to run more than once).

Usage:  python patch_models.py [path/to/models.py]
Default: models.py next to this script.
Then run migrate_holoo.py so the database gets the same columns.
"""
import re
import sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("models.py")
if not path.exists():
    print(f"ERR: {path} not found")
    sys.exit(1)

src = path.read_text(encoding="utf-8")
out = src
changes = []

SALE_FIELDS = (
    "\n\n    # Holoo sync fields\n"
    "    holoo_code = Column(Integer, nullable=True, unique=True)\n"
    "    holoo_sanad_code = Column(Integer, nullable=True)\n"
    "    paid_amount = Column(Float, default=0)\n"
    "    credit_amount = Column(Float, default=0)\n"
    "    discount_amount = Column(Float, default=0)"
)
CUSTOMER_FIELD = (
    "\n    # responsible visitor (Holoo invoices do not carry it)\n"
    "    salesperson_id = Column(Integer, ForeignKey(\"salespersons.id\"), nullable=True)"
)

if re.search(r"class Sale\(Base\):.*?holoo_code", out, flags=re.S):
    print("SKIP: Sale already has holoo_code")
else:
    out, n = re.subn(r"(class Sale\(Base\):.*?total_amount = Column\(Float\))",
                     lambda m: m.group(1) + SALE_FIELDS, out, count=1, flags=re.S)
    if n == 0:
        print("ERR: could not find 'total_amount = Column(Float)' inside class Sale")
        sys.exit(2)
    changes.append("Sale: holoo_code, holoo_sanad_code, paid_amount, credit_amount, discount_amount")

customer_block = re.search(r"class Customer\(Base\):.*?(?=\nclass )", out, flags=re.S)
if customer_block and "salesperson_id" in customer_block.group(0):
    print("SKIP: Customer already has salesperson_id")
else:
    out, n = re.subn(r"(class Customer\(Base\):.*?created_at = Column\(DateTime, default=datetime\.utcnow\))",
                     lambda m: m.group(1) + CUSTOMER_FIELD, out, count=1, flags=re.S)
    if n == 0:
        print("ERR: could not find 'created_at' inside class Customer")
        sys.exit(3)
    changes.append("Customer: salesperson_id")

if not changes:
    print("Nothing to do.")
    sys.exit(0)

backup = path.with_name(path.name + ".before_holoo_patch")
if not backup.exists():
    backup.write_text(src, encoding="utf-8")
path.write_text(out, encoding="utf-8")
print("OK: models.py patched ->", "; ".join(changes))
print("Backup:", backup.name)
