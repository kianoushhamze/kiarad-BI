# improvement.py
# ماژول بهبود مستمر - شامل تحلیل ایشیکاوا، ۵ چرا، و اقدامات اصلاحی

from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Date
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import text
from db import engine
from operations import current_user, require_manager

router = APIRouter(prefix="/improvement", tags=["improvement"])
Base = declarative_base()

# ============================================================
# مدل‌های دیتابیس (برای اضافه شدن به models.py)
# ============================================================

class Issue(Base):
    __tablename__ = "improvement_issues"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    category = Column(String(50))  # financial, sales, supply, delivery, customer, other
    severity = Column(String(20), default="medium")  # low, medium, high, critical
    status = Column(String(20), default="open")  # open, analyzing, resolved, closed
    reported_by = Column(Integer, ForeignKey("users.id"))
    assigned_to = Column(Integer, ForeignKey("users.id"))
    reported_date = Column(Date, default=date.today)
    resolved_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class FishboneCause(Base):
    __tablename__ = "improvement_fishbone_causes"

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("improvement_issues.id"), nullable=False)
    category = Column(String(50), nullable=False)  # machine, method, material, man, environment, management
    cause_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class FiveWhy(Base):
    __tablename__ = "improvement_five_whys"

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("improvement_issues.id"), nullable=False)
    level = Column(Integer, nullable=False)  # 1-5
    question = Column(String(500), nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class CorrectiveAction(Base):
    __tablename__ = "improvement_corrective_actions"

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("improvement_issues.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), default="pending")  # pending, in_progress, done, cancelled
    progress = Column(Integer, default=0)  # 0-100
    metric_target = Column(Float, nullable=True)  # هدف کمی
    metric_actual = Column(Float, nullable=True)  # مقدار فعلی
    metric_unit = Column(String(50), nullable=True)  # ریال، درصد، عدد، و غیره
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

# ============================================================
# Pydantic مدل‌های ورودی/خروجی
# ============================================================

class IssueCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: Optional[str] = None
    category: str = Field(default="other")
    severity: str = Field(default="medium")
    assigned_to: Optional[int] = None

class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[int] = None

class FishboneCauseCreate(BaseModel):
    category: str
    cause_text: str = Field(min_length=3)

class FiveWhyCreate(BaseModel):
    level: int = Field(ge=1, le=5)
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=3)

class CorrectiveActionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: Optional[str] = None
    owner_id: int
    due_date: date
    metric_target: Optional[float] = None
    metric_unit: Optional[str] = None

class CorrectiveActionUpdate(BaseModel):
    status: Optional[str] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    metric_actual: Optional[float] = None

# ============================================================
# توابع کمکی
# ============================================================

def get_user_name(user_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT full_name FROM users WHERE id=:id"),
            {"id": user_id}
        ).mappings().first()
    return row["full_name"] if row else f"user-{user_id}"

def get_issue_dict(conn, issue_id: int):
    row = conn.execute(
        text("""
            SELECT i.*, 
                   u1.full_name AS reporter_name, 
                   u2.full_name AS assignee_name
            FROM improvement_issues i
            LEFT JOIN users u1 ON u1.id = i.reported_by
            LEFT JOIN users u2 ON u2.id = i.assigned_to
            WHERE i.id = :id
        """),
        {"id": issue_id}
    ).mappings().first()
    return dict(row) if row else None

# ============================================================
# API: مسائل (Issues)
# ============================================================

@router.post("/issues", status_code=201)
def create_issue(data: IssueCreate, user: dict = Depends(current_user)):
    valid_categories = {"financial", "sales", "supply", "delivery", "customer", "other"}
    if data.category not in valid_categories:
        raise HTTPException(status_code=422, detail="دسته‌بندی نامعتبر است")
    valid_severity = {"low", "medium", "high", "critical"}
    if data.severity not in valid_severity:
        raise HTTPException(status_code=422, detail="سطح اهمیت نامعتبر است")
    
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO improvement_issues
                    (title, description, category, severity, status, reported_by, assigned_to, reported_date, created_at)
                VALUES
                    (:title, :description, :category, :severity, 'open', :reported_by, :assigned_to, :reported_date, NOW())
                RETURNING id
            """),
            {
                "title": data.title,
                "description": data.description,
                "category": data.category,
                "severity": data.severity,
                "reported_by": user["id"],
                "assigned_to": data.assigned_to,
                "reported_date": date.today(),
            }
        ).mappings().first()
        issue_id = row["id"]
    return get_issue_dict(engine.connect(), issue_id)

@router.get("/issues")
def list_issues(user: dict = Depends(current_user)):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT i.*, 
                   u1.full_name AS reporter_name, 
                   u2.full_name AS assignee_name
            FROM improvement_issues i
            LEFT JOIN users u1 ON u1.id = i.reported_by
            LEFT JOIN users u2 ON u2.id = i.assigned_to
            ORDER BY i.severity = 'critical' DESC, 
                     i.severity = 'high' DESC, 
                     i.created_at DESC
        """)).mappings().all()
    return {"count": len(rows), "issues": [dict(row) for row in rows]}

