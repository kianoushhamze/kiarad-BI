import hashlib
import hmac
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import text

from db import engine
from iran_time import iran_today, iran_month_bounds
from target_schema import ensure_person_target_columns, normalize_person_target, validate_target_person


router = APIRouter(tags=["operations"])

JWT_SECRET = os.getenv("KIARAD_JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
TOKEN_HOURS = 12
MANAGER_ROLES = {"ceo", "sales_manager"}
ROLE_PERMISSION_SENTINEL = "__configured__"
ROLE_MODULE_ALIASES = {
    "personnel": ("personnel", "person-targets"),
}
DEFAULT_ROLE_MODULES = {
    "salesperson": ["customers", "debtors", "catalog", "visitors", "visitor-kpis", "proformas", "crm", "tasks", "daily-reports", "personnel", "payroll", "voice-report", "map", "assistant", "kerman-bases", "team-chat"],
    "visitor": ["customers", "debtors", "catalog", "visitors", "visitor-kpis", "proformas", "crm", "tasks", "daily-reports", "personnel", "payroll", "voice-report", "map", "assistant", "kerman-bases", "team-chat"],
    "sales_manager": ["visitors", "visitor-kpis", "proformas", "crm", "campaigns", "tasks", "team-chat", "assistant", "kerman-bases", "voice-report", "daily-reports"],
    "finance": ["treasury", "payroll", "team-chat", "assistant"],
}


def get_role_module_permissions(role: str, *, connection=None) -> dict[str, dict[str, bool]]:
    """Return configured module grants, falling back only for roles never configured."""
    query=text("SELECT module, can_read, can_write, can_delete FROM role_permissions WHERE role = :r")
    if connection is None:
        with engine.connect() as conn:
            rows = conn.execute(query, {"r": role}).mappings().all()
    else:
        rows = connection.execute(query, {"r": role}).mappings().all()

    if rows:
        return {
            str(row["module"]): {
                "can_read": bool(row["can_read"]),
                "can_write": bool(row["can_write"]),
                "can_delete": bool(row["can_delete"]),
            }
            for row in rows
            if row["module"] != ROLE_PERMISSION_SENTINEL
        }

    return {
        module: {"can_read": True, "can_write": True, "can_delete": False}
        for module in DEFAULT_ROLE_MODULES.get(role, ["assistant", "team-chat"])
    }


def role_has_module_permission(role: str, module: str, action: str = "can_read", *, connection=None) -> bool:
    if role == "ceo":
        return True
    permissions = get_role_module_permissions(role) if connection is None else get_role_module_permissions(role,connection=connection)
    candidate_names = ROLE_MODULE_ALIASES.get(module, (module,))
    for candidate in (*candidate_names, "*"):
        grant = permissions.get(candidate)
        if grant and grant.get(action, False):
            return True
    return False


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
    # Read at call time: module import order (tests, tools) must not freeze an empty secret.
    secret = os.getenv("KIARAD_JWT_SECRET", "") or JWT_SECRET
    if len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="KIARAD_JWT_SECRET must be configured with at least 32 characters.",
        )
    return secret


