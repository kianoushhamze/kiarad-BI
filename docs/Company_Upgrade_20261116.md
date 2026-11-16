# ارتقای واقعی سرور شرکت — ۲۵ آبان ۱۴۰۵ / ۱۶ نوامبر ۲۰۲۶

این گزارش بر اساس خروجی PowerShell فرستاده‌شده توسط کاربر است. اجرای مستقیم دستیار روی ویندوز برقرار نیست؛ دستورات در کنسول سرور اجرا شدند.

## نصب و نتیجهٔ مشاهده‌شده

- دستگاه `DESKTOP-TGAKM7L`، Windows PowerShell 5.1، Docker 29.9.2 و Linux/amd64 با containerd snapshotter.
- پروژهٔ Compose همچنان `kiaradstage20261114` و مسیر فعال `D:\Kiarad-Stage-20261114` است.
- نسخه از `2e1c2a0c8f8fa37e87b541ca60d0b56c17cc71f2` به `325e0db7b63a4e5f198e8505117b200be6514bc0` ارتقا یافت؛ خروجی `UPGRADE_OK: 325e0db` مشاهده شد.
- backend و frontend با تصویرهای `r20261113-325e0db7b63a` سالم‌اند؛ storefront نیز Healthy است. PostgreSQL موجود با زمان کارکرد دو روزه حفظ شد؛ dump روی دیتابیس فعال restore نشد.
- پنج HTTP check موفق: API/health، panel/login، panel/api/health، storefront/buy و storefront/api/public/catalog.
- پس از ارتقا، `scripts/check_holoo_login.py` در کانتینر جدید اجرا شد و هر دو `login_ok=true` و `legacy_login_ok=true` مشاهده شدند؛ این مشاهده ورود واقعی را تأیید می‌کند، نه کامل‌بودن منابع یا تطبیق مالی.
- سپس GET احرازشدهٔ `/holoo/status` از پردازش API فعال خوانده شد: `status=completed`، snapshot1581، `finished_at=2026-11-16T09:33:35.714462+00:00`، automatic.enabled=true، automatic.running=true و interval_seconds=300. نوبت بعدی گزارش‌شده `2026-11-16T09:38:14.699807+00:00` بود؛ به وقت تهران پایان دریافت۱۳:۰۳:۳۵ و نوبت بعد۱۳:۰۸:۱۴ است. این شواهد اجرای scheduler در پردازش جدید را نشان می‌دهند؛ دو چرخهٔ متوالی جداگانه در این نوبت اندازه‌گیری نشدند.
- پورت‌ها حفظ شدند: API روی loopback8800، پنل روی loopback3300 و `192.168.1.3:3300`، فروشگاه روی loopback8190.
- کد backend/frontend از تصاویر اجرا می‌شود؛ فایل mounted فروشگاه `site-healer/buy.html` از همان source.zip به‌روز شد. این گزارش ادعای جایگزینی همهٔ فایل‌های سورس host را ندارد.

## صحت بسته و تفاوت شناسهٔ Docker

بسته در `D:\kiarad final\Kiarad-Offline-325e0db7b63a-attempt1` قرار دارد. ابتدا SHA256 فایل checksums.json با digest منتشرشده برابر شد و تمام فایل‌های فهرست‌شده از جمله images.tar بررسی شدند؛ خروجی `PACKAGE_CHECKSUMS_OK` مشاهده شد.

پس از docker load، ID بک‌اند در سرور `sha256:3d03f8541c8a77823f7289afc4b8d84fb3ee3ebe7ce833bd65c69f0f8afdc090` بود؛ ID ثبت‌شده در CI برابر `sha256:afb37816d922966c58b00118097d7cff332724f6d97246df84b04bfee22409e7` بود. مورد اول manifest descriptor و مورد دوم config digest است؛ کنترل صرف .Id میان image storeها معتبر نیست.

هر پنج تصویرِ بارگذاری‌شده با docker save --platform linux/amd64 صادر شدند. config blob هر tag از export خوانده و SHA256 واقعی آن با ID ثبت‌شدهٔ CI مقایسه شد. backend، frontend، PostgreSQL16، Node22 و Traccar6.17.0 همگی VERIFIED و خروجی `ALL_IMAGES_VERIFIED` مشاهده شد. کد تصویری به اتکای برچسب نسخه تنها تأیید نشد.

## بکاپ‌ها و بازگشت

- بکاپ اولیهٔ کامل: `private_exports\release-backups\20261116-112102115`؛ دیتابیس104266892بایت با SHA256 `2999dee4a56e557d728799fdaf4fdfc89c71ada9d8187144cfa67fbb708abd42`.
- بکاپ نهایی پس از توقف سه سرویس برنامه: `private_exports\release-backups\20261116-125201613`؛ دیتابیس105861890بایت با SHA256 `4f60d774994845dd3cf7afed228c4b7022f044439b8302d21bdb75a637baef38`.
- هر دو PostgreSQL16، database=`kiarad_restore` و user=`postgres` را از کانتینر فعال گزارش کردند.
- رسانه: یک فایل، آرشیو198010بایت و SHA256 `e2982ad313baa5dcc10b39bd91c700961075981c43ca350c88dd2a2c6bb00d09`؛ این شمار فقط دو ریشهٔ تعریف‌شده در ابزار بکاپ را پوشش می‌دهد.
- manifest بکاپ contains_env=false است. env، compose، receipt و secrets جداگانه در `private_exports\upgrade-prep\20261116-114122883` محلی حفظ شدند؛ تصاویر قبلی نیز rollback tag دارند.
- snapshot فایل‌های پیش از تعویض در `private_exports\upgrade-prep\20261116-114122883\apply-20261116-125153624` است. dump قدیمی جایگزین ثبت‌های تازه نشود.
- restore واقعی بکاپ‌های امروز و rollback پس از تعویض موفق نسخه در این نوبت اجرا نشده‌اند؛ ساخته‌شدن فایل بکاپ به‌تنهایی آزمون restore نیست.

## سازگاری PowerShell

اجرای فایل ps1 در دستگاه محدود بود؛ اجرای جداگانه با ExecutionPolicy Bypass فقط برای همان پردازش استفاده شد. بکاپ اول در مرحلهٔ ZIP رسانه به‌علت بارگذاری‌نشدن System.IO.Compression متوقف شد. بارگذاری صریح هر دو assembly در همان پردازش، بکاپ اولیه و نهایی را موفق کرد. اصلاح دائمی ابزارها باید این assembly را صریحاً بارگذاری کند.

اولین فرمان تعویض سرویس به‌علت تکرار compose در wrapper اجرا نشد. دستور اصلاح‌شده اجرا شد و ارتقای بالا موفق بود؛ شکست اولیهٔ قبل از stop، شاهد آزمون rollback عملی نیست.

## پذیرش باقی‌مانده

ورود هلو، پایان موفق دریافت و running بودن scheduler در پردازش جدید مشاهده شدند. تطبیق دستی چند نمونهٔ مالی/قیمت/موجودی، ورود و نقش انسانی، سفارش کنترل‌شده، نمایش رسانه، دسترسی واقعی از سرفیس/تونل، GPS گوشی و restart/rollback با حفظ داده هنوز پذیرش جدا دارند. نتیجهٔ فنی بالا، پذیرش کامل عملیاتی شرکت نیست.