@router.get("/issues/{issue_id}")
def get_issue(issue_id: int, user: dict = Depends(current_user)):
    with engine.connect() as conn:
        issue = get_issue_dict(conn, issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        # دریافت علل ایشیکاوا
        causes = conn.execute(
            text("SELECT * FROM improvement_fishbone_causes WHERE issue_id = :id ORDER BY category"),
            {"id": issue_id}
        ).mappings().all()
        # دریافت تحلیل ۵ چرا
        whys = conn.execute(
            text("SELECT * FROM improvement_five_whys WHERE issue_id = :id ORDER BY level"),
            {"id": issue_id}
        ).mappings().all()
        # دریافت اقدامات اصلاحی
        actions = conn.execute(
            text("""
                SELECT ca.*, u.full_name AS owner_name
                FROM improvement_corrective_actions ca
                LEFT JOIN users u ON u.id = ca.owner_id
                WHERE ca.issue_id = :id
                ORDER BY ca.due_date, ca.id
            """),
            {"id": issue_id}
        ).mappings().all()
        issue["causes"] = [dict(row) for row in causes]
        issue["five_whys"] = [dict(row) for row in whys]
        issue["corrective_actions"] = [dict(row) for row in actions]
        return issue

@router.patch("/issues/{issue_id}")
def update_issue(issue_id: int, data: IssueUpdate, user: dict = Depends(current_user)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_issues WHERE id = :id"),
            {"id": issue_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        updates = []
        params = {"id": issue_id}
        if data.title is not None:
            updates.append("title = :title")
            params["title"] = data.title
        if data.description is not None:
            updates.append("description = :description")
            params["description"] = data.description
        if data.category is not None:
            updates.append("category = :category")
            params["category"] = data.category
        if data.severity is not None:
            updates.append("severity = :severity")
            params["severity"] = data.severity
        if data.status is not None:
            updates.append("status = :status")
            params["status"] = data.status
            if data.status == "resolved":
                updates.append("resolved_date = :resolved_date")
                params["resolved_date"] = date.today()
        if data.assigned_to is not None:
            updates.append("assigned_to = :assigned_to")
            params["assigned_to"] = data.assigned_to
        if updates:
            conn.execute(
                text(f"UPDATE improvement_issues SET {', '.join(updates)} WHERE id = :id"),
                params
            )
    return get_issue_dict(engine.connect(), issue_id)

@router.delete("/issues/{issue_id}")
def delete_issue(issue_id: int, _: dict = Depends(require_manager)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_issues WHERE id = :id"),
            {"id": issue_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        conn.execute(text("DELETE FROM improvement_fishbone_causes WHERE issue_id = :id"), {"id": issue_id})
        conn.execute(text("DELETE FROM improvement_five_whys WHERE issue_id = :id"), {"id": issue_id})
        conn.execute(text("DELETE FROM improvement_corrective_actions WHERE issue_id = :id"), {"id": issue_id})
        conn.execute(text("DELETE FROM improvement_issues WHERE id = :id"), {"id": issue_id})
    return {"status": "deleted", "issue_id": issue_id}

# ============================================================
# API: علل ایشیکاوا (Fishbone Causes)
# ============================================================

@router.post("/issues/{issue_id}/causes", status_code=201)
def add_fishbone_cause(issue_id: int, data: FishboneCauseCreate, user: dict = Depends(current_user)):
    valid_categories = {"machine", "method", "material", "man", "environment", "management"}
    if data.category not in valid_categories:
        raise HTTPException(status_code=422, detail="دسته‌بندی ایشیکاوا نامعتبر است")
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_issues WHERE id = :id"),
            {"id": issue_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        row = conn.execute(
            text("""
                INSERT INTO improvement_fishbone_causes (issue_id, category, cause_text, created_at)
                VALUES (:issue_id, :category, :cause_text, NOW())
                RETURNING id
            """),
            {"issue_id": issue_id, "category": data.category, "cause_text": data.cause_text}
        ).mappings().first()
        cause_id = row["id"]
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM improvement_fishbone_causes WHERE id = :id"),
            {"id": cause_id}
        ).mappings().first()
    return dict(result)

@router.get("/issues/{issue_id}/fishbone")
def get_fishbone_analysis(issue_id: int, user: dict = Depends(current_user)):
    """گزارش تحلیل ایشیکاوا - گروه‌بندی علل بر اساس دسته‌بندی"""
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_issues WHERE id = :id"),
            {"id": issue_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        causes = conn.execute(
            text("SELECT * FROM improvement_fishbone_causes WHERE issue_id = :id ORDER BY category"),
            {"id": issue_id}
        ).mappings().all()
    # گروه‌بندی بر اساس دسته‌بندی
    categories = ["machine", "method", "material", "man", "environment", "management"]
    grouped = {}
    for cat in categories:
        grouped[cat] = []
    for cause in causes:
        grouped[cause["category"]].append(dict(cause))
    return {"issue_id": issue_id, "fishbone": grouped}

# ============================================================
# API: تحلیل ۵ چرا (Five Whys)
# ============================================================

@router.post("/issues/{issue_id}/five-whys", status_code=201)
def add_five_why(issue_id: int, data: FiveWhyCreate, user: dict = Depends(current_user)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_issues WHERE id = :id"),
            {"id": issue_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        # چک کردن اینکه سطح تکراری نباشد
        duplicate = conn.execute(
            text("SELECT id FROM improvement_five_whys WHERE issue_id = :id AND level = :level"),
            {"id": issue_id, "level": data.level}
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail=f"سطح {data.level} قبلاً ثبت شده است")
        row = conn.execute(
            text("""
                INSERT INTO improvement_five_whys (issue_id, level, question, answer, created_at)
                VALUES (:issue_id, :level, :question, :answer, NOW())
                RETURNING id
            """),
            {"issue_id": issue_id, "level": data.level, "question": data.question, "answer": data.answer}
        ).mappings().first()
        why_id = row["id"]
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM improvement_five_whys WHERE id = :id"),
            {"id": why_id}
        ).mappings().first()
    return dict(result)

@router.get("/issues/{issue_id}/five-whys")
def get_five_whys_analysis(issue_id: int, user: dict = Depends(current_user)):
    """گزارش کامل تحلیل ۵ چرا"""
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_issues WHERE id = :id"),
            {"id": issue_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        whys = conn.execute(
            text("SELECT * FROM improvement_five_whys WHERE issue_id = :id ORDER BY level"),
            {"id": issue_id}
        ).mappings().all()
        chain = [dict(row) for row in whys]
        return {"issue_id": issue_id, "five_whys": chain}

# ============================================================
# API: اقدامات اصلاحی (Corrective Actions)
# ============================================================

@router.post("/issues/{issue_id}/actions", status_code=201)
def create_corrective_action(issue_id: int, data: CorrectiveActionCreate, user: dict = Depends(current_user)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_issues WHERE id = :id"),
            {"id": issue_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        # بررسی وجود owner
        owner = conn.execute(
            text("SELECT id FROM users WHERE id = :id AND is_active = 1"),
            {"id": data.owner_id}
        ).first()
        if not owner:
            raise HTTPException(status_code=404, detail="مالک (owner) پیدا نشد")
        row = conn.execute(
            text("""
                INSERT INTO improvement_corrective_actions
                    (issue_id, title, description, owner_id, due_date, status, progress, metric_target, metric_unit, created_at)
                VALUES
                    (:issue_id, :title, :description, :owner_id, :due_date, 'pending', 0, :metric_target, :metric_unit, NOW())
                RETURNING id
            """),
            {
                "issue_id": issue_id,
                "title": data.title,
                "description": data.description,
                "owner_id": data.owner_id,
                "due_date": data.due_date,
                "metric_target": data.metric_target,
                "metric_unit": data.metric_unit,
            }
        ).mappings().first()
        action_id = row["id"]
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT ca.*, u.full_name AS owner_name
                FROM improvement_corrective_actions ca
                LEFT JOIN users u ON u.id = ca.owner_id
                WHERE ca.id = :id
            """),
            {"id": action_id}
        ).mappings().first()
    return dict(result)

@router.get("/issues/{issue_id}/actions")
def list_corrective_actions(issue_id: int, user: dict = Depends(current_user)):
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_issues WHERE id = :id"),
            {"id": issue_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="مسئله پیدا نشد")
        rows = conn.execute(
            text("""
                SELECT ca.*, u.full_name AS owner_name
                FROM improvement_corrective_actions ca
                LEFT JOIN users u ON u.id = ca.owner_id
                WHERE ca.issue_id = :id
                ORDER BY ca.status = 'pending' DESC, ca.due_date, ca.id
            """),
            {"id": issue_id}
        ).mappings().all()
    return {"count": len(rows), "actions": [dict(row) for row in rows]}

@router.patch("/actions/{action_id}")
def update_corrective_action(action_id: int, data: CorrectiveActionUpdate, user: dict = Depends(current_user)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_corrective_actions WHERE id = :id"),
            {"id": action_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="اقدام اصلاحی پیدا نشد")
        updates = []
        params = {"id": action_id}
        if data.status is not None:
            valid_status = {"pending", "in_progress", "done", "cancelled"}
            if data.status not in valid_status:
                raise HTTPException(status_code=422, detail="وضعیت نامعتبر است")
            updates.append("status = :status")
            params["status"] = data.status
            if data.status == "done":
                updates.append("completed_at = NOW()")
                updates.append("progress = 100")
        if data.progress is not None:
            updates.append("progress = :progress")
            params["progress"] = data.progress
        if data.metric_actual is not None:
            updates.append("metric_actual = :metric_actual")
            params["metric_actual"] = data.metric_actual
        if updates:
            conn.execute(
                text(f"UPDATE improvement_corrective_actions SET {', '.join(updates)} WHERE id = :id"),
                params
            )
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT ca.*, u.full_name AS owner_name
                FROM improvement_corrective_actions ca
                LEFT JOIN users u ON u.id = ca.owner_id
                WHERE ca.id = :id
            """),
            {"id": action_id}
        ).mappings().first()
    return dict(result)

@router.delete("/actions/{action_id}")
def delete_corrective_action(action_id: int, _: dict = Depends(require_manager)):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM improvement_corrective_actions WHERE id = :id"),
            {"id": action_id}
        ).first()
        if not existing:
            raise HTTPException(status_code=404, detail="اقدام اصلاحی پیدا نشد")
        conn.execute(
            text("DELETE FROM improvement_corrective_actions WHERE id = :id"),
            {"id": action_id}
        )
    return {"status": "deleted", "action_id": action_id}

# ============================================================
# API: گزارش‌های تحلیلی
# ============================================================

@router.get("/reports/summary")
def improvement_summary(user: dict = Depends(current_user)):
    """خلاصه وضعیت بهبود مستمر"""
    with engine.connect() as conn:
        total_issues = conn.execute(text("SELECT COUNT(*) FROM improvement_issues")).scalar()
        open_issues = conn.execute(text("SELECT COUNT(*) FROM improvement_issues WHERE status IN ('open', 'analyzing')")).scalar()
        critical = conn.execute(text("SELECT COUNT(*) FROM improvement_issues WHERE severity = 'critical' AND status IN ('open', 'analyzing')")).scalar()
        pending_actions = conn.execute(text("SELECT COUNT(*) FROM improvement_corrective_actions WHERE status IN ('pending', 'in_progress')")).scalar()
        overdue_actions = conn.execute(text("SELECT COUNT(*) FROM improvement_corrective_actions WHERE due_date < NOW()::date AND status IN ('pending', 'in_progress')")).scalar()
        resolved_issues = conn.execute(text("SELECT COUNT(*) FROM improvement_issues WHERE status = 'resolved'")).scalar()
        closed_issues = conn.execute(text("SELECT COUNT(*) FROM improvement_issues WHERE status = 'closed'")).scalar()
    return {
        "total_issues": total_issues,
        "open_issues": open_issues,
        "critical_issues": critical,
        "pending_actions": pending_actions,
        "overdue_actions": overdue_actions,
        "resolved_issues": resolved_issues,
        "closed_issues": closed_issues,
    }

@router.get("/reports/issue/{issue_id}/full")
def full_improvement_report(issue_id: int, user: dict = Depends(current_user)):
    """گزارش کامل یک مسئله با همه جزئیات"""
    return get_issue(issue_id, user)