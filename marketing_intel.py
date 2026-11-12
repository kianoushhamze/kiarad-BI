"""Marketing & brand intelligence module (/marketing).

Data honesty policy:
- kerman_sales_pct comes ONLY from the real internal sales tables
  (sales + sale_items filled by holoo_operational_sync). If those tables are
  empty the response says so — percentages are never fabricated.
- web_signal comes from DuckDuckGo searches (rate-limit-safe, bounded).
- Generated content requires assistant_engine.call_gpt (AvalAI). Without a
  reachable provider the endpoint returns an explicit 503, never fake text.
"""
import json
import logging
import os
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from db import engine
from operations import current_user, role_has_module_permission

logger = logging.getLogger("kiarad_marketing_intel")
router = APIRouter(prefix="/marketing", tags=["marketing_intel"])

MAX_HARVEST_SEARCHES = 6
MAX_DEMAND_SEARCHES = 5
SEARCH_SLEEP_SECONDS = 6
SALES_WINDOW_DAYS = 120
DEMAND_TOP_PRODUCTS = 40

HARVEST_QUERIES = [
    "مشکل پوست صورت",
    "ریزش مو راه حل",
    "بهترین شامپو ضد شوره",
    "مراقبت از پوست صورت روزانه",
    "موخوره درمان",
    "بهترین کرم مرطوب کننده",
]

TOPIC_RULES = [
    ("مو", ("مو", "شامپو", "ریزش", "شوره", "موخوره", "روغن آرگان", "کراتین")),
    ("پوست", ("پوست", "جوش", "آکنه", "کرم", "مرطوب", "ضد آفتاب", "لک", "چین و چروک")),
    ("محصولات", ("محصول", "کیاراد", "برند", "قیمت", "خرید")),
]


def ensure(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS market_questions(
        id SERIAL PRIMARY KEY, asked_on DATE NOT NULL DEFAULT CURRENT_DATE,
        topic TEXT NOT NULL DEFAULT 'عمومی', question TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'web', signal_score INT NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_market_questions_q ON market_questions(lower(question))"))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS market_demand(
        code TEXT PRIMARY KEY, category TEXT, kerman_sales_pct NUMERIC(6,2),
        web_signal INT NOT NULL DEFAULT 0, sales_source TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS marketing_content(
        id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
        based_on JSONB NOT NULL DEFAULT '{}'::jsonb, status TEXT NOT NULL DEFAULT 'draft')"""))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS marketing_leads(
        id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        source TEXT NOT NULL DEFAULT 'manual', name TEXT NOT NULL, city TEXT,
        phone TEXT, address TEXT, detail JSONB NOT NULL DEFAULT '{}'::jsonb,
        status TEXT NOT NULL DEFAULT 'new')"""))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_marketing_leads_name_city ON marketing_leads(name, (COALESCE(city, '')))"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_marketing_leads_source ON marketing_leads(source)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_marketing_leads_city ON marketing_leads(city)"))


# ----------------------------------------------------------------- leads (لید مشتری)

PRIVATE_EXPORTS = Path(os.getenv('KIARAD_PRIVATE_EXPORTS',
    str(Path(__file__).resolve().parent / 'private_exports')))
# فایل‌های استخراج‌شدهٔ موجود که به‌عنوان لید وارد می‌شوند (کلید یکتا: name+city)
LEAD_IMPORT_FILES = [
    ("shops", PRIVATE_EXPORTS / "shops_kerman_raw.jsonl"),
    ("physicians", PRIVATE_EXPORTS / "physicians_kerman_raw.jsonl"),
]


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    city: str | None = None
    phone: str | None = None
    address: str | None = None
    source: str | None = None
    detail: dict | None = None
    status: str | None = None


