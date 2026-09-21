from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from db import get_db
from compensation_models import SalespersonContract, SalespersonTarget, AttendanceSession, VisitorMission, TargetType

try:
    from holo_api import get_sales_invoices, get_customer_settlements
except ImportError:
    def get_sales_invoices(salesperson_id, start_date, end_date):
        return []
    def get_customer_settlements(salesperson_id, start_date, end_date):
        return []

router = APIRouter(prefix="/api/compensation", tags=["Compensation"])

class TargetSchema(BaseModel):
    target_type: TargetType
    item_identifier: str
    item_title: str
    target_amount: float
    target_quantity: int
    commission_percent: float

class ContractSaveSchema(BaseModel):
    hourly_rate: float
    min_monthly_hours: float
    settlement_commission_percent: float
    daily_mission_allowance: float
    per_km_rate: float
    targets: List[TargetSchema]

class AttendanceToggleSchema(BaseModel):
    salesperson_id: int
    lat: Optional[float] = None
    lng: Optional[float] = None

@router.get("/contract/{salesperson_id}")
def get_contract(salesperson_id: int, db: Session = Depends(get_db)):
    contract = db.query(SalespersonContract).filter_by(salesperson_id=salesperson_id).first()
    if not contract:
        return {"configured": False, "salesperson_id": salesperson_id}
    return {
        "configured": True,
        "hourly_rate": contract.hourly_rate,
        "min_monthly_hours": contract.min_monthly_hours,
        "settlement_commission_percent": contract.settlement_commission_percent,
        "daily_mission_allowance": contract.daily_mission_allowance,
        "per_km_rate": contract.per_km_rate,
        "targets": [
            {
                "target_type": t.target_type,
                "item_identifier": t.item_identifier,
                "item_title": t.item_title,
                "target_amount": t.target_amount,
                "target_quantity": t.target_quantity,
                "commission_percent": t.commission_percent,
            }
            for t in contract.targets
        ]
    }

@router.post("/contract/{salesperson_id}")
def save_contract(salesperson_id: int, data: ContractSaveSchema, db: Session = Depends(get_db)):
    contract = db.query(SalespersonContract).filter_by(salesperson_id=salesperson_id).first()
    if not contract:
        contract = SalespersonContract(salesperson_id=salesperson_id)
        db.add(contract)
        db.flush()
    
    contract.hourly_rate = data.hourly_rate
    contract.min_monthly_hours = data.min_monthly_hours
    contract.settlement_commission_percent = data.settlement_commission_percent
    contract.daily_mission_allowance = data.daily_mission_allowance
    contract.per_km_rate = data.per_km_rate
    
    db.query(SalespersonTarget).filter_by(contract_id=contract.id).delete()
    for t in data.targets:
        db.add(SalespersonTarget(
            contract_id=contract.id,
            target_type=t.target_type,
            item_identifier=t.item_identifier,
            item_title=t.item_title,
            target_amount=t.target_amount,
            target_quantity=t.target_quantity,
            commission_percent=t.commission_percent
        ))
    
    db.commit()
    return {"status": "success", "message": "قرارداد ویزیتور ذخیره شد."}

@router.post("/attendance/start")
def start_attendance(data: AttendanceToggleSchema, db: Session = Depends(get_db)):
    active = db.query(AttendanceSession).filter_by(salesperson_id=data.salesperson_id, is_active=True).first()
    if active:
        return {"status": "already_active", "session_id": active.id}
    
    session = AttendanceSession(
        salesperson_id=data.salesperson_id,
        start_time=datetime.utcnow(),
        start_lat=data.lat,
        start_lng=data.lng,
        is_active=True
    )
    db.add(session)
    db.commit()
    return {"status": "started", "session_id": session.id}

@router.post("/attendance/stop")
def stop_attendance(data: AttendanceToggleSchema, db: Session = Depends(get_db)):
    session = db.query(AttendanceSession).filter_by(salesperson_id=data.salesperson_id, is_active=True).first()
    if not session:
        raise HTTPException(status_code=400, detail="نشست فعالی یافت نشد.")
    
    session.end_time = datetime.utcnow()
    session.end_lat = data.lat
    session.end_lng = data.lng
    session.is_active = False
    diff = session.end_time - session.start_time
    session.duration_hours = round(diff.total_seconds() / 3600.0, 2)
    db.commit()
    return {"status": "stopped", "duration_hours": session.duration_hours}
