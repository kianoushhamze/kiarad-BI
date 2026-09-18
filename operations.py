import hashlib
import hmac
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import engine


router = APIRouter(tags=["operations"])

JWT_SECRET = os.getenv("KIARAD_JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
TOKEN_HOURS = 12
MANAGER_ROLES = {"ceo", "sales_manager"}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def require_jwt_secret() -> str:
    if len(JWT_SECRET) < 32:
        raise HTTPException(
            status_code=503,
            detail="KIARAD_JWT_SECRET must be configured with at least 32 characters.",
        )
    return JWT_SECRET


def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "role": user["role"],
        "exp": now + timedelta(hours=TOKEN_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, require_jwt_secret(), algorithm=JWT_ALGORITHM)


def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, require_jwt_secret(), algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, username, full_name, role, salesperson_id, is_active
                FROM users WHERE id = :id
            """),
            {"id": user_id},
        ).mappings().first()
    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="User is inactive")
    return dict(row)


def require_manager(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Manager access required")
    return user


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=10, max_length=200)
    role: str
    salesperson_id: Optional[int] = None


class SalespersonCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    phone: Optional[str] = Field(default=None, max_length=30)


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: Optional[str] = None
    priority: str = "normal"
    assigned_to: int
    customer_id: Optional[int] = None
    due_date: Optional[datetime] = None


class TaskProgress(BaseModel):
    progress: int = Field(ge=0, le=100)
    status: str
    note: Optional[str] = None


class DailyReportCreate(BaseModel):
    report_date: date
    visits_count: int = Field(default=0, ge=0)
    new_customers_count: int = Field(default=0, ge=0)
    orders_count: int = Field(default=0, ge=0)
    lost_orders_count: int = Field(default=0, ge=0)
    reported_sales_amount: float = Field(default=0, ge=0)
    reported_collections_amount: float = Field(default=0, ge=0)
    loss_reasons: Optional[str] = None
    competitor_notes: Optional[str] = None
    demand_notes: Optional[str] = None
    issues: Optional[str] = None
    tomorrow_plan: Optional[str] = None
    notes: Optional[str] = None


@router.post("/auth/login")
def login(data: LoginRequest):
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, username, password_hash, full_name, role,
                       salesperson_id, is_active
                FROM users WHERE username = :username
            """),
            {"username": data.username.strip().lower()},
        ).mappings().first()
    if not row or not row["is_active"] or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user = dict(row)
    return {
        "access_token": create_token(user),
        "token_type": "bearer",
        "user": {key: user[key] for key in ("id", "username", "full_name", "role", "salesperson_id")},
    }


@router.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@router.get("/users")
def list_users(_: dict = Depends(require_manager)):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT u.id, u.username, u.full_name, u.role, u.salesperson_id,
                   u.is_active, sp.name AS salesperson_name
            FROM users u
            LEFT JOIN salespersons sp ON sp.id = u.salesperson_id
            ORDER BY u.is_active DESC, u.full_name
        """)).mappings().all()
    return {"count": len(rows), "users": [dict(row) for row in rows]}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, manager: dict = Depends(require_manager)):
    allowed_roles = {"ceo", "sales_manager", "salesperson", "finance"}
    if data.role not in allowed_roles:
        raise HTTPException(status_code=422, detail="Invalid role")
    if manager["role"] != "ceo" and data.role in {"ceo", "sales_manager", "finance"}:
        raise HTTPException(status_code=403, detail="Only CEO can create privileged users")
    if data.role == "salesperson" and not data.salesperson_id:
        raise HTTPException(status_code=422, detail="Salesperson profile is required")
    with engine.begin() as conn:
        if data.salesperson_id:
            exists = conn.execute(
                text("SELECT id FROM salespersons WHERE id=:id"),
                {"id": data.salesperson_id},
            ).first()
            if not exists:
                raise HTTPException(status_code=404, detail="Salesperson not found")
        duplicate = conn.execute(
            text("SELECT id FROM users WHERE username=:username"),
            {"username": data.username.strip().lower()},
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Username already exists")
        row = conn.execute(text("""
            INSERT INTO users
                (username, password_hash, full_name, role, salesperson_id, is_active, created_at)
            VALUES
                (:username, :password_hash, :full_name, :role, :salesperson_id, 1, NOW())
            RETURNING id, username, full_name, role, salesperson_id, is_active
        """), {
            "username": data.username.strip().lower(),
            "password_hash": hash_password(data.password),
            "full_name": data.full_name.strip(),
            "role": data.role,
            "salesperson_id": data.salesperson_id,
        }).mappings().first()
    return dict(row)


@router.get("/salespersons")
def list_salespersons(_: dict = Depends(require_manager)):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT sp.id, sp.name, sp.phone,
                   u.id AS user_id, u.username, u.is_active
            FROM salespersons sp
            LEFT JOIN users u ON u.salesperson_id = sp.id
            ORDER BY sp.name
        """)).mappings().all()
    return {"count": len(rows), "salespersons": [dict(row) for row in rows]}