def lead_records_from_file(path: Path, source: str) -> list[dict]:
    """خواندن فایل JSONL استخراج‌شده و تبدیل هر رکورد به یک لید."""
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            kind = str(item.get("kind") or item.get("type") or item.get("level") or "").strip()
            detail = {k: v for k, v in item.items()
                      if k not in ("name", "city", "phone", "address") and v not in (None, "")}
            records.append({
                "source": f"{source}:{kind}" if kind else source,
                "name": name,
                "city": (str(item.get("city") or "").strip() or None),
                "phone": (str(item.get("phone") or "").strip() or None),
                "address": (str(item.get("address") or "").strip() or None),
                "detail": json.dumps(detail, ensure_ascii=False),
            })
    return records


def _require_manager(user):
    """Same gate as /platforms and /social-connect: ceo or online-sales manager."""
    if user.get("role") != "ceo" and not role_has_module_permission(str(user.get("role", "")), "online-sales", "can_write"):
        raise HTTPException(403, "این عملیات فقط برای مدیر فروش آنلاین است.")


# ------------------------------------------------------------- pure helpers

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[؟?!.،,;:«»\"'\u200c]+")


def normalize_question(raw: str) -> str:
    """Whitespace/punctuation-insensitive form used for dedup."""
    return _PUNCT_RE.sub(" ", _WS_RE.sub(" ", str(raw or "").strip())).strip().lower()


def dedup_questions(candidates: list[str], existing: list[str]) -> list[str]:
    """Return candidates whose normalized form is not already present or
    duplicated inside the candidate list itself (order preserved)."""
    seen = {normalize_question(q) for q in existing}
    seen.discard("")
    out = []
    for cand in candidates:
        key = normalize_question(cand)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(cand.strip())
    return out


def classify_topic(raw: str) -> str:
    text_low = str(raw or "")
    for topic, keywords in TOPIC_RULES:
        if any(k in text_low for k in keywords):
            return topic
    return "عمومی"


QUESTION_MARKERS = ("؟", "?", "چیست", "چیه", "چگونه", "چطور", "چند", "کدام", "آیا", "چی ")
QUESTION_STARTERS = ("بهترین", "چرا", "راه", "درمان", "روش")


def extract_questions(titles: list[str]) -> list[str]:
    """Pick genuinely question-like titles from search results (Persian)."""
    out = []
    for raw in titles:
        value = _WS_RE.sub(" ", str(raw or "").strip())
        if not (8 <= len(value) <= 180):
            continue
        if "کیاراد" in value:
            continue
        if value.endswith(("؟", "?")) or any(m in value for m in QUESTION_MARKERS) \
                or value.startswith(QUESTION_STARTERS):
            out.append(value)
    return dedup_questions(out, [])


def compute_kerman_sales_pct(sales_counts: dict[str, float]) -> tuple[dict[str, float], float]:
    """Quantity share (%) per product code from real sales counts.
    Returns ({code: pct}, total) — empty dict when there is no data."""
    total = float(sum(sales_counts.values()))
    if total <= 0:
        return {}, 0.0
    return {code: round(100.0 * qty / total, 2) for code, qty in sales_counts.items()}, total


def demand_tier(kerman_sales_pct: float | None, web_signal: int | None) -> str:
    """Higher real Kerman sales share AND web attention → bigger opportunity."""
    pct = float(kerman_sales_pct or 0)
    sig = int(web_signal or 0)
    if pct >= 2.0 or (pct >= 0.5 and sig >= 3):
        return "فرصت فروش بیشتر"
    return "فرصت فروش کمتر"


def web_signal_score(hit_count: int) -> int:
    """Bounded 0-10 attention score from the number of search hits seen."""
    return max(0, min(10, int(hit_count)))


# ------------------------------------------------------------- web harvest

def _ddg_text(query: str, max_results: int = 10) -> list[dict]:
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        return list(ddgs.text(keywords=query, max_results=max_results))


