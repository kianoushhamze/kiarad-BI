## ۱۴) طرح انتقال به سرور شرکت

> **یادداشت بازبینی ۱ نوامبر ۲۰۲۶:** این طرح هنوز اجرا نشده و بعضی فرض‌های آن، از جمله مسیر لینوکسی `/opt/kiaradbi`، وجود `deploy.ps1` و مایگریشن‌های آماده، با وضعیت واقعی پروژه سازگار نیست. مرجع به‌روز و راستی‌آزمایی‌شده: `docs/Kiarad_Handoff_Master_20261101.md`.

**وضعیت:** ثبت‌شده ۱ نوامبر ۲۰۲۶ — اجرا بعد از تکمیل پروژه.

### ۱۴.۱ تصمیم معماری

- **لپ‌تاپ** (100.95.236.49): محیط توسعه. DB محلی. Serve ندارد.
- **سرور شرکت** (100.67.20.31): محیط تولید. DB اصلی. Tailscale Serve روی :3000.
- **کاربران**: همان URL kiarad.taile287ae.ts.net — بدون تغییر.
- **قاعده طلایی**: سرور مستقیم ویرایش نمی‌شود. فقط git pull.

### ۱۴.۲ جریان کار — Git push/pull

لپ‌تاپ: git add . → git commit → git push
سرور: cd /opt/kiaradbi → git pull → .\deploy.ps1

مخزن: GitHub **private** (پروژه شامل .env است).

### ۱۴.۳ استراتژی دیتابیس

| محیط | DB | داده |
|------|-----|------|
| لپ‌تاپ | kiaradbi محلی | تست |
| سرور | kiaradbi اصلی | منبع حقیقت |

تغییرات schema: همیشه migration در پوشه migrations/. deploy.ps1 اجرا می‌کند.

### ۱۴.۴ پیش‌نیازها

**سرور شرکت:**
1. Tailscale آنلاین و لاگین
2. Docker Desktop نصب
3. Git نصب
4. حداقل 30 GB فضای دیسک
5. SSH یا PowerShell Remoting

**لپ‌تاپ قبل از انتقال:**
1. pg_dump از همه 71+ جدول
2. پشتیبان D:\project\kiaradbi
3. پشتیبان product_media و پیوست‌ها
4. تست بازیابی روی DB موقت
5. لیست تسک‌ها: Get-ScheduledTask *Kiarad*
6. باطل/تعویض دو کلید افشاشده
7. رمز اختصاصی 6 پرسنل

### ۱۴.۵ گام‌های انتقال

1. آماده‌سازی سرور: Docker + Tailscale + Git + دیسک
2. مخزن Git: GitHub private، اولین push
3. اولین pull روی سرور: git clone + .env دستی
4. بازیابی DB: pg_restore
5. اجرا: docker compose up -d + backend + frontend
6. Tailscale Serve روی سرور: tailscale serve --bg 3000
7. خاموش کردن Serve لپ‌تاپ: tailscale serve reset
8. تست از گوشی: همان URL، همان 6 حساب
9. پایش 24 ساعت: لاگ‌ها، health، sync
10. تأیید نهایی: لپ‌تاپ به توسعه برمی‌گردد

### ۱۴.۶ تسک‌های بازسازی روی سرور

| TaskName | فرکانس | توضیح |
|----------|--------|-------|
| KiaradHolooCatalogSync | هر ساعت | python holoo_auto_sync.py --once |
| KiaradHolooInvoiceSync | روزانه | معیوب (LastResult=3) — قبل از انتقال اصلاح |
| KiaradDigikalaSync | هر 30 دقیقه | UA سه‌بخشی |
| KiaradDailyProformaExport | روزانه 8:00 | CSV روز قبل |
| KiaradStackRecovery | بوت/دوره‌ای | بازیابی سرویس‌ها |
| KiaradPublicProxy | دائمی | پراکسی |

مسیرها ممکن است فرق کنند (C:\kiaradbi به‌جای D:\project\kiaradbi).

### ۱۴.۷ فایل‌های انتقال

| فایل | روش |
|------|------|
| کد (*.py, *.tsx, *.ps1) | Git |
| .env | دستی SCP، نه Git |
| private_exports/ | SCP |
| backups/staff-roster/ | SCP |
| site/data.json | Git یا SCP |
| DB dump | pg_dump → SCP → pg_restore |
| product_media/ | SCP |
| پیوست‌های چت | SCP |

### ۱۴.۸ ریسک‌ها

| ریسک | کاهش |
|------|------|
| فراموش کردن git pull | deploy.ps1 با health check |
| Migration نبودن | همه schema تغییرات با migration |
| .env در Git | .gitignore + بازبینی |
| دیباگ روی DB تولید | فقط از DB محلی |
| دو Tailscale Serve فعال | tailscale serve reset روی لپ‌تاپ |
| قطع برق سرور | UPS + BIOS Restore on AC Power Loss = On |
| Windows Update ری‌استارت | Active Hours 8am-10pm |
| خواب/هایبرنیت | Power settings → Never |

### ۱۴.۹ با انتقال منتقل می‌شود (بدون کار)

- دسترسی‌ها (کد در backend)
- 6 حساب پرسنل + مدیرعامل
- رمزها (hash در DB)
- داده‌های هلو/دیجی‌کالا

### ۱۴.۱۰ باید دوباره تنظیم شود

- تسک‌های زمان‌بندی ویندوز
- Tailscale Serve
- .env (کپی دستی)
- مسیرهای پروژه (اگر فرق کرد)

### ۱۴.۱۱ جریان روزمره بعد از انتقال

**تغییر کوچک:** لپ‌تاپ git push → سرور .\deploy.ps1 (30 ثانیه)
**تغییر بزرگ:** لپ‌تاپ توسعه+تست → push → سرور pull+deploy
**تغییر DB:** migration → push → سرور pull+deploy

### ۱۴.۱۲ وضعیت فعلی

- **لپ‌تاپ = سرور موقت** — باید 24/7 روشن بماند
- **سرور شرکت = آفلاین** — Tailscale، Docker، Git نیاز به راه‌اندازی
- **پرسنل** با همان محدودیت‌ها از هر دستگاهی وصل می‌شوند
- **همه کارها** روی لپ‌تاپ ادامه می‌یابد تا لحظه انتقال

---

*این سند بخشی از هنداف مادر است. قبل از انتقال دوباره مرور شود.*