def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "role": user["role"],
        "pwd_ver": user["password_version"],
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
        if payload.get("role") == "site_customer":
            raise jwt.InvalidTokenError("Customer tokens cannot authenticate employees")
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, username, full_name, role, salesperson_id, is_active, password_version
                FROM users WHERE id = :id
            """),
            {"id": user_id},
        ).mappings().first()
    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="User is inactive")
    if payload.get("pwd_ver", 0) != row["password_version"]:
        raise HTTPException(status_code=401, detail="Session expired after password change")
    return dict(row)


def require_manager(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Manager access required")
    return user


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=200)
    new_password: SecretStr = Field(min_length=10, max_length=200)


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
    note: Optional[str] = Field(default=None, max_length=5000)


class TaskReview(BaseModel):
    decision: str
    note: Optional[str] = Field(default=None, max_length=5000)


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
                       salesperson_id, is_active, password_version
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


@router.post("/auth/password")
def change_own_password(data: PasswordChangeRequest, user: dict = Depends(current_user)):
    require_jwt_secret()
    previous = data.current_password.get_secret_value()
    replacement = data.new_password.get_secret_value()
    if previous == replacement:
        raise HTTPException(status_code=422, detail="رمز جدید باید با رمز فعلی متفاوت باشد")
    with engine.begin() as conn:
        existing = conn.execute(text("""
            SELECT id, password_hash, is_active, password_version
            FROM users WHERE id=:id FOR UPDATE
        """), {"id": user["id"]}).mappings().first()
        if not existing or not existing["is_active"]:
            raise HTTPException(status_code=401, detail="نشست حساب معتبر نیست؛ دوباره وارد شوید")
        if existing["password_version"] != user["password_version"]:
            raise HTTPException(status_code=401, detail="نشست قبلی منقضی شده است؛ دوباره وارد شوید")
        if not verify_password(previous, existing["password_hash"]):
            raise HTTPException(status_code=400, detail="رمز فعلی درست نیست")
        updated = conn.execute(text("""
            UPDATE users SET password_hash=:password_hash,
                password_version=COALESCE(password_version,0)+1
            WHERE id=:id
            RETURNING id, username, full_name, role, salesperson_id, password_version
        """), {"id": user["id"], "password_hash": hash_password(replacement)}).mappings().one()
        updated_user = dict(updated)
        replacement_token = create_token(updated_user)
    return {
        "access_token": replacement_token,
        "token_type": "bearer",
        "user": {key: updated_user[key] for key in ("id", "username", "full_name", "role", "salesperson_id")},
    }


@router.get("/roles")
def list_roles(_: dict = Depends(require_manager)):
    with engine.connect() as conn:
        roles = conn.execute(text("""
            SELECT DISTINCT role FROM role_permissions
            UNION SELECT DISTINCT role FROM users WHERE role != ''
            ORDER BY role
        """)).fetchall()
        result = []
        for row in roles:
            r = row[0]
            perms = conn.execute(text(
                "SELECT module, can_read, can_write, can_delete FROM role_permissions WHERE role = :r ORDER BY module"
            ), {"r": r}).mappings().all()
            users_count = conn.execute(text(
                "SELECT COUNT(*) FROM users WHERE role = :r AND is_active = 1"
            ), {"r": r}).scalar()
            result.append({
                "role": r,
                "users_count": users_count,
                "permissions": [
                    {**dict(p), "module": "personnel" if p["module"] == "person-targets" else p["module"]}
                    for p in perms if p["module"] != ROLE_PERMISSION_SENTINEL
                ],
            })
    return {"roles": result}


@router.post("/roles/{role}/permissions")
def set_role_permissions(role: str, data: dict, manager: dict = Depends(require_manager)):
    if manager.get("role") != "ceo":
        raise HTTPException(status_code=403, detail="Only CEO can change permissions")
    if role == "ceo":
        raise HTTPException(status_code=403, detail="Cannot change CEO permissions")
    permissions = data.get("permissions")
    if permissions is None:
        # Backwards compatibility for older role editors.
        modules = data.get("modules") or []
        if not isinstance(modules, list) or any(not isinstance(module, str) for module in modules):
            raise HTTPException(status_code=422, detail="modules must be a list of module names")
        permissions = [
            {"module": module, "can_read": True, "can_write": True, "can_delete": False}
            for module in modules
        ]
    if not isinstance(permissions, list):
        raise HTTPException(status_code=422, detail="permissions must be a list")
    normalized = {}
    for item in permissions:
        if not isinstance(item, dict) or not isinstance(item.get("module"), str):
            raise HTTPException(status_code=422, detail="each permission needs a module name")
        module = item["module"].strip()
        if not module or module == ROLE_PERMISSION_SENTINEL:
            continue
        grant = {key: item.get(key, False) for key in ("can_read", "can_write", "can_delete")}
        if any(not isinstance(value, bool) for value in grant.values()):
            raise HTTPException(status_code=422, detail="permission flags must be booleans")
        if grant["can_write"] and not grant["can_read"]:
            raise HTTPException(status_code=422, detail="write permission requires read permission")
        if grant["can_delete"] and not grant["can_write"]:
            raise HTTPException(status_code=422, detail="delete permission requires write permission")
        normalized[module] = grant
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM role_permissions WHERE role = :r"), {"r": role})
        if not normalized:
            # Distinguish an intentional empty grant list from an unconfigured role.
            conn.execute(text("""
                INSERT INTO role_permissions (role, module, can_read, can_write, can_delete)
                VALUES (:r, :m, FALSE, FALSE, FALSE)
            """), {"r": role, "m": ROLE_PERMISSION_SENTINEL})
        for m, grant in normalized.items():
            conn.execute(text("""
                INSERT INTO role_permissions (role, module, can_read, can_write, can_delete)
                VALUES (:r, :m, :read, :write, :delete)
            """), {"r": role, "m": m, "read": grant["can_read"],
                    "write": grant["can_write"], "delete": grant["can_delete"]})
        if conn.execute(text("SELECT to_regclass('traccar_shifts') IS NOT NULL")).scalar() and not role_has_module_permission(role,'map','can_write',connection=conn):
            conn.execute(text("""UPDATE tracking_sessions s SET ended_at=NOW(),last_device_status='permission_revoked'
                FROM traccar_shifts x,users u WHERE x.session_id=s.id AND u.id=s.user_id AND u.role=:role AND s.ended_at IS NULL"""),{'role':role})
    return {"ok": True, "role": role, "modules_count": len(normalized)}


@router.get("/roles/all-modules")
def list_all_modules(_: dict = Depends(require_manager)):
    return {"modules": [
        "management", "visitor-kpis", "kerman-bases", "customers", "debtors", "proformas",
        "personnel", "manager", "visitors", "compensation", "payroll",
        "map", "daily-reports", "voice-report",
        "crm", "campaigns", "catalog", "advisory",
        "treasury",
        "online-sales", "social",
        "tasks", "team-chat", "assistant"
    ]}


@router.get("/auth/permissions")
def permissions(user: dict = Depends(current_user)):
    role = user.get("role", "")
    if role == "ceo":
        return {"modules": ["*"], "role": role}

    grants = get_role_module_permissions(role)
    modules = [
        "personnel" if module == "person-targets" else module
        for module, grant in grants.items()
        if module != "*" and grant["can_read"]
    ]
    if grants.get("*") and grants["*"]["can_read"]:
        modules.append("*")

    return {"modules": modules, "role": role}


@router.get("/targets/person-targets")
def list_person_targets(salesperson_id: int = None, user: dict = Depends(current_user)):
    # Every non-manager may see only their own target, including the legacy visitor role.
    if user.get("role") not in MANAGER_ROLES:
        salesperson_id = user.get("salesperson_id")
        if not salesperson_id:
            return {"items": []}
    with engine.connect() as conn:
        if salesperson_id:
            rows = conn.execute(text("""
                SELECT t.*, sp.name AS salesperson_name
                FROM targets t
                LEFT JOIN salespersons sp ON sp.id = t.salesperson_id
                WHERE t.salesperson_id = :spid
                ORDER BY t.id DESC
            """), {"spid": salesperson_id}).mappings().all()
        else:
            rows = conn.execute(text("""
                SELECT t.*, sp.name AS salesperson_name
                FROM targets t
                LEFT JOIN salespersons sp ON sp.id = t.salesperson_id
                ORDER BY t.id DESC
            """)).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/targets/person-targets", status_code=201)
def create_person_target(data: dict, user: dict = Depends(require_manager)):
    values = normalize_person_target(data)
    with engine.begin() as conn:
        validate_target_person(conn, values)
        ident = conn.execute(text("""
            INSERT INTO targets
                (title, target_amount, month, year, target_type, start_date, end_date,
                 status, salesperson_id, period_type, product_focus, bonus_reward, created_at)
            VALUES
                (:title, :target_amount, :month, :year, :target_type, :start_date, :end_date,
                 :status, :salesperson_id, :period_type, :product_focus, :bonus_reward, NOW())
            RETURNING id
        """), values).scalar_one()
    return {"ok": True, "id": ident}


@router.get("/targets/person-targets/options")
def person_target_options(user: dict = Depends(require_manager)):
    with engine.connect() as conn:
        people = conn.execute(text("SELECT id, name FROM salespersons ORDER BY name, id")).mappings()
        return {
            "salespersons": [dict(row) for row in people],
            "can_write": role_has_module_permission(user["role"], "personnel", "can_write", connection=conn),
        }


@router.patch("/targets/person-targets/{tid}")
def update_person_target(tid: int, data: dict, user: dict = Depends(require_manager)):
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT * FROM targets WHERE id=:id FOR UPDATE"), {"id": tid}).mappings().first()
        if not existing:
            raise HTTPException(404, "تارگت پیدا نشد.")
        values = normalize_person_target(data, existing=existing)
        validate_target_person(conn, values)
        assignments = ", ".join(f"{field} = :{field}" for field in values)
        conn.execute(text(f"UPDATE targets SET {assignments} WHERE id=:id"), {**values, "id": tid})
    return {"ok": True}


@router.delete("/targets/person-targets/{tid}")
def delete_person_target(tid: int, user: dict = Depends(require_manager)):
    with engine.begin() as conn:
        r = conn.execute(text("DELETE FROM targets WHERE id = :id RETURNING id"), {"id": tid}).first()
    if not r:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/targets/my-summary")
def my_target_summary(user: dict = Depends(current_user)):
    """Salesperson sees own target summary: targets + achieved sales."""
    spid = user.get("salesperson_id")
    if not spid:
        return {"salesperson_id": None, "targets": [], "sales": {"total": 0, "orders": 0}}
    month_start, month_end = iran_month_bounds()
    with engine.connect() as conn:
        # Get all active targets for this user
        targets = conn.execute(text("""
            SELECT id, title, target_amount, target_type, product_focus,
                   period_type, start_date, end_date, bonus_reward, status
            FROM targets
            WHERE salesperson_id = :spid AND status = 'active'
            ORDER BY id DESC
        """), {"spid": spid}).mappings().all()

        # Get this month's sales
        month_sales = conn.execute(text("""
            SELECT COALESCE(SUM(total_amount),0)
            FROM sales
            WHERE salesperson_id = :spid
              AND date >= :month_start
              AND date < :month_end
        """), {"spid": spid, "month_start": month_start, "month_end": month_end}).scalar() or 0

        # Get monthly sales for target calculation
        total_target = conn.execute(text("""
            SELECT COALESCE(SUM(target_amount),0)
            FROM targets
            WHERE salesperson_id = :spid AND status = 'active'
              AND COALESCE(target_type, '') <> 'تسویه'
              AND (start_date IS NULL OR start_date < :month_end)
              AND (end_date IS NULL OR end_date >= :month_start)
        """), {"spid": spid, "month_start": month_start, "month_end": month_end}).scalar() or 0

    achievement = 0
    if total_target and total_target > 0:
        achievement = round(float(month_sales) / float(total_target) * 100, 1)

    return {
        "salesperson_id": spid,
        "month_sales": float(month_sales),
        "total_target": float(total_target),
        "achievement_percent": achievement,
        "targets": [dict(t) for t in targets],
    }


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
    allowed_roles = {"ceo", "salesperson"}
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
        username = data.username.strip().lower()
        if not 3 <= len(username) <= 100:
            raise HTTPException(422, 'نام کاربری باید بین ۳ و ۱۰۰ نویسه باشد.')
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {'key': 'user-name:' + username})
        duplicate = conn.execute(
            text("SELECT id FROM users WHERE username=:username"),
            {"username": username},
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
            "username": username,
            "password_hash": hash_password(data.password),
            "full_name": data.full_name.strip(),
            "role": data.role,
            "salesperson_id": data.salesperson_id,
        }).mappings().first()
    return dict(row)



@router.patch("/users/{user_id}")
def update_user(user_id: int, data: dict, manager: dict = Depends(require_manager)):
    if user_id == 1 and (data.get("role", "ceo") != "ceo" or data.get("is_active", 1) in (0, False, "0")):
        raise HTTPException(status_code=403, detail="cannot demote or deactivate main CEO")
    fields = []
    params = {"id": user_id}
    allowed = {"full_name", "role", "salesperson_id", "is_active", "username"}
    for k in allowed:
        if k in data:
            fields.append(k + " = :" + k)
            params[k] = data[k]
    if not fields:
        raise HTTPException(status_code=422, detail="no valid fields")
    if "role" in data:
        allowed_roles = {"ceo", "salesperson"}
        if data["role"] not in allowed_roles:
            raise HTTPException(status_code=422, detail="Invalid role")
        if manager["role"] != "ceo" and data["role"] in {"ceo", "sales_manager", "finance"}:
            raise HTTPException(status_code=403, detail="Only CEO can set privileged roles")
    sql = "UPDATE users SET " + ", ".join(fields) + " WHERE id = :id RETURNING id, username, full_name, role, salesperson_id, is_active"
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT role,salesperson_id FROM users WHERE id=:id FOR UPDATE"), {"id": user_id}).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        if manager['role'] != 'ceo' and existing['role'] in {'ceo', 'sales_manager', 'finance'}:
            raise HTTPException(status_code=403, detail="فقط مدیرعامل می‌تواند حساب دارای دسترسی مدیریتی را تغییر دهد")
        if 'username' in data:
            if existing['role'] not in {'salesperson', 'visitor'}:
                raise HTTPException(403, 'تغییر نام کاربری فقط برای حساب ویزیتور مجاز است.')
            value = data['username']
            if not isinstance(value, str) or not 3 <= len(value.strip()) <= 100:
                raise HTTPException(422, 'نام کاربری باید بین ۳ و ۱۰۰ نویسه باشد.')
            username = value.strip().lower()
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {'key': 'user-name:' + username})
            if conn.execute(text("SELECT id FROM users WHERE username=:name AND id<>:id"),
                            {'name': username, 'id': user_id}).first():
                raise HTTPException(409, 'نام کاربری از قبل ثبت شده است.')
            params['username'] = username
        target_role = data.get('role', existing['role'])
        target_sp = data.get('salesperson_id', existing['salesperson_id'])
        if target_role in {'salesperson', 'visitor'} and not target_sp:
            raise HTTPException(status_code=422, detail="حساب پرسنل باید به پروفایل متصل باشد")
        if target_sp and not conn.execute(text("SELECT id FROM salespersons WHERE id=:id"), {'id': target_sp}).first():
            raise HTTPException(status_code=404, detail="پروفایل پرسنل پیدا نشد")
        if 'full_name' in data and (not isinstance(data['full_name'], str) or not 2 <= len(data['full_name'].strip()) <= 150):
            raise HTTPException(status_code=422, detail="نام کامل باید بین ۲ و ۱۵۰ نویسه باشد")
        if 'is_active' in data and (type(data['is_active']) not in (bool, int) or data['is_active'] not in (0, 1)):
            raise HTTPException(status_code=422, detail="وضعیت فعال معتبر نیست")
        # Reassignment and role changes must not leave old sessions usable.
        if {'role', 'salesperson_id', 'is_active', 'username'} & data.keys():
            sql = sql.replace(' WHERE id = :id', ', password_version=COALESCE(password_version,0)+1 WHERE id = :id')
        row = conn.execute(text(sql), params).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@router.post("/users/{user_id}/password")
def change_password(user_id: int, data: dict, manager: dict = Depends(require_manager)):
    newpass = data.get("password")
    if not isinstance(newpass, str) or not 10 <= len(newpass) <= 200:
        raise HTTPException(status_code=422, detail="password too short")
    with engine.begin() as conn:
        target = conn.execute(text("SELECT role FROM users WHERE id=:id FOR UPDATE"), {'id': user_id}).mappings().first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        if manager['role'] != 'ceo' and target['role'] in {'ceo', 'sales_manager', 'finance'}:
            raise HTTPException(status_code=403, detail="فقط مدیرعامل می‌تواند رمز حساب مدیریتی را تغییر دهد")
        row = conn.execute(text(
            "UPDATE users SET password_hash = :h, password_version=COALESCE(password_version,0)+1 WHERE id = :id RETURNING id"
        ), {"h": hash_password(newpass), "id": user_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, manager: dict = Depends(require_manager)):
    if user_id == 1:
        raise HTTPException(status_code=403, detail="cannot delete main CEO")
    if manager.get("id") == user_id:
        raise HTTPException(status_code=403, detail="cannot delete yourself")
    with engine.begin() as conn:
        target = conn.execute(text("SELECT role FROM users WHERE id=:id FOR UPDATE"), {"id": user_id}).mappings().first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        if manager["role"] != "ceo" and target["role"] in {"ceo", "sales_manager", "finance"}:
            raise HTTPException(status_code=403, detail="فقط مدیرعامل می‌تواند حساب دارای دسترسی مدیریتی را حذف کند")
        row = conn.execute(text("DELETE FROM users WHERE id = :id RETURNING id"), {"id": user_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


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
                  AND COALESCE(target_type, '') <> 'تسویه'
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
        item["report_submitted_today"] = item["last_report_date"] == iran_today()
        visitors.append(item)
    return {"count": len(visitors), "visitors": visitors}


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, manager: dict = Depends(require_manager)):
    with engine.begin() as conn:
        return create_task_in_connection(conn, data, manager)


def create_task_in_connection(conn, data: TaskCreate, manager: dict):
    if manager.get("role") not in MANAGER_ROLES:raise HTTPException(403,"تخصیص کار فقط برای مدیر مجاز است.")
    if not data.title.strip():
        raise HTTPException(status_code=422, detail="عنوان کار را وارد کنید")
    if data.priority not in {"low", "normal", "high", "urgent"}:
        raise HTTPException(status_code=422, detail="Invalid priority")
    _ensure_task_workflow(conn)
    assignee = conn.execute(
        text("SELECT id FROM users WHERE id=:id AND is_active::text IN ('1','true','t')"),
        {"id": data.assigned_to},
    ).first()
    if not assignee:
        raise HTTPException(status_code=404, detail="Assignee not found")
    row = conn.execute(
        text("""
            INSERT INTO tasks
                (title, description, priority, status, progress, assigned_to,
                 created_by, customer_id, due_date, created_at, updated_at, review_status)
            VALUES
                (:title, :description, :priority, 'new', 0, :assigned_to,
                 :created_by, :customer_id, :due_date, NOW(), NOW(), 'not_submitted')
            RETURNING *
        """),
        {**data.model_dump(), "title": data.title.strip(), "created_by": manager["id"]},
    ).mappings().first()
    conn.execute(text("""INSERT INTO task_updates
        (task_id,user_id,progress,status,note,created_at)
        VALUES (:task_id,:user_id,0,'new',:note,NOW())"""),
        {"task_id": row["id"], "user_id": manager["id"], "note": "ایجاد و تخصیص کار"})
    return dict(row)


@router.on_event("startup")
def initialize_task_workflow():
    with engine.begin() as conn:
        _ensure_task_workflow(conn)


@router.on_event("startup")
def initialize_person_target_columns():
    with engine.begin() as conn:
        ensure_person_target_columns(conn)


def _ensure_task_workflow(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT,
        priority VARCHAR(20) NOT NULL DEFAULT 'normal', status VARCHAR(20) NOT NULL DEFAULT 'new',
        progress INTEGER NOT NULL DEFAULT 0, assigned_to INTEGER NOT NULL REFERENCES users(id),
        created_by INTEGER NOT NULL REFERENCES users(id), customer_id INTEGER REFERENCES customers(id),
        due_date TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )"""))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS task_updates (
        id SERIAL PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
        user_id INTEGER NOT NULL REFERENCES users(id), progress INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL, note TEXT, created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )"""))
    conn.execute(text("""ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS review_status VARCHAR(30) NOT NULL DEFAULT 'not_submitted',
        ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES users(id),
        ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS review_note TEXT"""))


@router.on_event("startup")
def initialize_campaign_assignments():
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS role_permissions (
            role TEXT NOT NULL, module TEXT NOT NULL,
            can_read BOOLEAN NOT NULL DEFAULT FALSE,
            can_write BOOLEAN NOT NULL DEFAULT FALSE,
            can_delete BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (role, module)
        )"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS campaigns (
            id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT,
            starts_at DATE NOT NULL, ends_at DATE NOT NULL,
            target_amount NUMERIC NOT NULL DEFAULT 0,
            reward_type TEXT NOT NULL DEFAULT 'fixed',
            reward_value NUMERIC NOT NULL DEFAULT 0, reward_note TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        )"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS campaign_assignments (
            campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            assigned_by INTEGER NOT NULL REFERENCES users(id),
            assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (campaign_id, user_id)
        )"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS notification_reads (
            user_id INTEGER NOT NULL REFERENCES users(id),
            notification_key TEXT NOT NULL,
            read_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, notification_key)
        )"""))


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": f"public.{table_name}"}).scalar()


