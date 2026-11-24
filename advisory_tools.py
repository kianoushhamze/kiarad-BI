"""Advisory Agent Tools - database access for the AI consultant."""
from db import engine
from sqlalchemy import text


def _rows(sql, params=None):
    try:
        with engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql), params or {}).mappings().all()]
    except Exception as e:
        return [{"error": str(e)[:200]}]


def _scalar(sql, params=None, default=0):
    try:
        with engine.connect() as conn:
            v = conn.execute(text(sql), params or {}).scalar()
            return v if v is not None else default
    except Exception:
        return default


# ===== TOOL DEFINITIONS (for OpenAI Function Calling) =====
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_daily_reports",
            "description": "گزارش\u200cهای کار روزانه ویزیتورها. شامل تعداد ویزیت، سفارش، فروش، دلایل از دست رفتن سفارش و برنامه فردا.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "چند روز اخیر (پیش\u200cفرض 7)"},
                    "salesperson_id": {"type": "integer", "description": "اختیاری: فقط یک ویزیتور"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_history",
            "description": "تاریخچه کامل یک مشتری: خرید، بدهی، تعاملات CRM، تسک\u200cها.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "بخشی از نام مشتری"},
                    "days": {"type": "integer", "description": "بازه خرید (پیش\u200cفرض 365)"},
                },
                "required": ["customer_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_analysis",
            "description": "تحلیل کامل یک کالا: فروش، مشتریان خریدار، روند.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "بخشی از نام کالا"},
                },
                "required": ["product_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_salesperson_stats",
            "description": "آمار تفصیلی یک ویزیتور: فروش، مشتریان، تارگت، گزارش\u200cها.",
            "parameters": {
                "type": "object",
                "properties": {
                    "salesperson_name": {"type": "string"},
                    "days": {"type": "integer"},
                },
                "required": ["salesperson_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_crm_interactions",
            "description": "تعاملات CRM: تماس، ویزیت، پیگیری. برای بررسی وضعیت پیگیری مشتریان.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "visitor_name": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks_list",
            "description": "لیست تسک\u200cها با جزئیات. برای پیگیری کارهای باز.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "open / done / all"},
                    "days": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_proformas",
            "description": "پیش\u200cفاکتورها. برای بررسی سفارش\u200cهای در جریان.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "salesperson_id": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_customers",
            "description": "جستجوی مشتریان بر اساس شهر، بدهی، نام.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "has_debt": {"type": "boolean"},
                    "search": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
]


# ===== TOOL EXECUTORS =====
def execute_tool(name, args):
    try:
        if name == "get_daily_reports":
            return tool_daily_reports(args)
        if name == "get_customer_history":
            return tool_customer_history(args)
        if name == "get_product_analysis":
            return tool_product_analysis(args)
        if name == "get_salesperson_stats":
            return tool_salesperson_stats(args)
        if name == "get_crm_interactions":
            return tool_crm_interactions(args)
        if name == "get_tasks_list":
            return tool_tasks_list(args)
        if name == "get_proformas":
            return tool_proformas(args)
        if name == "search_customers":
            return tool_search_customers(args)
        return {"error": "unknown tool: " + str(name)}
    except Exception as e:
        return {"error": str(e)[:200]}


def tool_daily_reports(args):
    days = int(args.get("days", 7))
    spid = args.get("salesperson_id")
    sql = """
        SELECT dr.report_date, sp.name AS salesperson, dr.visits_count,
               dr.new_customers_count, dr.orders_count, dr.lost_orders_count,
               dr.reported_sales_amount, dr.loss_reasons, dr.competitor_notes,
               dr.demand_notes, dr.issues, dr.tomorrow_plan
        FROM daily_reports dr
        LEFT JOIN salespersons sp ON sp.id = dr.salesperson_id
        WHERE dr.report_date >= CURRENT_DATE - INTERVAL '1 day' * :days
    """
    params = {"days": days}
    if spid:
        sql += " AND dr.salesperson_id = :spid"
        params["spid"] = spid
    sql += " ORDER BY dr.report_date DESC LIMIT 50"
    return _rows(sql, params)


def tool_customer_history(args):
    name = args.get("customer_name", "")
    days = int(args.get("days", 365))
    cust = _rows("SELECT id, name, city, phone, customer_type FROM customers WHERE name ILIKE :q LIMIT 5", {"q": "%" + name + "%"})
    if not cust:
        return {"found": 0, "message": "مشتری با این نام پیدا نشد"}
    cid = cust[0]["id"]
    sales = _rows("""
        SELECT s.date, s.total_amount, sp.name AS salesperson
        FROM sales s LEFT JOIN salespersons sp ON sp.id = s.salesperson_id
        WHERE s.customer_id = :cid AND s.date >= CURRENT_DATE - INTERVAL '1 day' * :days
        ORDER BY s.date DESC LIMIT 30
    """, {"cid": cid, "days": days})
    debt = _rows("SELECT counterparty, balance FROM receivable_balances WHERE customer_id = :cid", {"cid": cid})
    interactions = _rows("""
        SELECT interaction_type, product_discussed, notes, status, created_at, visitor_name
        FROM customer_interactions
        WHERE archived_at IS NULL AND customer_name ILIKE :q
        ORDER BY created_at DESC LIMIT 10
    """, {"q": "%" + name + "%"})
    return {
        "customer": cust[0],
        "sales_count": len(sales),
        "sales": sales,
        "debt": debt,
        "interactions": interactions,
    }


def tool_product_analysis(args):
    name = args.get("product_name", "")
    prod = _rows("SELECT id, code, name, category, price, stock FROM products WHERE name ILIKE :q LIMIT 5", {"q": "%" + name + "%"})
    if not prod:
        return {"found": 0, "message": "کالا پیدا نشد"}
    pid = prod[0]["id"]
    items = _rows("""
        SELECT s.date, si.quantity, si.price, c.name AS customer
        FROM sale_items si
        JOIN sales s ON s.id = si.sale_id
        LEFT JOIN customers c ON c.id = s.customer_id
        WHERE si.product_id = :pid
        ORDER BY s.date DESC LIMIT 50
    """, {"pid": pid})
    total_sold = _scalar("SELECT COALESCE(SUM(si.quantity),0) FROM sale_items si WHERE si.product_id = :pid", {"pid": pid})
    return {
        "product": prod[0],
        "total_quantity_sold": float(total_sold),
        "recent_sales": items,
    }


def tool_salesperson_stats(args):
    name = args.get("salesperson_name", "")
    days = int(args.get("days", 30))
    sp = _rows("SELECT id, name, phone FROM salespersons WHERE name ILIKE :q LIMIT 3", {"q": "%" + name + "%"})
    if not sp:
        return {"found": 0}
    sid = sp[0]["id"]
    sales = _scalar("SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE salesperson_id = :sid AND date >= CURRENT_DATE - INTERVAL '1 day' * :days", {"sid": sid, "days": days})
    count = _scalar("SELECT COUNT(*) FROM sales WHERE salesperson_id = :sid AND date >= CURRENT_DATE - INTERVAL '1 day' * :days", {"sid": sid, "days": days})
    targets = _rows("SELECT title, target_amount, status, product_focus FROM targets WHERE salesperson_id = :sid AND status = 'active'", {"sid": sid})
    reports = _rows("SELECT report_date, visits_count, orders_count, reported_sales_amount FROM daily_reports WHERE salesperson_id = :sid ORDER BY report_date DESC LIMIT 10", {"sid": sid})
    return {
        "salesperson": sp[0],
        "total_sales": float(sales),
        "invoice_count": int(count),
        "active_targets": targets,
        "recent_reports": reports,
    }


def tool_crm_interactions(args):
    sql = "SELECT * FROM customer_interactions WHERE archived_at IS NULL"
    params = {}
    if args.get("customer_name"):
        sql += " AND customer_name ILIKE :cn"
        params["cn"] = "%" + args["customer_name"] + "%"
    if args.get("visitor_name"):
        sql += " AND visitor_name ILIKE :vn"
        params["vn"] = "%" + args["visitor_name"] + "%"
    sql += " ORDER BY created_at DESC LIMIT :lim"
    params["lim"] = int(args.get("limit", 20))
    return _rows(sql, params)


def tool_tasks_list(args):
    status = args.get("status", "open")
    sql = "SELECT t.id, t.title, t.status, t.priority, t.due_date, u.full_name AS assigned_to FROM tasks t LEFT JOIN users u ON u.id = t.assigned_to WHERE 1=1"
    if status == "open":
        sql += " AND t.status NOT IN ('done','cancelled')"
    elif status == "done":
        sql += " AND t.status IN ('done','completed')"
    sql += " ORDER BY t.due_date ASC NULLS LAST LIMIT 30"
    return _rows(sql, {})


def tool_proformas(args):
    sql = "SELECT p.*, c.name AS customer_name, sp.name AS salesperson_name FROM proforma_invoices p LEFT JOIN customers c ON c.id = p.customer_id LEFT JOIN salespersons sp ON sp.id = p.salesperson_id WHERE 1=1"
    params = {}
    if args.get("status"):
        sql += " AND p.status = :st"
        params["st"] = args["status"]
    if args.get("salesperson_id"):
        sql += " AND p.salesperson_id = :sid"
        params["sid"] = int(args["salesperson_id"])
    sql += " ORDER BY p.created_at DESC LIMIT 30"
    return _rows(sql, params)


def tool_search_customers(args):
    sql = "SELECT c.id, c.name, c.city, c.phone, COALESCE(rb.balance, 0) AS debt FROM customers c LEFT JOIN receivable_balances rb ON rb.customer_id = c.id WHERE 1=1"
    params = {}
    if args.get("city"):
        sql += " AND c.city ILIKE :city"
        params["city"] = "%" + args["city"] + "%"
    if args.get("search"):
        sql += " AND c.name ILIKE :q"
        params["q"] = "%" + args["search"] + "%"
    if args.get("has_debt"):
        sql += " AND COALESCE(rb.balance, 0) > 0"
    sql += " ORDER BY debt DESC NULLS LAST LIMIT :lim"
    params["lim"] = int(args.get("limit", 30))
    return _rows(sql, params)
