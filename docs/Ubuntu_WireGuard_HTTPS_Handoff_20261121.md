# هنداف استقرار پنل کیاراد با Ubuntu، WireGuard، Nginx و HTTPS — ۲۱ نوامبر ۲۰۲۶

> **وضعیت نهایی این نوبت: نیمه‌تمام / نیازمند آزمون دسترسی بیرونی.** گواهی HTTPS و پاسخ HTTP 200 از داخل خود VPS مشاهده شده، اما کاربر گزارش کرده لینک روی دستگاهش باز نمی‌شود. **آن را «منتشرشده و پذیرفته‌شده برای عموم» تلقی نکنید.**

## مبنا و محدودهٔ این گزارش

- این گزارش از خروجی‌های CMD/PowerShell ویندوز و SSH Ubuntu که کاربر در گفت‌وگو ارائه کرده تهیه شده؛ دستیار به میزبان‌ها دسترسی اجرایی مستقیم نداشت.
- این تغییرات مربوط به **پیکربندی در حال اجرای شرکت** هستند، نه انتشار نسخهٔ تازه‌ای از کد مخزن GitHub. هیچ تغییر کد، image، schema یا دادهٔ هلو در این مستندسازی انجام نشده است.
- مخزن GitHub عمومی است: برای امنیت، IP عمومی میزبان، کلیدهای WireGuard، رمزها، محتوای `.env` و سایر اسرار عمداً در این سند ثبت نشده‌اند. آدرس‌های خصوصی در دسترس اپراتور باقی می‌مانند.

## معماری فعلی

مرورگر/گوشی → DNS دامنه → HTTPS:443 در VPS Ubuntu → Nginx reverse proxy → تونل خصوصی WireGuard → Windows portproxy → Docker frontend اصلی روی `127.0.0.1:3300`.

- دامنهٔ پنل: `panel.kiaradhealer.ir`؛ رکورد A آن در سرویس DNS ابر آروان تنظیم شده و `getent ahostsv4` روی Ubuntu، IP مورد انتظار VPS را برگردانده است.
- روش انتخابی **Nginx + WireGuard** است؛ دستورالعمل قدیمی Cloudflare Named Tunnel در `docs/Cloudflare_Permanent_Address_20261117.md` برای این استقرار **اجرا نشده** و مرجع اجرایی فعلی نیست.
- پورت فروشگاه روی ویندوز `127.0.0.1:8190` است، اما انتشار `shop.kiaradhealer.ir` با Nginx/WireGuard **هنوز راه‌اندازی یا تأیید نشده**.
- WireGuard برای مسیر خصوصی استفاده می‌شود؛ Full-tunnel VPN ویندوز و GPS در این نوبت راه‌اندازی نشده‌اند.

## شواهد تأییدشده در ۲۱ نوامبر

### Windows / Docker (پروژهٔ اصلی، نه آزمایشی)

- مسیر فعال: `D:\Kiarad-Stage-20261114`؛ فایل compose: `compose.transfer.yml`؛ نام پروژه: `kiaradstage20261114`.
- فایل compose اصلی ۳۲۳۸ بایت و سالم بود؛ یک فرمان اشتباه قبلی، فایل خالی جداگانه در ریشهٔ درایو C ایجاد کرده بود، **نه** فایل compose اصلی را.
- پس از گرفتن نسخهٔ پشتیبان از compose، binding قدیمی مربوط به IP قبلی LAN حذف شد؛ `ports: ['127.0.0.1:3300:3000']` و `docker compose ... config --quiet` بدون خطا تأیید شدند.
- تنها سرویس `frontend` با `docker compose ... up -d --no-deps --force-recreate frontend` بازسازی شد. مشاهده: `kiaradstage20261114-frontend-1` در وضعیت `healthy`، با انتشار `127.0.0.1:3300->3000/tcp`.
- `curl.exe -I http://127.0.0.1:3300/login` پاسخ `HTTP/1.1 200 OK` داد. این فقط صفحهٔ ورود را تأیید می‌کند.
- بک‌اند `127.0.0.1:8800` با `/health` و فروشگاه `127.0.0.1:8190/buy/` در آزمون‌های قبلی پاسخ موفق داده بودند؛ سلامت و صحت داده‌های هلو در پایان این نوبت مجدداً آزمون end-to-end نشد.
- سرویس `iphlpsvc` فعال (`RUNNING`) بود. قانون Windows portproxy برای گوش‌دادن روی IP خصوصی WireGuard ویندوز و انتقال TCP پورت 3300 به `127.0.0.1:3300` ثبت شد؛ `netsh interface portproxy show v4tov4` این نگاشت را نشان داد.
- قانون Windows Defender Firewall فقط برای دسترسی TCP 3300 از IP خصوصی WireGuard سرور به IP خصوصی WireGuard ویندوز اضافه شد و خروجی `Ok.` دریافت شد. **هیچ پورت عمومی روی ویندوز باز نشده است.**