def _notification_items(conn, user: dict) -> list[dict]:
    items: list[dict] = []
    manager = user.get("role") in MANAGER_ROLES
    if _table_exists(conn, "tasks"):
        params = {}
        scope = ""
        if not manager:
            scope = " AND assigned_to=:user_id"
            params["user_id"] = user["id"]
        overdue = int(conn.execute(text(f"""
            SELECT COUNT(*) FROM tasks
            WHERE status <> 'completed' AND due_date IS NOT NULL
              AND due_date < NOW(){scope}
        """), params).scalar() or 0)
        if overdue:
            items.append({"key": "tasks:overdue", "kind": "task", "severity": "warning",
                          "title": "وظایف عقب‌افتاده", "message": f"{overdue} وظیفه از موعد گذشته است.",
                          "href": "/tasks"})
        if manager:
            pending = int(conn.execute(text("SELECT COUNT(*) FROM tasks WHERE review_status='pending' AND assigned_to<>:manager_id"), {"manager_id": user["id"]}).scalar() or 0)
            if pending:
                items.append({"key": "tasks:review", "kind": "task", "severity": "info",
                              "title": "گزارش کار منتظر بررسی", "message": f"{pending} گزارش کار منتظر تصمیم شماست.",
                              "href": "/tasks"})

    if _table_exists(conn, "visit_route_assignments"):
        params = {}
        scope = ""
        if not manager:
            scope = " AND user_id=:user_id"
            params["user_id"] = user["id"]
        route_count = int(conn.execute(text(f"""
            SELECT COUNT(*) FROM visit_route_assignments
            WHERE visit_date=CURRENT_DATE{scope}
        """), params).scalar() or 0)
        if route_count:
            items.append({"key": "routes:today", "kind": "route", "severity": "info",
                          "title": "مسیر ویزیت امروز", "message": f"{route_count} ایستگاه برای امروز برنامه‌ریزی شده است.",
                          "href": "/my-plan"})

    salesperson_id = user.get("salesperson_id")
    if not manager and salesperson_id and _table_exists(conn, "daily_reports"):
        submitted = conn.execute(text("""
            SELECT 1 FROM daily_reports WHERE salesperson_id=:salesperson_id
              AND report_date=CURRENT_DATE LIMIT 1
        """), {"salesperson_id": salesperson_id}).first()
        if not submitted:
            items.append({"key": f"report:missing:{iran_today().isoformat()}", "kind": "report", "severity": "warning",
                          "title": "گزارش روزانه ثبت نشده", "message": "گزارش کار امروز هنوز ثبت نشده است.",
                          "href": "/voice-report"})

    if manager and _table_exists(conn, "payroll_approvals"):
        pending = int(conn.execute(text("""
            SELECT COUNT(*) FROM users u
            WHERE u.salesperson_id IS NOT NULL AND u.is_active::text IN ('1','true','t')
              AND NOT EXISTS (
                SELECT 1 FROM payroll_approvals p
                WHERE p.salesperson_id=u.salesperson_id
                  AND p.payroll_month=TO_CHAR(CURRENT_DATE,'YYYY-MM')
              )
        """)).scalar() or 0)
        if pending:
            items.append({"key": "payroll:pending", "kind": "payroll", "severity": "warning",
                          "title": "کارکرد منتظر تأیید", "message": f"کارکرد {pending} نفر در این ماه تأیید نشده است.",
                          "href": "/payroll"})
    try:
        from assistant_automations import notification_items as automation_items
        items.extend(automation_items(conn, user))
    except Exception:
        pass
    from agent_center import alert_items
    items.extend(alert_items(conn, user))
    return items


