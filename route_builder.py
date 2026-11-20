"""مسیرساز ویزیت (Route Builder): مدیریت فهرست پزشکان و پیشنهاد دسته‌بندی مسیر.
پیشنهادهای مسیر فقط ساختاری هستند و در دیتابیس ذخیره نمی‌شوند (proposals only)."""
import json
import os
import re
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from operations import current_user, role_has_module_permission

router = APIRouter(prefix='/route-builder', tags=['route_builder'])

PHYSICIANS_JSONL = Path(os.getenv('KIARAD_PHYSICIANS_JSONL',
    str(Path(__file__).resolve().parent / 'private_exports' / 'physicians_kerman_raw.jsonl')))
PHYSICIAN_LEVELS = {'عمومی', 'متخصص', 'فوق‌تخصص', 'فلوشیپ', 'دندانپزشک'}
# بزرگ‌ترین بستهٔ هر مسیر بر پایهٔ نوع منبع (پایگاه‌ها بیشتر جمع می‌شوند تا پزشکان)
BASES_PER_ROUTE_DEFAULT = 10
PHYSICIANS_PER_ROUTE_DEFAULT = 6
SPREAD_BUCKET = 'پراکنده'  # عناوینی که از روی آدرس، محله‌شان مشخص نیست
SESSIONS = ('morning', 'evening')
SESSION_LABELS = {'morning': 'صبح', 'evening': 'عصر'}
# واژه‌های نشانهٔ محله در انتهای آدرس‌های ایران‌زمین
_AREA_KEYWORDS = 'خیابان|بلوار|فلکه|میدان|بازار'
_AREA_PATTERN = re.compile(rf'({_AREA_KEYWORDS})\s*([^\s،\-()]+)')