@router.post("/salespersons", status_code=status.HTTP_201_CREATED)
def create_salesperson(data: SalespersonCreate, _: dict = Depends(require_manager)):
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO salespersons (name, phone)
            VALUES (:name, :phone) RETURNING *
        """), {"name": data.name.strip(), "phone": data.phone}).mappings().first()
    return dict(row)


@router.get("/visitors/overview")
def visitors_overview(user: dict = Depends(current_user)):
    params = {}
    where = ""
    if user["role"] not in MANAGER_ROLES:
        if not user["salesperson_id"]:
            return {"count": 0, "visitors": []}
        where = "WHERE sp.id=:salesperson_id"
        params["salesperson_id"] = user["salesperson_id"]
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT sp.id, sp.name, sp.phone,
                   COALESCE(s.sales_amount, 0) AS sales_amount,
                   COALESCE(s.invoice_count, 0) AS invoice_count,
                   COALESCE(t.target_amount, 0) AS target_amount,
                   COALESCE(ts.open_tasks, 0) AS open_tasks,
                   COALESCE(ts.overdue_tasks, 0) AS overdue_tasks,
                   dr.report_date AS last_report_date,
                   COALESCE(dr.visits_count, 0) AS last_visits_count,
                   COALESCE(dr.orders_count, 0) AS last_orders_count
            FROM salespersons sp
            LEFT JOIN LATERAL (
                SELECT SUM(total_amount) AS sales_amount, COUNT(*) AS invoice_count
                FROM sales WHERE salesperson_id=sp.id
            ) s ON TRUE
            LEFT JOIN LATERAL (
                SELECT target_amount FROM targets
                WHERE salesperson_id=sp.id AND status='active'
                ORDER BY start_date DESC NULLS LAST, id DESC LIMIT 1
            ) t ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) FILTER (WHERE status <> 'completed') AS open_tasks,
                       COUNT(*) FILTER (WHERE status <> 'completed' AND due_date < NOW()) AS overdue_tasks
                FROM tasks task
                JOIN users task_user ON task_user.id=task.assigned_to
                WHERE task_user.salesperson_id=sp.id
            ) ts ON TRUE
            LEFT JOIN LATERAL (
                SELECT report_date, visits_count, orders_count FROM daily_reports
                WHERE salesperson_id=sp.id ORDER BY report_date DESC LIMIT 1
            ) dr ON TRUE
            {where}
            ORDER BY sales_amount DESC, sp.name
        """), params).mappings().all()
    visitors = []
    for row in rows:
        item = dict(row)
        target = float(item["target_amount"] or 0)
        actual = float(item["sales_amount"] or 0)
        item["achievement_percent"] = round(actual / target * 100, 2) if target else 0
        item["remaining"] = max(target - actual, 0)
        item["report_submitted_today"] = item["last_report_date"] == date.today()
        visitors.append(item)
    return {"count": len(visitors), "visitors": visitors}


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, manager: dict = Depends(require_manager)):
    if data.priority not in {"low", "normal", "high", "urgent"}:
        raise HTTPException(status_code=422, detail="Invalid priority")
    with engine.begin() as conn:
        assignee = conn.execute(
            text("SELECT id FROM users WHERE id=:id AND is_active=1"),
            {"id": data.assigned_to},
        ).first()
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found")
        row = conn.execute(
            text("""
                INSERT INTO tasks
                    (title, description, priority, status, progress, assigned_to,
                     created_by, customer_id, due_date, created_at, updated_at)
                VALUES
                    (:title, :description, :priority, 'new', 0, :assigned_to,
                     :created_by, :customer_id, :due_date, NOW(), NOW())
                RETURNING *
            """),
            {**data.model_dump(), "created_by": manager["id"]},
        ).mappings().first()
    return dict(row)