@router.get("/notifications")
def list_notifications(user: dict = Depends(current_user)):
    with engine.connect() as conn:
        items = _notification_items(conn, user)
        reads = {row[0] for row in conn.execute(text(
            "SELECT notification_key FROM notification_reads WHERE user_id=:user_id"
        ), {"user_id": user["id"]}).all()}
    result = [{**item, "read": item["key"] in reads} for item in items]
    return {"items": result, "unread_count": sum(not item["read"] for item in result)}


@router.post("/notifications/{notification_key}/read")
def mark_notification_read(notification_key: str, user: dict = Depends(current_user)):
    if not notification_key or len(notification_key) > 200:
        raise HTTPException(status_code=422, detail="شناسهٔ اعلان معتبر نیست")
    with engine.begin() as conn:
        valid_keys = {item["key"] for item in _notification_items(conn, user)}
        if notification_key not in valid_keys:
            raise HTTPException(status_code=404, detail="اعلان فعال پیدا نشد")
        conn.execute(text("""
            INSERT INTO notification_reads (user_id, notification_key, read_at)
            VALUES (:user_id, :notification_key, NOW())
            ON CONFLICT (user_id, notification_key) DO UPDATE SET read_at=NOW()
        """), {"user_id": user["id"], "notification_key": notification_key})
    return {"status": "read", "key": notification_key}


