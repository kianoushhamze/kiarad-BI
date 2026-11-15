"""Available stock uses both internal and platform reservation ledgers."""
from sqlalchemy import bindparam, inspect, text


def lock_products(conn, *, product_ids=None, codes=None):
    """Every multi-product writer acquires product rows in database ID order."""
    keys = product_ids if product_ids is not None else codes
    if not keys:
        return
    column = 'id' if product_ids is not None else 'code'
    statement = text(f'SELECT id FROM products WHERE {column} IN :keys ORDER BY id FOR UPDATE')
    conn.execute(statement.bindparams(bindparam('keys', expanding=True)), {'keys': list(set(keys))}).all()


def reservation_totals(conn, product_ids=None):
    if product_ids is not None and not product_ids:
        return {}
    inspector = inspect(conn)
    sources = []
    if inspector.has_table('inventory_reservations'):
        sources.append("""SELECT product_id,
            CASE WHEN quantity > 0 THEN quantity ELSE 0 END AS quantity
            FROM inventory_reservations WHERE status='reserved'""")
    if inspector.has_table('platform_reservations'):
        sources.append("""SELECT p.id AS product_id,
            CASE WHEN r.qty > 0 THEN r.qty ELSE 0 END AS quantity
            FROM platform_reservations r JOIN products p ON p.code=r.code
            WHERE r.status='active'""")
    if not sources:
        return {}
    query = 'SELECT product_id, SUM(quantity) AS quantity FROM (' + ' UNION ALL '.join(sources) + ') reservations'
    params = {}
    if product_ids is not None:
        query += ' WHERE product_id IN :ids'
        params['ids'] = list(product_ids)
    query += ' GROUP BY product_id'
    statement = text(query)
    if product_ids is not None:
        statement = statement.bindparams(bindparam('ids', expanding=True))
    return {int(r['product_id']): float(r['quantity'] or 0) for r in conn.execute(statement, params).mappings()}


def reserved_quantity(conn, product_id):
    return reservation_totals(conn, [product_id]).get(int(product_id), 0.0)
