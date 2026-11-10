# راهنمای دامنه + کلادفلر تانل — شرکت پخش کیاراد شفا اندیش

هدف: بعد از خرید دامنه، در کمتر از ۳۰ دقیقه این دو آدرس از **هر جای ایران** باز شوند:

| آدرس | چیست | میزبان | پورت محلی |
|---|---|---|---|
| `panel.[دامنه]` | داشبورد کیاراد BI | PC دفتر (فرانت standalone) | 3100 |
| `shop.[دامنه]` | سایت KiaradHealer (ویترین ۱۰ برند + پرتال همکاران) | PC دفتر | 8090 |

هزینهٔ ماهانه: **صفر** (پلن رایگان کلادفلر) — هیچ پورتی روی مودم باز نمی‌شود؛ از CGNAT ایرانسل رد می‌شود.

## قدم ۱ — خرید دامنه (کارفرما)
`kiaradshafa.ir` یا `kiaradco.ir` (kiarad.com آزاد نیست) — به نام خود کارفرما. اسم دامنه را به دستیار بفرستد تا CORS/آدرس API آماده شود.

## قدم ۲ — دامنه → کلادفلر
حساب رایگان در dash.cloudflare.com → Add a site → پلن Free → دو Nameserver را در پنل رجیسترار جایگزین کن تا وضعیت Active شود.

## قدم ۳ — اجرای اسکریپت روی PC دفتر
```
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\cloudflare\kiarad_cloudflare_setup_v1.ps1
```
(نصب cloudflared + لاگین مرورگری + تانل kiarad + رکوردهای panel/shop + سرویس ویندوزی همیشه‌روشن)

## قدم ۴ — بالا آوردن دو سرویس محلی
```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-kiaradhealer-site.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File D:\project\kiaradbi\start-kiarad-frontend.ps1
```

## قدم ۵ — تست
از اینترنت موبایل (نه وای‌فای دفتر): `https://panel.[دامنه]` و `https://shop.[دامنه]` — HTTPS سبز = موفق.

## نکته‌ها
- قطع برق دفتر = قطع موقت هر دو آدرس (داده‌ها لوکال می‌مانند؛ درمان: UPS).
- اختلال بین‌الملل ممکن است تونل را کند کند؛ داخل دفتر کار با IP داخلی همیشه برقرار است. راهکار بعدی در صورت نیاز: VPS ایرانی بدون تغییر دامنه.
- برای پنل می‌شود Cloudflare Access (ورود ایمیل، ۵۰ کاربر رایگان) فعال کرد.
- سفارش‌های سایت فعلاً در مرورگر بایگانی می‌شوند (`kiarad_healer_orders`) + پیش‌فاکتور چاپی؛ اتصال به داشبورد: مقدار `window.KIARAD_API_URL` در `site-healer/index.html` → endpoint `/site-orders`.
