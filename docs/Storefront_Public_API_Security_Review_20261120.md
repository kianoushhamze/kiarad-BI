# Storefront public API and schema review — 2026-11-20

## Scope

This review covers the public storefront/catalog, customer authentication and order endpoints, public banners, marketplace feeds, and schema initialization used by those paths. It does not constitute acceptance of the company server, live ERP credentials, DNS, or production database.

## Public response contract

- `GET /public/catalog` is intentionally public. It returns product code/title/category, image URL, the final consumer-facing price in Toman, any configured customer discount, and a boolean `in_stock`.
- It no longer returns exact inventory quantities, internal product IDs, or the raw Holoo base price. The 15% consumer-price factor is applied server-side before serialization.
- Static catalog snapshots in `site/data.json` and `site/data_demo_backup.json` follow the same contract. The catalog builder writes only `consumer_price_toman` and `in_stock`.
- Torob/Emalls JSON and CSV feeds remain public by design. They publish an availability label (`instock` / `outofstock`), not the exact inventory count.
- `GET /public/catalog/prices` is no longer an anonymous endpoint. It is mapped to the `online-sales` module and requires a manager account. It returns Digikala variant prices and stock for internal use.

## Customer and order access

- `POST /site-auth/register` and `POST /site-auth/login` remain public by design.
- `GET /site-auth/me` requires a valid customer token despite being reachable through the authentication gate.
- `POST /site-orders` and `GET /site-orders/mine` require a customer token and are scoped to that customer.
- `GET /site-orders/all` and order-status changes remain manager-only.
- Customer tokens cannot be used to authenticate employee routes.

## Banner safety

- Public banner links accept only same-origin absolute paths or HTTPS URLs. Scriptable schemes, protocol-relative URLs, credentials in URLs, whitespace/control characters, and malformed URLs are rejected.
- Existing unsafe links are omitted from the public response until corrected by an administrator.
- Banner uploads are capped at 600 KiB and must have PNG, JPEG, GIF, or WebP file signatures. SVG and arbitrary binary/text payloads are rejected.
- Banner image responses set `X-Content-Type-Options: nosniff`.
- The storefront proxy now passes the public banner image route, and the browser resolves banner images through its configured API base.

## Schema lifecycle

Migration `0006_storefront_platform_storage.sql` creates the customer, order, banner, listing, platform reservation, raw platform-order, proposal, platform-order/proforma, proforma invoice, and inventory-reservation tables. It adds the order idempotency and reservation columns/index to legacy installations without deleting rows.

Request-time schema creation was removed from:
- `site_auth.py`
- `site_orders.py`
- `site_cms.py` (including banners)
- `platform_sync.py`
- public catalog/feed paths
- `scripts/build_site_catalog.py`, `scripts/derive_site_categories.py`, and `scripts/platform_stock_task.py`

Apply migrations 0005 and 0006 through the normal backup/review process before deploying this branch. Do not use a public HTTP request as a schema migration mechanism.

## Remaining deployment requirement

Application-level rate limiting is not yet implemented for public customer login/registration. Before exposing the API publicly, configure rate limits at the trusted ingress/reverse proxy for both endpoints. Only trust forwarded client-IP headers from explicitly configured proxy addresses; do not trust arbitrary client-supplied `X-Forwarded-For` values.

## Validation status

The code changes are on the draft PR branch. CI is the acceptance gate; this document does not claim production deployment or live-company verification.