@router.post("/harvest-questions")
def harvest_questions(user: dict = Depends(current_user)):
    _require_manager(user)
    inserted, extracted, ratelimited, searched = 0, 0, 0, 0
    candidates: list[str] = []
    for query in HARVEST_QUERIES[:MAX_HARVEST_SEARCHES]:
        searched += 1
        try:
            hits = _ddg_text(query, max_results=10)
        except Exception as exc:
            name = type(exc).__name__
            if "Ratelimit" in name or "rate" in str(exc).lower():
                ratelimited += 1
                logger.warning("harvest rate-limited on %s", query)
                time.sleep(SEARCH_SLEEP_SECONDS * 3)
            else:
                logger.warning("harvest search failed on %s: %s", query, name)
            continue
        time.sleep(SEARCH_SLEEP_SECONDS)
        titles = [h.get("title") or "" for h in hits]
        found = extract_questions(titles)
        extracted += len(found)
        candidates.extend(found)
    if candidates:
        with engine.begin() as conn:
            ensure(conn)
            existing = [r[0] for r in conn.execute(text(
                "SELECT question FROM market_questions ORDER BY id DESC LIMIT 2000")).all()]
            for q in dedup_questions(candidates, existing):
                conn.execute(text("""INSERT INTO market_questions(topic, question, source, signal_score)
                    VALUES (:t,:q,'web-ddg',1)"""), {"t": classify_topic(q), "q": q})
                inserted += 1
    return {
        "searched": searched, "search_budget": MAX_HARVEST_SEARCHES,
        "ratelimited": ratelimited, "extracted": extracted,
        "inserted": inserted,
        "honest_note": "فقط نتایج واقعی DuckDuckGo ذخیره می‌شود؛ محدودیت نرخ یا خطای شبکه باعث کمبود داده می‌شود نه صفر ساختگی.",
    }


@router.get("/questions")
def list_questions(user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.connect() as conn:
        ensure(conn)
        rows = conn.execute(text("""SELECT id, asked_on, topic, question, source, signal_score, created_at
            FROM market_questions ORDER BY created_at DESC, id DESC LIMIT 100""")).mappings().all()
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["topic"], []).append(dict(row))
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    return {"total": len(rows), "groups": [{"topic": t, "count": len(v), "items": v} for t, v in ordered]}


# ------------------------------------------------------------- demand refresh

def _kerman_sales_counts(conn) -> tuple[dict[str, float], int]:
    """Per-product sold quantity from the real internal sales data
    (holoo operational sync fills sales/sale_items)."""
    rows = conn.execute(text(f"""
        SELECT p.code AS code, COALESCE(SUM(si.quantity),0) AS qty
        FROM sale_items si
        JOIN sales s ON s.id = si.sale_id
        JOIN products p ON p.id = si.product_id
        WHERE s.date >= NOW() - INTERVAL '{SALES_WINDOW_DAYS} days'
        GROUP BY p.code""")).mappings().all()
    return {r["code"]: float(r["qty"] or 0) for r in rows}, len(rows)


