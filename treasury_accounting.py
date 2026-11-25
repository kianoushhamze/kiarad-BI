"""Recognized income and expenses, separate from treasury cash movements."""
from datetime import date, timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from db import engine
from iran_time import iran_today


class AccountingCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    kind: Literal["income", "expense"]

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class AccountingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: int = Field(gt=0)
    amount: int = Field(gt=0, le=10**14)
    recognized_on: date
    description: str = Field(min_length=2, max_length=300)
    check_id: int | None = Field(default=None, gt=0)


def ensure_accounting(conn):
    existing = conn.execute(text("""
        SELECT to_regclass('treasury_accounting_categories') IS NOT NULL
           AND to_regclass('treasury_accounting_entries') IS NOT NULL
    """)).scalar()
    if existing:
        return
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('treasury-accounting-schema'))"))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS treasury_accounting_categories (
            id BIGSERIAL PRIMARY KEY, name VARCHAR(120) NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
            UNIQUE (kind, name)
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS treasury_accounting_entries (
            id BIGSERIAL PRIMARY KEY,
            category_id BIGINT NOT NULL REFERENCES treasury_accounting_categories(id),
            amount BIGINT NOT NULL CHECK (amount > 0), recognized_on DATE NOT NULL,
            description VARCHAR(300) NOT NULL, created_by INTEGER NOT NULL,
            check_id BIGINT UNIQUE REFERENCES financial_documents(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_treasury_accounting_recognized
        ON treasury_accounting_entries (recognized_on, id)
    """))


def add_category(data: AccountingCategory):
    with engine.begin() as conn:
        ensure_accounting(conn)
        category_id = conn.execute(text("""
            INSERT INTO treasury_accounting_categories (name, kind)
            VALUES (:name, :kind) ON CONFLICT (kind, name) DO NOTHING RETURNING id
        """), data.model_dump()).scalar()
    if category_id is None:
        raise HTTPException(409, "این سرفصل قبلاً ثبت شده است.")
    return {"id": category_id}


def add_entry(data: AccountingEntry, actor_id: int):
    description = data.description.strip()
    if len(description) < 2:
        raise HTTPException(422, "شرح رویداد مالی را وارد کنید.")
    with engine.begin() as conn:
        ensure_accounting(conn)
        if not conn.execute(text("SELECT id FROM treasury_accounting_categories WHERE id=:id"),
                            {"id": data.category_id}).scalar():
            raise HTTPException(404, "سرفصل یافت نشد.")
        if data.check_id is not None:
            check = conn.execute(text("""
                SELECT id FROM financial_documents
                WHERE id=:id AND (document_type IN ('receivable_check', 'payable_check')
                                  OR to_jsonb(financial_documents)->'check_details' IS NOT NULL
                                  AND to_jsonb(financial_documents)->'check_details' <> 'null'::jsonb)
            """), {"id": data.check_id}).scalar()
            if check is None:
                raise HTTPException(404, "چک مرتبط یافت نشد.")
        entry_id = conn.execute(text("""
            INSERT INTO treasury_accounting_entries
                (category_id, amount, recognized_on, description, created_by, check_id)
            VALUES (:category_id, :amount, :recognized_on, :description, :actor_id, :check_id)
            ON CONFLICT (check_id) DO NOTHING RETURNING id
        """), {**data.model_dump(), "description": description, "actor_id": actor_id}).scalar()
    if entry_id is None:
        raise HTTPException(409, "این چک قبلاً به یک رویداد مالی متصل شده است.")
    return {"id": entry_id}


def accounting_report(start=None, end=None, *, include_entries=False):
    end = end or iran_today()
    start = start or end - timedelta(days=29)
    if start > end:
        raise HTTPException(422, "تاریخ شروع باید پیش از تاریخ پایان باشد.")
    args = {"start": start, "end": end}
    with engine.begin() as conn:
        ensure_accounting(conn)
        categories = [dict(row) for row in conn.execute(text("""
            SELECT c.id, c.name, c.kind, COALESCE(SUM(e.amount),0) AS total, COUNT(e.id) AS entry_count
            FROM treasury_accounting_categories c
            LEFT JOIN treasury_accounting_entries e
                ON e.category_id=c.id AND e.recognized_on BETWEEN :start AND :end
            GROUP BY c.id ORDER BY c.kind, c.name
        """), args).mappings()]
        checks = [dict(row) for row in conn.execute(text("""
            SELECT fd.document_type, fd.status,
                   COALESCE(to_jsonb(fd)->'check_details'->>'sayad_registration', 'unknown') AS sayad_registration,
                   COUNT(*) AS count, SUM(fd.amount) AS total
            FROM financial_documents fd
            WHERE fd.due_date BETWEEN :start AND :end
              AND (fd.document_type IN ('receivable_check', 'payable_check')
                   OR to_jsonb(fd)->'check_details' <> 'null'::jsonb)
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """), args).mappings()]
        spent = [dict(row) for row in conn.execute(text("""
            SELECT COALESCE(NULLIF(to_jsonb(fd)->'check_details'->>'spent_for',''), 'نامشخص') AS destination,
                   COUNT(*) AS count, SUM(fd.amount) AS total
            FROM financial_documents fd
            WHERE fd.status='spent' AND fd.due_date BETWEEN :start AND :end
            GROUP BY 1 ORDER BY SUM(fd.amount) DESC, 1
        """), args).mappings()]
        entries = []
        if include_entries:
            entries = [dict(row) for row in conn.execute(text("""
                SELECT e.id, e.recognized_on, e.amount, e.description, e.check_id, c.name, c.kind
                FROM treasury_accounting_entries e JOIN treasury_accounting_categories c ON c.id=e.category_id
                WHERE e.recognized_on BETWEEN :start AND :end
                ORDER BY e.recognized_on DESC, e.id DESC LIMIT 100
            """), args).mappings()]
    income = sum(int(row["total"]) for row in categories if row["kind"] == "income")
    expense = sum(int(row["total"]) for row in categories if row["kind"] == "expense")
    for row in categories:
        row["total"] = int(row["total"])
    return {"start": start, "end": end, "currency": "IRR", "income": income, "expense": expense,
            "profit": income - expense, "categories": categories, "checks_by_due_date": checks,
            "entry_count": sum(row["entry_count"] for row in categories), "spent_checks_by_destination": spent,
            "entries": entries, "basis": "درآمد و هزینهٔ ثبت‌شده در دفتر داشبورد بر اساس تاریخ شناسایی. چک‌ها بر اساس سررسید جداگانه گزارش می‌شوند و به‌خودی‌خود درآمد یا هزینه نیستند."}