def ensure(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS physicians(
        id SERIAL PRIMARY KEY,name TEXT NOT NULL,level TEXT,specialty TEXT,city TEXT,area TEXT,
        address TEXT,phone TEXT,source TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_physicians_name_city ON physicians(name, (COALESCE(city, '')))"))
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_physicians_city ON physicians(city)'))

@router.on_event('startup')
def startup():
    with engine.begin() as conn:


def _manager(user):
    """دسترسی مدیر: مدیرعامل، یا نقشی که روی ماژول manager دسترسی نوشتن دارد."""
    if not user or not user.get('id'):
        raise HTTPException(403, 'دسترسی مدیر لازم است.')
    if user.get('role') == 'ceo' or role_has_module_permission(user['role'], 'manager', 'can_write'):
        return user
    raise HTTPException(403, 'این عملیات فقط با دسترسی مدیر مجاز است.')


# ---------------------------------------------------------------------------
# توابع خالص (pure) — قابل تست بدون دیتابیس
# ---------------------------------------------------------------------------

def _to_persian_digits(number: int) -> str:
    return str(number).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


_CITY_CHAR_MAP = str.maketrans({
    'ي': 'ی', 'ك': 'ک', 'ۀ': 'ه', '\u200c': ' ',  # عربی→فارسی، نیم‌فاصله→فاصله
})


def normalize_city(city: str | None) -> str:
    """نرمال‌سازی نام شهر: حذف فاصله‌های اضافه، یکسان‌سازی ی/ک عربی و نیم‌فاصله."""
    cleaned = ' '.join(str(city or '').strip().translate(_CITY_CHAR_MAP).split())
    return cleaned or 'نامشخص'


def extract_area(address: str | None) -> str | None:
    """استخراج نشانهٔ محله از انتهای آدرس: خیابان/بلوار/فلکه/میدان/بازار + واژه‌های بعدی."""
    if not address:
        return None
    # از انتهای آدرس جلو می‌رویم تا آخرین اشاره به محله را بگیریم
    best = None
    for match in _AREA_PATTERN.finditer(address):
        candidate = match.group(1) + ' ' + match.group(2)
        best = candidate.strip()
    return best or None


def chunk_routes(items: list, per_route: int) -> list[list]:
    """تقسیم فهرست به دسته‌های هم‌اندازه (آخری می‌تواند کوچک‌تر باشد)."""
    per_route = max(1, int(per_route))
    return [items[i:i + per_route] for i in range(0, len(items), per_route)]


def build_proposal(rows: list[dict], kind: str, per_route: int, session: str, city: Optional[str] = None) -> dict:
    """دسته‌بندی پیشنهادی بر پایهٔ شهر و سپس محله؛ خروجی فقط ساختاری و بدون ذخیره است."""
    if city:
        wanted = normalize_city(city)
        rows = [r for r in rows if normalize_city(r.get('city')) == wanted]
    by_city: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        city_name = normalize_city(row.get('city'))
        area = extract_area(row.get('address')) or SPREAD_BUCKET
        by_city.setdefault(city_name, {}).setdefault(area, []).append(row)

    cities = []
    flat_routes = []
    total_routes = 0
    for city_name in sorted(by_city):
        areas = by_city[city_name]
        # اگر هیچ عضو این شهر آدرس قابل‌تحلیل ندارد، گروه‌بندی فقط شهری است
        # (یک مسیر «همان شهر» به‌جای ریزشدن در «پراکنده»).
        city_has_area = any(a != SPREAD_BUCKET for a in areas)
        if not city_has_area:
            areas = {f'شهر {city_name}': [m for members in areas.values() for m in members]}
        routes = []
        for area_name in sorted(areas, key=lambda a: (a.startswith('شهر '), a)):
            for chunk in chunk_routes(areas[area_name], per_route):
                routes.append({'title': chunk[0].get('name'), 'area': area_name, 'members': chunk})
        numbered = []
        for idx, route in enumerate(routes, start=1):
            entry = {
                'route': f'مسیر {_to_persian_digits(idx)}',
                'session': SESSION_LABELS.get(session, session),
                'city': city_name,
                'area': route['area'],
                'first_stop': route['title'],
                # نام همهٔ اعضای مسیر + آدرس (برای نمایش در پنل)
                'stops': [m.get('name') for m in route['members']],
                'members': [{'name': m.get('name'), 'address': m.get('address'),
                             'phone': m.get('phone')} for m in route['members']],
            }
            numbered.append(entry)
            flat_routes.append(entry)
        total_routes += len(numbered)
        cities.append({
            'city': city_name,
            'routes': numbered,
            'route_count': len(numbered),
            'item_count': sum(len(a) for a in areas.values()),
        })
    return {
        'kind': kind,
        'session': session,
        'per_route': per_route,
        'city_filter': city,
        'total_items': sum(len(a) for areas in by_city.values() for a in areas.values()),
        'total_routes': total_routes,
        'summary': {'cities': len(cities), 'routes': total_routes},
        'cities': cities,
        # فهرست تخت همهٔ مسیرها برای ساده‌تر بودن مصرف در فرانت
        'routes': flat_routes,
    }


# ---------------------------------------------------------------------------
# CRUD پزشکان
# ---------------------------------------------------------------------------

def _physician_row(row) -> dict:
    return {'id': row['id'], 'name': row['name'], 'level': row['level'], 'specialty': row['specialty'],
            'city': row['city'], 'area': row['area'], 'address': row['address'], 'phone': row['phone'],
            'source': row['source'], 'created_at': row['created_at'].isoformat() if row['created_at'] else None}


@router.get('/physicians')
def list_physicians(level: str | None = None, city: str | None = None, q: str | None = None,
                    limit: int = 200, user: dict = Depends(current_user)):
    _manager(user)
    limit = max(1, min(limit, 200))
    query = 'SELECT * FROM physicians WHERE 1=1'
    params: dict = {}
    if level:
        query += ' AND level = :level'
        params['level'] = level
    if city:
        query += ' AND city = :city'
        params['city'] = city
    if q:
        query += ' AND (name ILIKE :q OR specialty ILIKE :q OR address ILIKE :q)'
        params['q'] = f'%{q}%'
    query += ' ORDER BY city, name LIMIT :limit'
    params['limit'] = limit
    with engine.connect() as conn:
        ensure(conn)
        rows = conn.execute(text(query), params).mappings().all()
    return {'items': [_physician_row(r) for r in rows], 'count': len(rows)}


class PhysicianCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2, max_length=200)
    level: Literal['عمومی', 'متخصص', 'فوق‌تخصص', 'فلوشیپ', 'دندانپزشک']
    specialty: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=100)
    area: str | None = Field(default=None, max_length=200)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=40)
    source: str | None = Field(default=None, max_length=60)


