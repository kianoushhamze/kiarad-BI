# کیاراد BI — سامانه هوش تجاری و اتوماسیون پخش کیاراد شفا اندیش

![CI](https://github.com/kianoushhamze/kiarad-BI/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688)
![Next.js](https://img.shields.io/badge/frontend-Next.js%2016-black)
![PostgreSQL](https://img.shields.io/badge/db-PostgreSQL%2016-336791)

سامانه جامع مدیریت، هوش تجاری و اتوماسیون شرکت **پخش کیاراد شفا اندیش** (کرمان) — پخش مویینه محصولات پوست، مو و مزوتراپی (Swalin Vira، Dermalist، Total Derm، MC Cosmetics).

پنل مدیریت فارسی (RTL) با دستیار هوشمند همه‌دانه، یکپارچه‌سازی کامل با **هلو (Holoo ERP)** و **دیجی‌کالا**، مدیریت تیم فروش میدانی و ویزیت‌ها، خزانه و چک‌ها، حقوق و جبران خدمات، سایت عمومی فروش (Ordibeauty) و موجودی مجازی چندسکویی.

> **وضعیت پروژه:** مخزن داخلی شرکت. آخرین شمار رسمی آزمون: ۷۰۱ مورد (۵۲۰ پاس، ۱۸۱ skip، صفر شکست) در زیرمجموعهٔ آفلاین. تأیید شروع بهره‌برداری کامل سرور هنوز صادر نشده است — جزئیات در [`HANDOFF.md`](HANDOFF.md) و [`docs/Delivery_20261108.md`](docs/Delivery_20261108.md).

---

## پشته فنی

| لایه | فناوری |
|---|---|
| بک‌اند | Python 3.12 · FastAPI · SQLAlchemy · PyJWT · pandas |
| پایگاه داده | PostgreSQL 16 (پورت ۵۴۳۲، تایم‌زون تهران) |
| فرانت‌اند | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS 4 · فارسی RTL |
| هوش مصنوعی | AvalAI (GPT) برای دستیار · Faster-Whisper برای گزارش صوتی |
| یکپارچه‌سازی | وب‌سرویس هلو (Holoo ERP) · گیت فروشندگی دیجی‌کالا · ربات تلگرام |
| استقرار | Docker Compose (postgres + backend + frontend + pgAdmin) |

## معماری کلی

```
┌─────────────────┐   ┌──────────────────┐   ┌────────────────┐
│  kiarad-dashboard│   │  بک‌اند FastAPI   │   │  PostgreSQL 16 │
│  Next.js :3000  │──▶│   api.py :8000   │──▶│   db.py        │
│  فارسی RTL      │   │  ۲۱۹ مسیر API    │   │  ۲۴ جدول       │
└─────────────────┘   └────────┬─────────┘   └────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        هلو (Holoo)      دیجی‌کالا         AvalAI (GPT)
        وب‌سرویس ERP      گیت فروشنده        دستیار هوشمند
```

- **بک‌اند:** ساختار فلت در ریشه؛ همهٔ روترها در `api.py` رجیستر می‌شوند (`operations.py` احراز هویت و نقش‌ها، `treasury.py` خزانه و چک‌ها، `assistant_engine.py` موتور دستیار و BI).
- **فرانت‌اند:** پنل تاریک بنفش با شِل مشترک `kiarad-dashboard/components/portal-shell.tsx`، پالت فرمان Ctrl+K، و حدود ۴۰ صفحه در `kiarad-dashboard/app/`.
- **مستندات زمینه‌ای:** [`GEMINI.md`](GEMINI.md) خلاصهٔ معماری برای عامل‌های کدنویس است.

## ماژول‌های اصلی

| حوزه | ماژول‌های کلیدی | توضیح |
|---|---|---|
| فروش میدانی | `monthly_visit_plans.py` · `route_builder.py` · `reconciliation_engine.py` · `field_intelligence.py` | برنامهٔ ماهانهٔ ویزیت، مسیرسازی خودکار، تطبیق ۴گانهٔ پایان ماه، هوش میدانی |
| مالی | `treasury*.py` (۵ ماژول) · `payroll_*.py` · `compensation.py` · `purchase_profit.py` | خزانه و چک‌ها، موتور حقوق، جبران خدمات، سود خرید |
| دستیار هوشمند | `assistant_engine.py` · `assistant_automations.py` · `assistant_*.py` · `ai_knowledge/` | چت داده‌محور با ۸۷ منبع پنل، ایجنت خودکار زمان‌بندی‌شده، پرامپت‌های نقش‌محور |
| انبار و کالا | `catalog.py` · `inventory_intelligence.py` · `product_pricing.py` | کاتالوگ، هوش موجودی، قیمت‌گذاری |
| یکپارچه‌سازی | `holoo_*.py` (۱۰+ ماژول) · `digikala_api.py` · `platform_sync.py` | سینک هلو، گیت دیجی‌کالا، موجودی مجازی چندسکویی |
| فروش آنلاین | `site_*.py` · `site/` · `site_cms.py` | سایت عمومی Ordibeauty، CMS، سفارش‌ها با رزرو اتمیک |
| بازاریابی | `marketing_intel.py` · `campaign_ai.py` · `integrations.py` | سؤالات پرتکرار پوست/مو، لیدها، تقویم محتوا |
| پشتیبانی | `voice_reports.py` · `telegram_bot.py` · `audit_panel.py` | گزارش صوتی، ربات تلگرام، ممیزی |

## راه‌اندازی سریع (Docker Compose)

### ۱) تنظیمات محیطی

```bash
cp .env.example .env
```

سپس در `.env` حداقل این مقادیر را کامل کنید:

```dotenv
KIARAD_JWT_SECRET=<رشتهٔ تصادفی حداقل ۳۲ کاراکتری>
POSTGRES_PASSWORD=<رمز یکتای دیتابیس>
HOLO_API_URL=http://<IP رایانهٔ هلو>:8080/TncHoloo/api
HOLO_USERNAME=web
HOLO_PASSWORD=<رمز وب‌سرویس هلو>
```

### ۲) بالا آوردن استک

```bash
docker compose up -d --build
```

| سرویس | نشانی |
|---|---|
| فرانت‌اند | `http://127.0.0.1:3000` |
| بک‌اند (health) | `http://127.0.0.1:8000/health` |
| pgAdmin (اختیاری) | `docker compose --profile tools up -d pgadmin` → پورت ۵۰۵۰ |

### ۳) دیتابیس تازه و اولین مدیر

- مهاجرت پایه: [`migrations/0001_baseline.sql`](migrations/0001_baseline.sql) با [`scripts/run_migrations.py`](scripts/run_migrations.py) — راهنمای [`migrations/README.md`](migrations/README.md).
- در صورت نیاز به تکمیل شِما روی دیتابیس نو: `fix_missing_tables.py`.
- ساخت اولین کاربر مدیر: `create_admin.py` را داخل کانتینر بک‌اند اجرا کنید.

ترتیب دقیق استقرار روی سرور واقعی در [`docs/Server_Deployment_Runbook_20261101.md`](docs/Server_Deployment_Runbook_20261101.md) و [`docs/server-deployment.md`](docs/server-deployment.md) آمده است.

## اجرای آزمون‌ها

```bash
pip install -r requirements.txt

# زیرمجموعهٔ آفلاین (بدون PostgreSQL/شبکه — همان اجرای CI)
python scripts/run_offline_review_tests.py
```

مجموعهٔ کامل و گروه‌های دیتابیس فقط در محیط واقعی اجرا می‌شوند (اسکریپت‌های `run_full_test_suite.ps1` و `run_full_system_test.py`). تست‌های opt-in دیتابیس با متغیرهای `KIARAD_TEST_*_DB` فعال می‌شوند؛ رانر آفلاین آن‌ها را عمداً نادیده می‌گیرد.

## ساختار مخزن

```
├── api.py                  # نقطهٔ ورود FastAPI و رجیستری روترها
├── *.py                    # ~۱۱۵ ماژول بک‌اند (۳۶ هزار خط)
├── kiarad-dashboard/       # فرانت‌اند Next.js 16 (۷ هزار خط TSX/TS)
│   ├── app/                # صفحات پنل (App Router)
│   ├── components/         # portal-shell، command-palette و…
│   └── lib/                # secure-api و ابزارهای مشترک
├── site/                   # سایت عمومی Ordibeauty (استاتیک + API زنده)
├── ai_knowledge/           # پرامپت‌های نقش‌محور دستیار (CFO، CEO، انبار…)
├── migrations/             # مهاجرت پایهٔ اسکیما
├── scripts/                # ابزارهای عملیاتی، رانرها و چک‌های انتشار
├── tests/                  # ۷۶ فایل آزمون unittest
├── docs/                   # ۴۵ سند تحویل، دیباگ و RUNBOOK
├── templates/              # قالب ورود اکسل خزانه
└── docker-compose.yml      # استک کامل production
```

## متغیرهای محیطی

| متغیر | نقش |
|---|---|
| `KIARAD_JWT_SECRET` | سکرت امضای توکن‌های JWT (حداقل ۳۲ کاراکتر) |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` | اتصال PostgreSQL |
| `POSTGRES_PASSWORD` | رمز دیتابیس |
| `HOLO_API_URL` / `HOLO_USERNAME` / `HOLO_PASSWORD` | وب‌سرویس هلو |
| `HOLO_AUTO_REFRESH_ENABLED` / `HOLO_AUTO_REFRESH_SECONDS` | سینک خودکار هلو (پیش‌فرض فعال، هر ۳۰۰ ثانیه) |
| `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD` | pgAdmin (پروفایل tools) |

توکن‌های دیجی‌کالا و سایر اعتبارنامه‌ها در پوشهٔ `secrets/` نگهداری می‌شوند و هرگز وارد مخزن نمی‌شوند (در `.gitignore` مستثنا شده است).

## امنیت و انتشار

- تفکیک نقش‌ها: `ceo` دسترسی جامع؛ `salesperson` فقط پیش‌نویس و مسیر اختصاصی خود؛ مسیرهای عمومی فقط دو endpoint کاتالوگ فقط‌خواندنی.
- آزمون دسترسی نقش‌ها در `tests/` پوشش داده شده است (صفر نشتی در سوییپ‌های ثبت‌شده).
- پیش از هر عمومی‌سازی این مخزن: محدودکردن CORS از `*` به دامنهٔ واقعی، رتبه‌بندی درخواست در `public_proxy.py`، و بازبینی ۱۰ فایل حاوی IP داخلی هلو انجام شود.

## CI

Workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) روی هر push و pull request دو شغلی اجرا می‌کند:

1. **backend-offline-tests** — نصب `requirements.txt` و اجرای زیرمجموعهٔ آفلاین (`scripts/run_offline_review_tests.py`).
2. **frontend-build** — `npm ci`، بررسی نوع TypeScript و بیلد تولیدی Next.js.

## مجوز

مخزن داخلی شرکت؛ بدون لایسنس متن‌باز. تمام حقوق برای **شرکت پخش کیاراد شفا اندیش** محفوظ است.