### Ubuntu / reverse proxy / TLS

- تونل WireGuard پیش‌تر handshake و ping موفق داشت. سپس روی VPS، `curl -I http://<WINDOWS_WG_IP>:3300/login` پاسخ `200 OK` داد.
- `nginx/1.28.3` نصب، سرویس `nginx` در وضعیت `active (running)` و `enabled` بود.
- سایت جدید در `/etc/nginx/sites-available/panel.kiaradhealer.ir` ساخته و در `sites-enabled` فعال شد. `server_name panel.kiaradhealer.ir` با `proxy_pass` به IP خصوصی WireGuard ویندوز و پورت 3300 اشاره می‌کند؛ هدرهای Host / X-Forwarded برای عبور از پراکسی تنظیم شده‌اند.
- `nginx -t` موفق شد؛ پس از reload، `curl -I -H 'Host: panel.kiaradhealer.ir' http://127.0.0.1/login` روی VPS پاسخ `HTTP/1.1 200 OK` از Nginx/Next.js داد.
- Certbot نصب شد (`certbot 4.0.0`). دستور `certbot --nginx -d panel.kiaradhealer.ir --non-interactive --agree-tos --register-unsafely-without-email --redirect` اجرا شد و فرمان زنجیره‌ای پس از آن `curl -I https://panel.kiaradhealer.ir/login` روی همان VPS پاسخ `HTTP/1.1 200 OK` داد. صدور/نصب و موفقیت مسیر HTTPS **از داخل VPS** بر این اساس مشاهده شد.
- `ufw status` برابر `inactive` بود. خروجی `ss -lntp` تأیید کرد Nginx روی `0.0.0.0:80` و `0.0.0.0:443` گوش می‌دهد. این موارد به‌تنهایی بازبودن مسیر از اینترنت بیرونی را ثابت نمی‌کنند.
- Certbot این بار بدون ایمیل ثبت شد؛ برای هشدار انقضای گواهی، ثبت ایمیل معتبر و آزمایش تمدید خودکار لازم است.

## مشکل باز و آخرین نقطهٔ توقف

کاربر اعلام کرد «باز نمیشه». هیچ پاسخ HTTP یا خطای معتبر از **بیرون VPS** هنوز دریافت نشده است. اولین دستور تست از CMD ویندوز به‌اشتباه با `]` اضافی در انتهای URL وارد شد و curl خطای `unmatched close brace/bracket` داد؛ بنابراین آن تست **نامعتبر** است. آخرین اقدام، ارائهٔ دستور صحیح زیر به کاربر بود و خروجی آن هنوز دریافت نشده:

```cmd
curl.exe -Iv --connect-timeout 8 --max-time 15 https://panel.kiaradhealer.ir/login
```

**اقدام بعدی، بدون تغییر پیکربندی:** دستور بالا را در CMD ویندوز خارج از SSH اجرا کنید و خروجی کاملِ بدون دادهٔ حساس را بررسی کنید. همچنین از اینترنت موبایل (Wi‑Fi خاموش) صفحه را تست و **متن دقیق خطا** را ثبت کنید.

