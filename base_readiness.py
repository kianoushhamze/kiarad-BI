"""Read-only structural gaps in the local base registry; never infers business facts."""
import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from sqlalchemy import text

BASES = ('pharmacies', 'cosmetics_shops', 'kerman_bases_manual')
GAPS = ('owner', 'location', 'grade', 'capacity', 'customer', 'type')


def valid_location(latitude, longitude):
    try:
        lat, lon = float(latitude), float(longitude)
        return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
    except (ValueError, TypeError, OverflowError):
        return False


def positive_capacity(value):
    try:
        number = Decimal(str(value))
        return number.is_finite() and number > 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def summarize(rows):
    items = []
    counts = Counter({gap: 0 for gap in GAPS})
    for row in rows:
        profile = row.get('profile') or {}
        missing = []
        # Exactly one assignment with an active field account is required.
        if row['owner_count'] != 1 or not row['owner_active']:
            missing.append('owner')
        if not valid_location(row.get('latitude'), row.get('longitude')):
            missing.append('location')
        if profile.get('grade') not in ('A', 'B', 'C'):
            missing.append('grade')
        if not positive_capacity(profile.get('monthly_capacity')):
            missing.append('capacity')
        if not row['customer_exists']:
            missing.append('customer')
        if str(row.get('type') or '').strip() in ('', 'unknown', 'holoo_counterparty'):
            missing.append('type')
        counts.update(missing)
        items.append({'source': row['source'], 'id': row['id'], 'name': row['name'],
                      'city': row['city'], 'missing': missing})
    return {'total': len(items), 'without_structural_gaps': sum(not item['missing'] for item in items),
            'counts': dict(counts), 'items': items,
            'basis': 'local_structural_fields_only',
            'notice': 'وجود مختصات یا تکمیل فیلدها، تأیید دقت موقعیت، هویت، گرید یا پوشش واقعی استان نیست.'}


def collect_readiness(conn):
    union = ' UNION ALL '.join(
        f"SELECT '{source}' AS source,b.id,b.name,b.city,b.type,"
        f"to_jsonb(b)->>'latitude' AS latitude,to_jsonb(b)->>'longitude' AS longitude FROM {source} b"
        for source in BASES)
    rows = conn.execute(text('''WITH bases AS (''' + union + '''), profiles AS (
        SELECT DISTINCT ON (base_source,base_id) base_source,base_id,payload
        FROM base_coach_profiles ORDER BY base_source,base_id,revision DESC,id DESC)
        SELECT b.*,p.payload AS profile, a.owner_count,COALESCE(a.owner_active,FALSE) AS owner_active,
            EXISTS(SELECT 1 FROM customers c WHERE c.id::text=p.payload->>'customer_id') AS customer_exists
        FROM bases b LEFT JOIN profiles p ON p.base_source=b.source AND p.base_id=b.id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS owner_count,BOOL_AND(EXISTS(SELECT 1 FROM users u
                WHERE u.salesperson_id=a.salesperson_id AND u.is_active::text IN ('1','true','t')
                AND u.role IN ('visitor','salesperson'))) AS owner_active
            FROM base_portfolio_assignments a
            WHERE a.base_source=b.source AND a.base_id=b.id AND a.ended_at IS NULL
        ) a ON TRUE ORDER BY b.name,b.source,b.id''')).mappings().all()
    return summarize(rows)
