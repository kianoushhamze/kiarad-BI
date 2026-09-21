from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
try:
    from db import Base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base
    Base = declarative_base()

class TargetType(str, enum.Enum):
    BRAND = "brand"
    PRODUCT = "product"

class SalespersonContract(Base):
    __tablename__ = "salesperson_contracts"

    id = Column(Integer, primary_key=True, index=True)
    salesperson_id = Column(Integer, ForeignKey("salespersons.id"), unique=True, nullable=False)
    hourly_rate = Column(Float, default=0.0)
    min_monthly_hours = Column(Float, default=176.0)
    settlement_commission_percent = Column(Float, default=0.0)
    daily_mission_allowance = Column(Float, default=0.0)
    per_km_rate = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    targets = relationship("SalespersonTarget", back_populates="contract", cascade="all, delete-orphan")

class SalespersonTarget(Base):
    __tablename__ = "salesperson_targets"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("salesperson_contracts.id"), nullable=False)
    target_type = Column(Enum(TargetType), default=TargetType.BRAND)
    item_identifier = Column(String(100), nullable=False)
    item_title = Column(String(200), nullable=False)
    target_amount = Column(Float, default=0.0)
    target_quantity = Column(Integer, default=0)
    commission_percent = Column(Float, default=0.0)
    
    contract = relationship("SalespersonContract", back_populates="targets")

class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(Integer, primary_key=True, index=True)
    salesperson_id = Column(Integer, ForeignKey("salespersons.id"), nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    start_lat = Column(Float, nullable=True)
    start_lng = Column(Float, nullable=True)
    end_lat = Column(Float, nullable=True)
    end_lng = Column(Float, nullable=True)
    duration_hours = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

class VisitorMission(Base):
    __tablename__ = "visitor_missions"

    id = Column(Integer, primary_key=True, index=True)
    salesperson_id = Column(Integer, ForeignKey("salespersons.id"), nullable=False)
    destination_city = Column(String(100), nullable=False)
    mission_date = Column(DateTime, default=datetime.utcnow)
    distance_km = Column(Float, default=0.0)
    days_count = Column(Integer, default=1)
    approved = Column(Boolean, default=True)
