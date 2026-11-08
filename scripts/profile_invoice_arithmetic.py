"""Aggregate field arithmetic only; never print parties, identifiers or credentials."""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env', override=False)
from sqlalchemy import text
from db import engine
from holoo_finance import numeric

def close(a, b):
    return abs(a - b) <= Decimal('1')

with engine.connect() as conn:
    payload = conn.execute(text('SELECT payload FROM holoo_financial_snapshots ORDER BY id DESC LIMIT 1')).scalar_one()
report = {}
for kind in ('purchases', 'sales', 'purchase_returns', 'sales_returns'):
    stats = Counter()
    for invoice in payload['sources'][kind]['rows']:
        stats['invoices'] += 1
        gross = net_amount = net_percent = line_total = discount_amount = Decimal(0)
        for row in invoice['Detail']:
            stats['lines'] += 1
            g = numeric(row['Few']) * numeric(row['Price'])
            a, p, s = numeric(row.get('Discount', 0)), numeric(row.get('PersentDiscount', 0)), numeric(row['SumPrice'])
            gross += g
            net_amount += g-a
            net_percent += g*(1-p/100)
            line_total += s
            discount_amount += a
            stats['nonzero_amount_discount'] += a != 0
            stats['nonzero_percent_discount'] += p != 0
            stats['both_discount_equivalent'] += a != 0 and p != 0 and close(a, g*p/100)
            stats['sum_matches_gross'] += close(s,g)
            stats['sum_matches_amount_net'] += close(s,g-a)
            stats['sum_matches_percent_net'] += close(s,g*(1-p/100))
            stats['zero_price_positive_quantity'] += numeric(row['Few']) > 0 and numeric(row['Price']) == 0
            stats['nonzero_line_levy'] += numeric(row.get('Levy',0)) != 0
            stats['nonzero_line_scot'] += numeric(row.get('Scot',0)) != 0
        total, hd, levy, scot = [numeric(invoice.get(k,0)) for k in ('SumPrice','SumDiscount','SumLevy','SumScot')]
        paid = sum(numeric(invoice.get(k,0)) for k in ('SumNaghd','SumCard','SumNesiyeh','SumCheck'))
        stats['settlement_matches_gross_minus_hd'] += close(paid,gross-hd)
        stats['settlement_matches_gross_minus_hd_plus_tax'] += close(paid,gross-hd+levy+scot)
        stats['settlement_matches_percent_net_minus_hd_plus_tax'] += close(paid,net_percent-hd+levy+scot)
        stats['settlement_matches_percent_net_plus_tax'] += close(paid,net_percent+levy+scot)
        stats['header_discount_matches_percent_line_discount'] += close(hd,gross-net_percent)
        stats['settlement_matches_header'] += close(paid,total)
        if hd or gross != net_percent or total != gross:
            report.setdefault(kind+'_discount_arithmetic', []).append({'gross':str(gross),'sum_price':str(total),'header_discount':str(hd),'percent_line_discount':str(gross-net_percent),'levy':str(levy),'scot':str(scot),'settlement_sum':str(paid)})
        stats['header_nonzero_discount'] += hd != 0
        stats['header_nonzero_levy'] += levy != 0
        stats['header_nonzero_scot'] += scot != 0
        stats['header_matches_gross'] += close(total,gross)
        stats['header_matches_line_sum'] += close(total,line_total)
        stats['header_matches_line_sum_minus_hd'] += close(total,line_total-hd)
        stats['header_matches_gross_minus_hd'] += close(total,gross-hd)
        stats['header_matches_gross_minus_hd_plus_tax'] += close(total,gross-hd+levy+scot)
        stats['header_discount_matches_line_discount'] += close(hd,discount_amount)
        stats['header_matches_percent_net'] += close(total,net_percent)
        stats['header_matches_amount_net'] += close(total,net_amount)
        stats['header_matches_line_net_plus_tax'] += close(total,net_amount+levy+scot)
    report[kind] = dict(stats)
path = ROOT/'audit-2026-10-19'/'invoice-arithmetic.json'
path.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
