from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    name = Column(String)
    phone = Column(String)
    city = Column(String)
    credit_limit = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    sales = relationship("Sale", back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    name = Column(String)
    category = Column(String)
    price = Column(Float)
    stock = Column(Float, default=0)
    min_stock = Column(Float, default=0)
    is_active = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ProductChannel(Base):
    __tablename__ = "product_channels"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    channel = Column(String(30), nullable=False)
    external_id = Column(String(200), nullable=False)
    is_active = Column(Integer, default=1, nullable=False)
    last_synced_at = Column(DateTime)
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_product_channel_external"),)


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    source = Column(String(30), nullable=False)
    quantity = Column(Float, nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    channel = Column(String(30), nullable=False)
    external_order_id = Column(String(200), nullable=False)
    quantity = Column(Float, nullable=False)
    status = Column(String(20), default="reserved", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("channel", "external_order_id", "product_id", name="uq_inventory_reservation"),)


class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    channel = Column(String(30), nullable=False)
    old_price = Column(Float)
    new_price = Column(Float, nullable=False)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id = Column(Integer, primary_key=True)
    channel = Column(String(30), nullable=False)
    direction = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime)
    records_read = Column(Integer, default=0, nullable=False)
    records_written = Column(Integer, default=0, nullable=False)


class SyncError(Base):
    __tablename__ = "sync_errors"
    id = Column(Integer, primary_key=True)
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id"), nullable=True)
    channel = Column(String(30), nullable=False)
    entity = Column(String(50), nullable=False)
    external_id = Column(String(200))
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SalesPerson(Base):
    __tablename__ = "salespersons"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    phone = Column(String)

    targets = relationship("Target", back_populates="salesperson")


class Target(Base):
    __tablename__ = "targets"

    id = Column(Integer, primary_key=True)
    title = Column(String)

    target_amount = Column(Float)

    month = Column(Integer)
    year = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)

    target_type = Column(String)

    start_date = Column(Date)
    end_date = Column(Date)

    status = Column(String)

    salesperson_id = Column(
        Integer,
        ForeignKey("salespersons.id")
    )

    salesperson = relationship(
        "SalesPerson",
        back_populates="targets"
    )


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id")
    )

    salesperson_id = Column(
        Integer,
        ForeignKey("salespersons.id")
    )

    date = Column(DateTime, default=datetime.utcnow)

    total_amount = Column(Float)

    customer = relationship(
        "Customer",
        back_populates="sales"
    )


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True)

    sale_id = Column(
        Integer,
        ForeignKey("sales.id")
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id")
    )

    quantity = Column(Float)
    price = Column(Float)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id")
    )

    amount = Column(Float)

    payment_date = Column(
        DateTime,
        default=datetime.utcnow
    )


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True)

    source = Column(String)

    status = Column(String)

    message = Column(String)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(30), nullable=False)
    salesperson_id = Column(Integer, ForeignKey("salespersons.id"), nullable=True)
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    priority = Column(String(20), default="normal", nullable=False)
    status = Column(String(20), default="new", nullable=False)
    progress = Column(Integer, default=0, nullable=False)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TaskUpdate(Base):
    __tablename__ = "task_updates"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    progress = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("salesperson_id", "report_date", name="uq_daily_report_salesperson_date"),
    )

    id = Column(Integer, primary_key=True)
    salesperson_id = Column(Integer, ForeignKey("salespersons.id"), nullable=False)
    report_date = Column(Date, nullable=False)
    visits_count = Column(Integer, default=0, nullable=False)
    new_customers_count = Column(Integer, default=0, nullable=False)
    orders_count = Column(Integer, default=0, nullable=False)
    lost_orders_count = Column(Integer, default=0, nullable=False)
    reported_sales_amount = Column(Float, default=0, nullable=False)
    reported_collections_amount = Column(Float, default=0, nullable=False)
    loss_reasons = Column(Text)
    competitor_notes = Column(Text)
    demand_notes = Column(Text)
    issues = Column(Text)
    tomorrow_plan = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CashAccount(Base):
    __tablename__ = "cash_accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    account_type = Column(String(30), nullable=False)
    current_balance = Column(Float, default=0, nullable=False)
    minimum_reserve = Column(Float, default=0, nullable=False)
    is_active = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FinancialDocument(Base):
    __tablename__ = "financial_documents"

    id = Column(Integer, primary_key=True)
    document_type = Column(String(20), nullable=False)
    counterparty = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), default="open", nullable=False)
    collection_probability = Column(Float, default=1, nullable=False)
    reference_number = Column(String(100))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FixedExpense(Base):
    __tablename__ = "fixed_expenses"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    due_day = Column(Integer, nullable=False)
    is_active = Column(Integer, default=1, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReceivableSnapshot(Base):
    __tablename__ = "receivable_snapshots"

    id = Column(Integer, primary_key=True)
    source_file = Column(String(255), nullable=False)
    import_hash = Column(String(64), unique=True, nullable=False)
    report_from_text = Column(String(20))
    report_to_text = Column(String(20))
    snapshot_date = Column(Date, nullable=False)
    total_amount = Column(Float, default=0, nullable=False)
    row_count = Column(Integer, default=0, nullable=False)
    imported_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReceivableBalance(Base):
    __tablename__ = "receivable_balances"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("receivable_snapshots.id"), nullable=False)
    counterparty = Column(String(250), nullable=False)
    normalized_counterparty = Column(String(250), nullable=False)
    balance = Column(Float, nullable=False)
    share_percent = Column(Float)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