@router.post("/refresh-demand")
def refresh_demand(user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        sales_counts, product_count = _kerman_sales_counts(conn)
    pcts, total_qty = compute_kerman_sales_pct(sales_counts)
    has_sales = bool(pcts)
    sales_source = "sale_items/sales (همگام هلو، ۱۲۰ روز اخیر — سهم تعدادی)" if has_sales else "فروش داخلی موجود نیست"
    if has_sales:
        ranked = sorted(pcts.items(), key=lambda kv: -kv[1])[:DEMAND_TOP_PRODUCTS]
    else:
        # No sales data: still fill web_signal for the active catalog so the
        # panel works, but the response says sales percentages are missing.
        with engine.connect() as conn:
            ensure(conn)
            ranked = [(r[0], 0.0) for r in conn.execute(text(
                "SELECT code FROM products WHERE COALESCE(is_active,1)=1 ORDER BY name LIMIT :n"),
                {"n": DEMAND_TOP_PRODUCTS}).all()]

    searched, ratelimited, web_signals = 0, 0, {}
    with engine.connect() as conn:
        ensure(conn)
        names = dict(conn.execute(text(
            "SELECT code, name FROM products WHERE code = ANY(:codes)"),
            {"codes": [c for c, _ in ranked]}).all())
    for code, _pct in ranked:
        if searched >= MAX_DEMAND_SEARCHES:
            break
        query = f"{names.get(code, code)} خرید"
        try:
            hits = _ddg_text(query, max_results=10)
        except Exception as exc:
            name = type(exc).__name__
            if "Ratelimit" in name or "rate" in str(exc).lower():
                ratelimited += 1
                time.sleep(SEARCH_SLEEP_SECONDS * 3)
            else:
                logger.warning("demand search failed %s: %s", code, name)
            continue
        searched += 1
        web_signals[code] = web_signal_score(len(hits))
        time.sleep(SEARCH_SLEEP_SECONDS)

    updated = 0
    with engine.begin() as conn:
        ensure(conn)
        for code, pct in ranked:
            category = conn.execute(text(
                "SELECT COALESCE(category,'') FROM products WHERE code=:c"), {"c": code}).scalar()
            conn.execute(text("""INSERT INTO market_demand(code, category, kerman_sales_pct, web_signal, sales_source, updated_at)
                VALUES (:c,:cat,:pct,:sig,:src,NOW())
                ON CONFLICT (code) DO UPDATE SET category=EXCLUDED.category,
                    kerman_sales_pct=EXCLUDED.kerman_sales_pct, web_signal=EXCLUDED.web_signal,
                    sales_source=EXCLUDED.sales_source, updated_at=NOW()"""),
                {"c": code, "cat": category or "", "pct": pct,
                 "sig": web_signals.get(code, 0), "src": sales_source})
            updated += 1
    return {
        "updated": updated, "sales_data_available": has_sales,
        "total_sold_quantity": total_qty, "products_with_sales": product_count,
        "web_searched": searched, "web_budget": MAX_DEMAND_SEARCHES, "ratelimited": ratelimited,
        "sales_source": sales_source,
        "honest_note": None if has_sales else
            "دادهٔ فروش داخلی در دسترس نیست؛ درصد فروش صفر ثبت شد و فقط سیگنال وب پر شد.",
    }


@router.get("/demand")
def list_demand(user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.connect() as conn:
        ensure(conn)
        rows = conn.execute(text("""SELECT d.code, d.category, d.kerman_sales_pct, d.web_signal,
                d.sales_source, d.updated_at, COALESCE(p.name, d.code) AS product_name
            FROM market_demand d LEFT JOIN products p ON p.code = d.code
            ORDER BY d.kerman_sales_pct DESC NULLS LAST, d.web_signal DESC
            LIMIT 100""")).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        item["tier"] = demand_tier(row["kerman_sales_pct"], row["web_signal"])
        items.append(item)
    return {"items": items}


# ------------------------------------------------------------- content generation

def _fmt_pct(value) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "0.0"


@router.post("/generate-content")
def generate_content(user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.connect() as conn:
        ensure(conn)
        demand = conn.execute(text("""SELECT d.kerman_sales_pct, d.web_signal, d.code,
                COALESCE(p.name, d.code) AS product_name
            FROM market_demand d LEFT JOIN products p ON p.code=d.code
            ORDER BY d.kerman_sales_pct DESC NULLS LAST, d.web_signal DESC LIMIT 5""")).mappings().all()
        questions = conn.execute(text(
            "SELECT question, topic FROM market_questions ORDER BY signal_score DESC, created_at DESC LIMIT 8")).mappings().all()
    if not demand and not questions:
        raise HTTPException(409, "هنوز دادهٔ تقاضا یا سؤالاتی ثبت نشده؛ ابتدا «بررسی تقاضا» یا «برداشت سؤالات» را اجرا کنید.")

    demand_lines = [f"- {_fmt_pct(d['kerman_sales_pct'])}٪ از فروش داخلی کرمان: {d['product_name']} (کد {d['code']})، سیگنال وب {d['web_signal']}" for d in demand]
    question_lines = [f"- [{q['topic']}] {q['question']}" for q in questions]
    prompt = (
        "تو مشاور مارکتینگ و برندینگ شرکت پخش کیاراد شفا اندیش در کرمان هستی. فقط بر اساس اعداد واقعی زیر محتوا بساز؛ "
        "عدد یا محصول دیگری ادعا نکن و اعداد را دقیقاً همین‌ها نقل کن.\n\n"
        "تقاضای محصولات (سهم درصدی از فروش داخلی کرمان ۱۲۰ روز اخیر + سیگنال وب):\n" + "\n".join(demand_lines) + "\n\n"
        "سؤالات پرتکرار کاربران وب:\n" + "\n".join(question_lines) + "\n\n"
        "خروجی را دقیقاً با این سه بخش و عناوین انگلیسی ساده بنویس:\n"
        "POST: یک پست اینستاگرام فارسی با کپشن، شامل حداقل یک عدد واقعی از جدول بالا.\n"
        "STORY: یک ایده استوری اینستاگرام (تصویر + متن کوتاه) مرتبط با یکی از سؤالات پرتکرار.\n"
        "SEO: طرح‌وارهٔ مقالهٔ سئو فارسی (H1، سه H2، نکات کلیدی) بر پایهٔ همان سؤالات و محصولات."
    )
    from assistant_engine import build_live_context, call_gpt
    with engine.connect() as conn:
        ctx = build_live_context(conn, user)
    answer = call_gpt(prompt, ctx, [], "ceo", str(user.get("full_name") or "مدیرعامل"))
    if not answer:
        raise HTTPException(503, "سرویس هوش مصنوعی در دسترس نیست (AvalAI/شبکه)؛ بدون پاسخ واقعی محتوایی ساخته نمی‌شود.")

    sections = {"post": [], "story": [], "seo": []}
    current = None
    for line in str(answer).splitlines():
        stripped = line.strip()
        head = stripped[:6].lower()
        if head.startswith("post:"):
            current = "post"
            stripped = stripped[5:].strip()
        elif head.startswith("story:"):
            current = "story"
            stripped = stripped[6:].strip()
        elif head.startswith("seo:"):
            current = "seo"
            stripped = stripped[4:].strip()
        if current and stripped:
            sections[current].append(stripped)
    bases = {
        "post": {"demand": [dict(d) for d in demand[:3]]},
        "story": {"questions": [dict(q) for q in questions[:3]]},
        "seo": {"demand": [dict(d) for d in demand[:3]], "questions": [dict(q) for q in questions[:3]]},
    }
    defaults = {
        "post": ("پست اینستاگرام مارکتینگ", "پست"),
        "story": ("ایدهٔ استوری مارکتینگ", "story"),
        "seo": ("طرح مقالهٔ سئو", "seo"),
    }
    saved = []
    with engine.begin() as conn:
        ensure(conn)
        for key in ("post", "story", "seo"):
            lines = sections[key]
            if key == "post":
                title = (lines[0] if lines else "")[:180] or "پست اینستاگرام مارکتینگ"
                body = "\n".join(lines[1:]) if len(lines) > 1 else "\n".join(lines)
            else:
                title = (lines[0] if lines else "")[:180] or defaults[key][0]
                body = "\n".join(lines[1:]) if len(lines) > 1 else "\n".join(lines)
            if not body.strip():
                body = title
            row = conn.execute(text("""INSERT INTO marketing_content(kind, title, body, based_on, status)
                VALUES (:k,:t,:b,CAST(:bo AS JSONB),'draft') RETURNING id"""),
                {"k": defaults[key][1], "t": title[:190], "b": body, "bo": json.dumps(bases[key], ensure_ascii=False)}).scalar()
            saved.append({"id": int(row), "kind": defaults[key][1], "title": title[:190]})
    return {"saved": saved, "used_demand": len(demand), "used_questions": len(questions)}


@router.get("/content")
def list_content(kind: str | None = None, user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.connect() as conn:
        ensure(conn)
        sql = text("SELECT id, created_at, kind, title, body, based_on, status FROM marketing_content "
                   "WHERE (:k IS NULL OR kind=:k) ORDER BY created_at DESC, id DESC LIMIT 100")
        rows = conn.execute(sql, {"k": kind}).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/content/{item_id}/to-calendar")
def to_calendar(item_id: int, user: dict = Depends(current_user)):
    _require_manager(user)
    from integrations import CONTENT_CHANNELS, ensure_table
    with engine.begin() as conn:
        ensure(conn)
        row = conn.execute(text("SELECT id, kind, title, body FROM marketing_content WHERE id=:i"),
                           {"i": item_id}).mappings().first()
        if not row:
            raise HTTPException(404, "پیش‌نویس مارکتینگ پیدا نشد.")
        if row["kind"] != "post":
            raise HTTPException(422, "فقط پست اینستاگرام مستقیم به تقویم محتوا می‌رود؛ استوری و سئو ابتدا باید بازبینی شوند.")
    ensure_table()
    from datetime import datetime, timedelta, timezone
    from integrations import content_calendar
    with engine.begin() as conn:
        cal_id = conn.execute(content_calendar.insert().values(
            channel="instagram", title=row["title"][:200], body=row["body"],
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
            status="pending", created_by=int(user["id"]), created_at=datetime.now(timezone.utc),
        ).returning(content_calendar.c.id)).scalar()
        conn.execute(text("UPDATE marketing_content SET status='sent_to_calendar' WHERE id=:i"), {"i": item_id})
    return {"calendar_id": int(cal_id), "channel": "instagram",
            "note": "به‌عنوان پیش‌نویس «در انتظار بازبینی» به تقویم محتوا اضافه شد؛ انتشار بیرونی دستی است."}


# ------------------------------------------------------------- leads (لید مشتری)

@router.get("/leads")
def list_leads(source: str | None = None, city: str | None = None, status: str | None = None,
               q: str | None = None, limit: int = 200, user: dict = Depends(current_user)):
    _require_manager(user)
    limit = max(1, min(limit, 500))
    query = "SELECT id, created_at, source, name, city, phone, address, detail, status FROM marketing_leads WHERE 1=1"
    params: dict = {}
    if source:
        query += " AND source LIKE :source"
        params["source"] = f"{source}%"
    if city:
        query += " AND city = :city"
        params["city"] = city
    if status:
        query += " AND status = :status"
        params["status"] = status
    if q:
        query += " AND (name ILIKE :q OR address ILIKE :q OR phone ILIKE :q)"
        params["q"] = f"%{q}%"
    query += " ORDER BY created_at DESC, id DESC LIMIT :limit"
    params["limit"] = limit
    with engine.connect() as conn:
        ensure(conn)
        rows = conn.execute(text(query), params).mappings().all()
        counts = conn.execute(text(
            "SELECT source, count(*) FROM marketing_leads GROUP BY source ORDER BY 2 DESC")).all()
    return {"items": [dict(r) for r in rows], "count": len(rows),
            "source_counts": [{"source": s, "count": n} for s, n in counts]}


@router.post("/leads")
def create_lead(data: LeadCreate, user: dict = Depends(current_user)):
    _require_manager(user)
    name = data.name.strip()
    if not name:
        raise HTTPException(422, "نام لید الزامی است.")
    with engine.begin() as conn:
        ensure(conn)
        row = conn.execute(text("""INSERT INTO marketing_leads(source, name, city, phone, address, detail, status)
            VALUES (:source, :name, :city, :phone, :address, CAST(:detail AS JSONB), COALESCE(:status, 'new'))
            ON CONFLICT (name, (COALESCE(city, ''))) DO UPDATE SET
                phone=COALESCE(EXCLUDED.phone, marketing_leads.phone),
                address=COALESCE(EXCLUDED.address, marketing_leads.address)
            RETURNING id, (xmax = 0) AS inserted"""),
            {"source": data.source or "manual", "name": name, "city": data.city, "phone": data.phone,
             "address": data.address, "detail": json.dumps(data.detail or {}, ensure_ascii=False),
             "status": data.status}).mappings().first()
    return {"id": row["id"], "created": bool(row["inserted"])}


@router.delete("/leads/{lead_id}")
def delete_lead(lead_id: int, user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        deleted = conn.execute(text("DELETE FROM marketing_leads WHERE id = :id"), {"id": lead_id}).rowcount
    if not deleted:
        raise HTTPException(404, "لید یافت نشد.")
    return {"deleted": deleted}


@router.post("/leads/import-files")
def import_leads_from_files(user: dict = Depends(current_user)):
    """واردکردن لیدها از فایل‌های استخراج‌شدهٔ موجود (داروخانه‌ها و پزشکان).
    idempotent: کلید یکتا name+city، رکورد تکراری skip می‌شود."""
    _require_manager(user)
    per_file: dict[str, dict] = {}
    with engine.begin() as conn:
        ensure(conn)
        for source, path in LEAD_IMPORT_FILES:
            records = lead_records_from_file(path, source)
            inserted = skipped = 0
            for rec in records:
                result = conn.execute(text("""INSERT INTO marketing_leads(source, name, city, phone, address, detail, status)
                    VALUES (:source, :name, :city, :phone, :address, CAST(:detail AS JSONB), 'new')
                    ON CONFLICT (name, (COALESCE(city, ''))) DO NOTHING
                    RETURNING id"""),
                    rec).scalar()
                if result:
                    inserted += 1
                else:
                    skipped += 1
            per_file[source] = {"file": path.name, "read": len(records),
                                "inserted": inserted, "skipped": skipped}
    return {"imported": True, "files": per_file}


# ------------------------------------------------- live lead discovery (لیدیابی زنده)

P24_SEARCH_URL = "https://apigw.paziresh24.com/seapi/v1/search/{city}/doctor"
MOJAVEZ_SEARCH_URL = "https://qr.mojavez.ir/api/v1/licenses/search"
_LEAD_PHONE_RE = re.compile(r"(?:034\d{8}|09\d{9}|0\d{9,10})")


class LeadDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specialty_text: str = "پوست"
    city_slug: str = "kerman"
    city_fa: str = "کرمان"
    mojavez_license_id: int | None = None
    province_id: int | None = None
    mojavez_name: str = ""
    page: int = 1
    save: bool = True


def _p24_search(text_query: str, city_slug: str, page: int = 1) -> list:
    """جست‌وجوی عمومی پزشکان در گیت‌وی پذیرش۲۴ (read-only، بدون احراز)."""
    import requests
    headers = {"User-Agent": "KiaradBI/1.0 (+lead-discovery)"}
    url = P24_SEARCH_URL.format(city=city_slug.strip() or "kerman")
    resp = requests.get(url, params={"text": text_query, "page": page}, headers=headers, timeout=20)
    resp.raise_for_status()
    return (resp.json().get("search") or {}).get("result") or []


def _p24_items_to_leads(items: list, city_fa: str) -> list[dict]:
    """تبدیل آیتم‌های پذیرش۲۴ به لید — فقط فیلدهای عمومی (نام/تخصص/آدرس مطب/تلفن)."""
    leads: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = f"{it.get('prefix') or ''} {it.get('display_name') or it.get('title') or ''}".strip()
        if not name:
            continue
        phones: list[str] = []
        for center in it.get("centers") or []:
            if not isinstance(center, dict):
                continue
            for key in ("phone", "telephone", "tel", "mobile"):
                if center.get(key):
                    phones.extend(_LEAD_PHONE_RE.findall(str(center[key])))
        rate_info = it.get("rate_info") if isinstance(it.get("rate_info"), dict) else {}
        detail = {
            "expertise": it.get("display_expertise"),
            "medical_code": it.get("medical_code"),
            "url": ("https://paziresh24.com" + str(it["url"])) if it.get("url") else None,
            "rate": rate_info.get("rate"),
        }
        detail = {k: v for k, v in detail.items() if v}
        leads.append({"source": "paziresh24", "name": name, "city": city_fa or None,
                      "phone": phones[0] if phones else None,
                      "address": it.get("display_address") or None, "detail": detail})
    return leads


def _mojavez_search(name_query: str, license_id: int, province_id: int | None, page: int = 1) -> dict:
    """جست‌وجوی صنفی در درگاه ملی مجوزها (همان APIهای JSON پشت SPA)."""
    import requests
    headers = {"User-Agent": "KiaradBI/1.0", "Content-Type": "application/json"}
    payload = {"license_id": license_id, "province_id": province_id, "name": name_query or "", "page": page}
    resp = requests.post(MOJAVEZ_SEARCH_URL, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _normalize_mojavez_items(body: dict, city_fa: str) -> list[dict]:
    """فرم پاسخ درگاه مجوزها نسخه‌ای است؛ اولین فهرست موجود در پوشه‌های شناخته‌شده خوانده می‌شود."""
    data = body.get("data") if isinstance(body, dict) else body
    candidates: list = []
    if isinstance(data, dict):
        for key in ("items", "result", "records", "licenses", "list"):
            if isinstance(data.get(key), list):
                candidates = data[key]
                break
        if not candidates and isinstance(data.get("data"), list):
            candidates = data["data"]
    elif isinstance(data, list):
        candidates = data
    leads: list[dict] = []
    for it in candidates:
        if not isinstance(it, dict):
            continue
        name = next((str(it[k]).strip() for k in ("name", "title", "owner_name", "business_name", "subject") if it.get(k)), "")
        if not name:
            continue
        phone_raw = it.get("phone") or it.get("tel") or it.get("mobile") or ""
        phones = _LEAD_PHONE_RE.findall(str(phone_raw))
        detail = {k: it[k] for k in ("license_id", "license_title", "province", "province_id", "city") if it.get(k)}
        leads.append({"source": "mojavez", "name": name,
                      "city": city_fa or it.get("city") or None,
                      "phone": phones[0] if phones else None,
                      "address": it.get("address") or None, "detail": detail})
    return leads


@router.post("/leads/discover")
def discover_leads(params: LeadDiscoveryRequest, user: dict = Depends(current_user)):
    """لیدیابی زنده از منابع عمومی: پذیرش۲۴ (پزشکان) و درگاه ملی مجوزها (اصناف).

    گوگل‌مپ/بله/تلگرام نیازمند کلید یا کراول مرورگری‌اند و عمداً اینجا نیستند.
    ذخیره idempotent است: تکراری‌ها با کلید یکتای name+city رد می‌شوند.
    """
    _require_manager(user)
    found: list[dict] = []
    notes: list[str] = []
    try:
        items = _p24_search(params.specialty_text, params.city_slug, params.page)
        p24_leads = _p24_items_to_leads(items, params.city_fa)
        found.extend(p24_leads)
        with_addr = sum(1 for lead in p24_leads if lead["address"])
        notes.append(f"پذیرش۲۴: {len(p24_leads)} پزشک ({with_addr} با آدرس)")
    except Exception as exc:
        notes.append(f"پذیرش۲۴ در دسترس نیست: {type(exc).__name__}")
    if params.mojavez_license_id:
        try:
            body = _mojavez_search(params.mojavez_name, params.mojavez_license_id, params.province_id, params.page)
            mj_leads = _normalize_mojavez_items(body, params.city_fa)
            found.extend(mj_leads)
            notes.append(f"مجوزها: {len(mj_leads)} مورد")
        except Exception as exc:
            notes.append(f"درگاه مجوزها از این شبکه در دسترس نیست: {type(exc).__name__} (از سرور دفتر امتحان شود)")
    inserted = skipped = 0
    if params.save and found:
        with engine.begin() as conn:
            ensure(conn)
            for rec in found[:500]:
                row = conn.execute(text("""INSERT INTO marketing_leads(source, name, city, phone, address, detail, status)
                    VALUES (:source, :name, :city, :phone, :address, CAST(:detail AS JSONB), 'new')
                    ON CONFLICT (name, (COALESCE(city, ''))) DO NOTHING
                    RETURNING id"""), {
                    "source": rec["source"], "name": rec["name"], "city": rec["city"],
                    "phone": rec["phone"], "address": rec["address"],
                    "detail": json.dumps(rec["detail"] or {}, ensure_ascii=False)}).scalar()
                if row:
                    inserted += 1
                else:
                    skipped += 1
    return {"found": len(found), "inserted": inserted, "skipped": skipped,
            "notes": notes, "preview": found[:10]}
