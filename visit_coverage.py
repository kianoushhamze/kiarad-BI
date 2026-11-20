"""Explicit base ownership and evidence-based fifteen-day visit coverage."""
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from db import engine
from operations import current_user, require_manager, MANAGER_ROLES

router=APIRouter(prefix='/api/compensation',tags=['visit_coverage'])


def ensure_portfolios(conn, *, temporary=False):
    conn.execute(text(f'''CREATE {'TEMP ' if temporary else ''}TABLE IF NOT EXISTS base_portfolio_assignments (
        id SERIAL PRIMARY KEY,salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
        base_source TEXT NOT NULL,base_id INTEGER NOT NULL,assigned_by INTEGER NOT NULL REFERENCES users(id),
        assigned_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'),ended_at TIMESTAMP)'''))
    conn.execute(text('''CREATE UNIQUE INDEX IF NOT EXISTS ix_active_base_portfolio
        ON base_portfolio_assignments (base_source,base_id) WHERE ended_at IS NULL'''))


class PortfolioInput(BaseModel):
    salesperson_id: int=Field(gt=0)
    source: Literal['pharmacies','cosmetics_shops','kerman_bases_manual']
    base_id: int=Field(gt=0)


@router.post('/base-portfolios')
def assign_portfolio(data: PortfolioInput,manager: dict=Depends(require_manager)):
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
                     {'key':f'portfolio:{data.source}:{data.base_id}'})
        if not conn.execute(text('SELECT id FROM salespersons WHERE id=:id'),{'id':data.salesperson_id}).first():
            raise HTTPException(404,'پروفایل پرسنل پیدا نشد')
        if not conn.execute(text(f'SELECT id FROM {data.source} WHERE id=:id'),{'id':data.base_id}).first():
            raise HTTPException(404,'پایگاه پیدا نشد')
        values={'source':data.source,'base_id':data.base_id,'sp':data.salesperson_id,'actor':manager['id']}
        previous=conn.execute(text('''SELECT id,salesperson_id FROM base_portfolio_assignments
            WHERE base_source=:source AND base_id=:base_id AND ended_at IS NULL FOR UPDATE'''),values).mappings().first()
        if previous and previous['salesperson_id']==data.salesperson_id:
            return {'id':previous['id'],'unchanged':True}
        if previous:
            conn.execute(text("UPDATE base_portfolio_assignments SET ended_at=NOW() AT TIME ZONE 'Asia/Tehran' WHERE id=:id"),{'id':previous['id']})
        identity=conn.execute(text('''INSERT INTO base_portfolio_assignments (salesperson_id,base_source,base_id,assigned_by)
            VALUES (:sp,:source,:base_id,:actor) RETURNING id'''),values).scalar()
    return {'id':identity,'unchanged':False}


def classify_visit(assigned_date,last_visit,today):
    reference=last_visit or assigned_date
    due=reference+timedelta(days=15)
    return {'last_verified_visit':last_visit,'next_due_date':due,'days_overdue':max(0,(today-due).days),
            'days_since_verified_visit':(today-last_visit).days if last_visit else None,
            'status':'overdue' if today>due else 'due_today' if today==due else 'never_visited' if last_visit is None else 'on_schedule'}


@router.get('/visit-coverage')
def coverage(salesperson_id: int|None=None,user: dict=Depends(current_user)):
    manager=user.get('role') in MANAGER_ROLES
    target=salesperson_id if manager else user.get('salesperson_id')
    if not manager and not target:
        return {'items':[],'cycle_days':15}
    where=' AND a.salesperson_id=:sp' if target is not None else ''
    with engine.connect() as conn:
        today=conn.execute(text("SELECT (NOW() AT TIME ZONE 'Asia/Tehran')::date")).scalar()
        rows=conn.execute(text('''SELECT a.id,a.salesperson_id,sp.name AS salesperson_name,
            a.base_source,a.base_id,a.assigned_at,COALESCE(p.name,c.name,m.name) AS base_name,
            COALESCE(p.city,c.city,m.city) AS city,v.last_visit,COALESCE(v.recent_count,0) AS verified_visits_15_days
            FROM base_portfolio_assignments a JOIN salespersons sp ON sp.id=a.salesperson_id
            LEFT JOIN pharmacies p ON a.base_source='pharmacies' AND p.id=a.base_id
            LEFT JOIN cosmetics_shops c ON a.base_source='cosmetics_shops' AND c.id=a.base_id
            LEFT JOIN kerman_bases_manual m ON a.base_source='kerman_bases_manual' AND m.id=a.base_id
            LEFT JOIN LATERAL (
                SELECT MAX(checked_in_at)::date AS last_visit,
                    COUNT(*) FILTER (WHERE checked_in_at::date > (NOW() AT TIME ZONE 'Asia/Tehran')::date-15) AS recent_count
                FROM base_checkins b WHERE b.salesperson_id=a.salesperson_id AND b.base_source=a.base_source
                AND b.base_id=a.base_id AND b.status='verified' AND b.checked_in_at>=a.assigned_at
                AND b.checked_in_at<=NOW() AT TIME ZONE 'Asia/Tehran'
            ) v ON TRUE WHERE a.ended_at IS NULL'''+where+' ORDER BY a.assigned_at,a.id'),{'sp':target}).mappings().all()
    items=[]
    for row in rows:
        item=dict(row)
        last=item.pop('last_visit')
        item.update(classify_visit(item['assigned_at'].date(),last,today))
        items.append(item)
    return {'items':items,'cycle_days':15,'as_of':today,'basis':'active_explicit_assignments_and_verified_checkins'}