@router.get("/tasks")
def list_tasks(user: dict = Depends(current_user)):
    query = """
        SELECT t.*, u.full_name AS assignee_name, c.name AS customer_name
        FROM tasks t
        JOIN users u ON u.id = t.assigned_to
        LEFT JOIN customers c ON c.id = t.customer_id
    """
    params = {}
    if user["role"] not in MANAGER_ROLES:
        query += " WHERE t.assigned_to = :user_id"
        params["user_id"] = user["id"]
    query += " ORDER BY t.due_date NULLS LAST, t.id DESC"
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return {"count": len(rows), "tasks": [dict(row) for row in rows]}


@router.patch("/tasks/{task_id}/progress")
def update_task_progress(task_id: int, data: TaskProgress, user: dict = Depends(current_user)):
    allowed_statuses = {"new", "in_progress", "completed", "blocked"}
    if data.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Invalid status")
    if data.status == "completed" and data.progress != 100:
        raise HTTPException(status_code=422, detail="Completed tasks must have 100 percent progress")
    with engine.begin() as conn:
        task = conn.execute(
            text("SELECT * FROM tasks WHERE id=:id"), {"id": task_id}
        ).mappings().first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if user["role"] not in MANAGER_ROLES and task["assigned_to"] != user["id"]:
            raise HTTPException(status_code=403, detail="Task access denied")
        row = conn.execute(
            text("""
                UPDATE tasks SET progress=:progress, status=:status, updated_at=NOW()
                WHERE id=:id RETURNING *
            """),
            {"id": task_id, "progress": data.progress, "status": data.status},
        ).mappings().first()
        conn.execute(
            text("""
                INSERT INTO task_updates (task_id, user_id, progress, status, note, created_at)
                VALUES (:task_id, :user_id, :progress, :status, :note, NOW())
            """),
            {"task_id": task_id, "user_id": user["id"], **data.model_dump()},
        )
    return dict(row)


@router.post("/daily-reports", status_code=status.HTTP_201_CREATED)
def create_daily_report(data: DailyReportCreate, user: dict = Depends(current_user)):
    if not user["salesperson_id"]:
        raise HTTPException(status_code=403, detail="Salesperson profile required")
    if data.report_date > date.today():
        raise HTTPException(status_code=422, detail="Future reports are not allowed")
    with engine.begin() as conn:
        existing = conn.execute(
            text("""
                SELECT id FROM daily_reports
                WHERE salesperson_id=:salesperson_id AND report_date=:report_date
            """),
            {"salesperson_id": user["salesperson_id"], "report_date": data.report_date},
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Daily report already exists")
        values = data.model_dump()
        values["salesperson_id"] = user["salesperson_id"]
        row = conn.execute(
            text("""
                INSERT INTO daily_reports
                    (salesperson_id, report_date, visits_count, new_customers_count,
                     orders_count, lost_orders_count, reported_sales_amount,
                     reported_collections_amount, loss_reasons, competitor_notes,
                     demand_notes, issues, tomorrow_plan, notes, created_at)
                VALUES
                    (:salesperson_id, :report_date, :visits_count, :new_customers_count,
                     :orders_count, :lost_orders_count, :reported_sales_amount,
                     :reported_collections_amount, :loss_reasons, :competitor_notes,
                     :demand_notes, :issues, :tomorrow_plan, :notes, NOW())
                RETURNING *
            """),
            values,
        ).mappings().first()
    return dict(row)


@router.get("/daily-reports")
def list_daily_reports(user: dict = Depends(current_user)):
    query = """
        SELECT dr.*, sp.name AS salesperson_name
        FROM daily_reports dr
        JOIN salespersons sp ON sp.id = dr.salesperson_id
    """
    params = {}
    if user["role"] not in MANAGER_ROLES:
        if not user["salesperson_id"]:
            return {"count": 0, "reports": []}
        query += " WHERE dr.salesperson_id=:salesperson_id"
        params["salesperson_id"] = user["salesperson_id"]
    query += " ORDER BY dr.report_date DESC, dr.id DESC"
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return {"count": len(rows), "reports": [dict(row) for row in rows]}