@router.get("/tasks/campaign-assignments")
def personal_campaigns(user_id: Optional[int] = None, user: dict = Depends(current_user)):
    target_id = user_id if user.get("role") in MANAGER_ROLES and user_id is not None else user["id"]
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.id, c.title, c.description, c.starts_at, c.ends_at, c.is_active, a.assigned_at
            FROM campaign_assignments a JOIN campaigns c ON c.id=a.campaign_id
            WHERE a.user_id=:user_id ORDER BY c.is_active DESC, c.ends_at, c.id
        """), {"user_id": target_id}).mappings().all()
    return {"items": [dict(row) for row in rows]}


class CampaignAssignment(BaseModel):
    campaign_id: int = Field(gt=0)
    user_id: int = Field(gt=0)


@router.post("/tasks/campaign-assignments")
def assign_campaign(data: CampaignAssignment, manager: dict = Depends(require_manager)):
    with engine.begin() as conn:
        if not conn.execute(text("SELECT id FROM users WHERE id=:id AND is_active=TRUE"), {"id": data.user_id}).first():
            raise HTTPException(status_code=404, detail="حساب فعال پرسنل پیدا نشد")
        campaign = conn.execute(text("SELECT id FROM campaigns WHERE id=:id AND is_active=TRUE FOR UPDATE"), {"id": data.campaign_id}).first()
        if not campaign:
            raise HTTPException(status_code=409, detail="کمپین فعال پیدا نشد")
        conn.execute(text("""INSERT INTO campaign_assignments (campaign_id,user_id,assigned_by)
            VALUES (:campaign_id,:user_id,:assigned_by)
            ON CONFLICT (campaign_id,user_id) DO NOTHING"""), {**data.model_dump(), "assigned_by": manager["id"]})
    return {"status": "assigned"}

@router.get("/tasks/assignees")
def task_assignees(manager: dict = Depends(require_manager)):
    with engine.connect() as conn:
        rows = conn.execute(text("""SELECT id,username,full_name,role,salesperson_id,is_active
            FROM users WHERE is_active::text IN ('1','true','t')
            AND role IN ('salesperson','visitor') ORDER BY full_name,id""")).mappings().all()
    return {"users": [dict(row) for row in rows]}


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
    with engine.begin() as conn:
        return update_task_progress_in_connection(conn, task_id, data, user)


def update_task_progress_in_connection(conn, task_id: int, data: TaskProgress, user: dict):
    allowed_statuses = {"new", "in_progress", "completed", "blocked"}
    if data.status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Invalid status")
    if data.status == "completed" and data.progress != 100:
        raise HTTPException(status_code=422, detail="Completed tasks must have 100 percent progress")
    if data.status != "completed" and data.progress == 100:
        raise HTTPException(status_code=422, detail="برای پیشرفت کامل، گزارش پایان کار را ارسال کنید")
    note = (data.note or "").strip()
    if data.status in {"completed", "blocked"} and not note:
        raise HTTPException(status_code=422, detail="نتیجهٔ کار یا علت توقف را بنویسید")
    task = conn.execute(
        text("SELECT * FROM tasks WHERE id=:id FOR UPDATE"), {"id": task_id}
    ).mappings().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["assigned_to"] != user["id"]:
        raise HTTPException(status_code=403, detail="Task access denied")
    if task.get("review_status") in {"pending", "approved"}:
        raise HTTPException(status_code=409, detail="این کار در انتظار بررسی یا تأییدشده است")
    row = conn.execute(
        text("""
            UPDATE tasks SET progress=:progress, status=:status, updated_at=NOW(),
                review_status=:review_status, reviewed_by=NULL, reviewed_at=NULL, review_note=NULL
            WHERE id=:id RETURNING *
        """),
        {"id": task_id, "progress": data.progress, "status": data.status,
         "review_status": "pending" if data.status == "completed" else task.get("review_status", "not_submitted")},
    ).mappings().first()
    conn.execute(
        text("""
            INSERT INTO task_updates (task_id, user_id, progress, status, note, created_at)
            VALUES (:task_id, :user_id, :progress, :status, :note, NOW())
        """),
        {"task_id": task_id, "user_id": user["id"], **data.model_dump(), "note": note or None},
    )
    return dict(row)

@router.get("/tasks/{task_id}/updates")
def task_history(task_id: int, user: dict = Depends(current_user)):
    with engine.connect() as conn:
        task = conn.execute(text("SELECT assigned_to FROM tasks WHERE id=:id"), {"id": task_id}).mappings().first()
        if not task:
            raise HTTPException(status_code=404, detail="کار پیدا نشد")
        if user["role"] not in MANAGER_ROLES and task["assigned_to"] != user["id"]:
            raise HTTPException(status_code=403, detail="دسترسی به این کار مجاز نیست")
        rows = conn.execute(text("""SELECT t.*,u.full_name AS author_name
            FROM task_updates t JOIN users u ON u.id=t.user_id
            WHERE t.task_id=:id ORDER BY t.created_at,t.id"""), {"id": task_id}).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/tasks/{task_id}/review")
def review_task(task_id: int, data: TaskReview, manager: dict = Depends(require_manager)):
    if manager["role"] not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="بررسی کار مخصوص مدیر است")
    if data.decision not in {"approved", "changes_requested"}:
        raise HTTPException(status_code=422, detail="نتیجهٔ بررسی معتبر نیست")
    note = (data.note or "").strip()
    if data.decision == "changes_requested" and not note:
        raise HTTPException(status_code=422, detail="علت برگشت کار را بنویسید")
    with engine.begin() as conn:
        task = conn.execute(text("SELECT * FROM tasks WHERE id=:id FOR UPDATE"), {"id": task_id}).mappings().first()
        if not task:
            raise HTTPException(status_code=404, detail="کار پیدا نشد")
        if task["assigned_to"] == manager["id"]:
            raise HTTPException(status_code=403, detail="بررسی کار خودتان باید توسط مدیر دیگری انجام شود")
        if task.get("review_status") != "pending" or task["status"] != "completed":
            raise HTTPException(status_code=409, detail="کار گزارش‌شده‌ای برای بررسی وجود ندارد")
        approved = data.decision == "approved"
        values = {"id": task_id, "review_status": data.decision, "reviewed_by": manager["id"],
                  "note": note or None, "status": "completed" if approved else "in_progress",
                  "progress": 100 if approved else 75}
        row = conn.execute(text("""UPDATE tasks SET review_status=:review_status,
            reviewed_by=:reviewed_by,reviewed_at=NOW(),review_note=:note,
            status=:status,progress=:progress,updated_at=NOW() WHERE id=:id RETURNING *"""), values).mappings().first()
        conn.execute(text("""INSERT INTO task_updates (task_id,user_id,progress,status,note,created_at)
            VALUES (:id,:reviewed_by,:progress,:review_status,:note,NOW())"""), values)
    return dict(row)


@router.post("/daily-reports", status_code=status.HTTP_201_CREATED)
def create_daily_report(data: DailyReportCreate, user: dict = Depends(current_user)):
    if not user["salesperson_id"]:
        raise HTTPException(status_code=403, detail="Salesperson profile required")
    if data.report_date > iran_today():
        raise HTTPException(status_code=422, detail="Future reports are not allowed")
    with engine.begin() as conn:
        conn.execute(text("SELECT id FROM salespersons WHERE id=:id FOR UPDATE"), {"id":user["salesperson_id"]})
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