@router.post('/physicians')
def create_physician(data: PhysicianCreate, user: dict = Depends(current_user)):
    _manager(user)
    with engine.begin() as conn:
        ensure(conn)
        new_id = conn.execute(text('''INSERT INTO physicians(name, level, specialty, city, area, address, phone, source)
            VALUES(:name, :level, :specialty, :city, :area, :address, :phone, COALESCE(:source, 'manual'))
            RETURNING id'''), data.model_dump()).scalar_one()
    return {'id': new_id}


@router.delete('/physicians/{physician_id}')
def delete_physician(physician_id: int, user: dict = Depends(current_user)):
    _manager(user)
    with engine.begin() as conn:
        ensure(conn)
        deleted = conn.execute(text('DELETE FROM physicians WHERE id=:id'), {'id': physician_id}).rowcount
    if not deleted:
        raise HTTPException(404, 'پزشک یافت نشد.')
    return {'deleted': deleted}


@router.post('/physicians/import-jsonl')
def import_physicians_jsonl(user: dict = Depends(current_user)):
    """درون‌ریزی فایل JSONL پزشکان (اگر موجود باشد)؛ upsert بر اساس name+city."""
    _manager(user)
    if not PHYSICIANS_JSONL.exists():
        return {'imported': False, 'reason': f'فایل یافت نشد: {PHYSICIANS_JSONL}', 'inserted': 0, 'updated': 0, 'skipped': 0}
    inserted = updated = skipped = 0
    with engine.begin() as conn:
        ensure(conn)
        with PHYSICIANS_JSONL.open('r', encoding='utf-8') as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                name = (item.get('name') or '').strip()
                if not name:
                    skipped += 1
                    continue
                level = (item.get('level') or '').strip()
                city = (item.get('city') or '').strip() or None
                result = conn.execute(text('''INSERT INTO physicians(name, level, specialty, city, area, address, phone, source)
                    VALUES(:name, :level, :specialty, :city, :area, :address, :phone, COALESCE(:source, 'jsonl'))
                    ON CONFLICT(name, (COALESCE(city, ''))) DO UPDATE SET
                        level=EXCLUDED.level, specialty=EXCLUDED.specialty, address=EXCLUDED.address,
                        phone=EXCLUDED.phone, source=EXCLUDED.source
                    RETURNING (xmax = 0) AS inserted'''),
                    {'name': name, 'level': level if level in PHYSICIAN_LEVELS else None,
                     'specialty': item.get('specialty'), 'city': city,
                     'area': extract_area(item.get('address')), 'address': item.get('address'),
                     'phone': item.get('phone'), 'source': item.get('source')}).scalar()
                if result:
                    inserted += 1
                else:
                    updated += 1
    return {'imported': True, 'inserted': inserted, 'updated': updated, 'skipped': skipped}


# ---------------------------------------------------------------------------
# پیشنهاد مسیر
# ---------------------------------------------------------------------------

class SuggestRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['bases', 'physicians']
    per_route: int | None = Field(default=None, ge=1, le=30)
    city: str | None = Field(default=None, max_length=100)
    session: Literal['morning', 'evening'] = 'morning'


@router.post('/suggest')
def suggest_routes(data: SuggestRequest, user: dict = Depends(current_user)):
    """پیشنهاد دسته‌بندی مسیر بر پایهٔ شهر و محله؛ فقط پیشنهاد است و چیزی ذخیره نمی‌شود."""
    _manager(user)
    per_route = data.per_route or (BASES_PER_ROUTE_DEFAULT if data.kind == 'bases' else PHYSICIANS_PER_ROUTE_DEFAULT)
    if data.kind == 'bases':
        with engine.connect() as conn:
            rows = conn.execute(text('''SELECT name, city, address, phone FROM kerman_bases_manual
                WHERE (:city IS NULL OR city = :city) ORDER BY city, name'''),
                {'city': data.city}).mappings().all()
    else:
        with engine.connect() as conn:
            rows = conn.execute(text('''SELECT name, city, address, phone FROM physicians
                WHERE (:city IS NULL OR city = :city) ORDER BY city, name'''),
                {'city': data.city}).mappings().all()
    proposal = build_proposal([dict(r) for r in rows], data.kind, per_route, data.session, data.city)
    return proposal