راهنمای تفسیر: اگر DNS resolve نمی‌شود، رکوردها/کش resolver بررسی شوند؛ اگر TCP timeout یا connection refused است، firewall/security group پنل VPS و مسیر شبکه/اپراتور بررسی شود؛ اگر خطای TLS است، certificate chain/SNI و زمان دستگاه بررسی شود؛ اگر HTML باز می‌شود اما ورود/درخواست API شکست می‌خورد، مسیرهای Next.js `/api`، headerها و backend را جداگانه بررسی کنید. تست موفق روی خود VPS معادل تأیید بیرونی نیست.

## پذیرش باقی‌مانده

- [ ] تست موفق `curl.exe -Iv` از ویندوز با اینترنت مستقل از VPS و بررسی جزئیات DNS/TCP/TLS/HTTP.
- [ ] بازشدن `https://panel.kiaradhealer.ir/login` روی گوشی با اینترنت سیم‌کارت، بدون خطای گواهی.
- [ ] ورود واقعی با حساب مجاز، بررسی نقش‌ها و درخواست‌های API (بدون درج رمز در لاگ یا چت).
- [ ] آزمایش پاسخ مناسب Next.js پشت reverse proxy، کوکی امن و نبود mixed content.
- [ ] بررسی وضعیت Renew Certbot و ثبت ایمیل هشدار؛ آزمایش `certbot renew --dry-run` در زمان مناسب.
- [ ] تنظیم جداگانهٔ WireGuard/portproxy/firewall/Nginx/SSL برای فروشگاه و آزمون `shop.kiaradhealer.ir`.
- [ ] کنترل بیدارماندن Windows PC، Docker Desktop و WireGuard و راه‌اندازی خودکار پس از reboot.
- [ ] آزمون پس از خاموش/روشن‌شدن با حفظ داده؛ نمونه‌گیری موجودی/قیمت/مالی و وضعیت sync هلو با شواهد تازه.

## احتیاط‌های اجرایی

- تا پیش از اثبات مشکل، compose، کانتینر دیتابیس، volumeها و اتصال هلو را تغییر ندهید. اجرای `docker compose down -v` یا restore بکاپ روی پایگاه زنده ممنوع است.
- نسخهٔ آزمایشی `kiaradtrialc247b02b` **پروژهٔ تولید نیست**؛ از پورت‌های آزمایشی آن برای انتشار عمومی استفاده نکنید.
- اجرای `ssh` باید از CMD ویندوز باشد؛ دستورات `systemctl`, `nginx`, `certbot`, `curl` لینوکسی در نشست SSH Ubuntu اجرا شوند. متن prompt را همراه دستور کپی نکنید.
- برای بازکردن دسترسی عمومی فقط پورت‌های لازم روی VPS را با سیاست مجاز امنیتی تنظیم کنید؛ bind کردن سرویس‌های داخلی Windows به `0.0.0.0` بدون کنترل فایروال توصیه نمی‌شود.
- روی Ubuntu اعلان `System restart required` و به‌روزرسانی‌های معوق دیده شد؛ reboot بدون برنامه‌ریزی و بررسی امکان برگشت تونل/سرویس‌ها انجام نشود.
- مستند `docs/Company_Upgrade_20261116.md` برای نسخهٔ اجرایی `325e0db` و وضعیت قبلی Holoo مرجع است؛ این هنداف جایگزین پذیرش عملیاتی یا نسخه‌گذاری کد نیست.

## وضعیت خلاصه

| بخش | وضعیت تا آخرین خروجی |
|---|---|
| Frontend تولید روی Windows | ✅ Healthy و HTTP 200 در loopback |
| WireGuard → frontend | ✅ HTTP 200 از Ubuntu |
| Nginx vhost پنل | ✅ Syntax و proxy HTTP 200 |
| Certbot و تست HTTPS از خود VPS | ✅ HTTP 200 |
| باز شدن پنل از اینترنت عمومی | ❌ هنوز تأیید نشده / کاربر اعلام عدم دسترسی |
| ورود واقعی و API از گوشی | ⏳ انجام نشده |
| دامنهٔ فروشگاه | ⏳ راه‌اندازی نشده |

**نقطهٔ آغاز جلسهٔ بعد:** گرفتن خروجی دستور `curl.exe -Iv` اصلاح‌شده از CMD ویندوز و متن دقیق خطای گوشی؛ بعد تشخیص DNS/TCP/TLS/HTTP، بدون تغییر DB.
