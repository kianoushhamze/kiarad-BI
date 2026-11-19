# راهنمای اتصال Kiarad BI به VPS آروان پشت NAT — ۱۹ نوامبر ۲۰۲۶

> **وضعیت: مستند آماده‌سازی؛ هنوز هیچ تغییری روی DNS، VPS یا سرور شرکت اعمال نشده است.**
>
> این راهنما براساس وضعیت ثبت‌شده در گفتگو و فایل‌های جاری مخزن تهیه شده است. اجرای هر مرحله باید با خروجی واقعی همان مرحله تأیید شود.

## ۱. وضعیت تأییدشده

### دامنه و زیرساخت
- دامنه: `kiaradhealer.ir`
- ثبت‌کننده دامنه: هاست ایران (HostIran)
- VPS واسط: ابر آروان (ArvanCloud)
- سرور اصلی شرکت: Windows، پشت NAT و بدون IPv4 عمومی؛ اتصال ورودی مستقیم از اینترنت ندارد.
- VPS: Ubuntu 26.04 LTS، یک vCPU، حدود 956 MiB RAM، دیسک 23 GB.
- رابط شبکه VPS: `eth0`
- IPv4 عمومی گزارش‌شده در کنسول: `37.32.8.23`
- Gateway گزارش‌شده: `37.32.8.1`
- اینترنت VPS و ping به `1.1.1.1` در زمان بررسی موفق بوده است.
- ورود تعاملی با کاربر `root` موفق بوده است.

**محرمانگی:** URL کنسول VNC در یکی از تصاویر قبلی دارای token نشست بوده است. آن URL را بازنشر نکنید؛ نشست VNC را ببندید و در صورت امکان از پنل یک نشست تازه بسازید. رمز root، کلید خصوصی WireGuard/SSH و API Token نباید در Git یا گفتگو ثبت شوند.

### وضعیت نصب روی VPS
در زمان ثبت این سند، فقط سیستم‌عامل و شبکه بررسی شده‌اند. نصب یا فعال‌سازی SSH، WireGuard، Nginx، گواهی TLS، DNS، فایروال و تونل هنوز تأیید نشده است. پیش از اجرای نصب، وضعیت بسته‌ها و سرویس‌ها دوباره بررسی شود.

### نسخه برنامه شرکت
گزارش ارتقای شرکت در `docs/Company_Upgrade_20261116.md` نسخه `325e0db` را روی نصب شرکت ثبت می‌کند:
- پنل روی loopback پورت 3300
- API روی loopback پورت 8800
- فروشگاه روی loopback پورت 8190
- Traccar اختیاری روی loopback پورت 5055
- Compose انتقال، backend را روی `127.0.0.1:8800`، پنل را روی `127.0.0.1:3300`، فروشگاه را روی `127.0.0.1:8190` و Traccar را روی `127.0.0.1:5055` منتشر می‌کند.

نسخه نصب‌شده شرکت را با HEAD فعلی Git یا بسته‌های بعدی یکی فرض نکنید. برای هر انتقال، `source_commit` و manifest همان بسته باید تطبیق داده شود.

## ۲. معماری هدف

دامنه در HostIran باقی می‌ماند و DNS آن در حال حاضر می‌تواند همان‌جا مدیریت شود. VPS آروان نقطه ورودی عمومی است. سرور شرکت اتصال WireGuard را از داخل شبکه به VPS آغاز می‌کند؛ بنابراین به IP عمومی یا Port Forward روی مودم شرکت نیاز نیست.

```text
کاربر اینترنت
    |
    | HTTPS :443
    v
DNS دامنه در HostIran
    |
    v
ArvanCloud VPS (37.32.8.23)
    |  Nginx :443
    |  WireGuard :51820/UDP
    |
    |  تونل رمزگذاری‌شده: 10.77.0.0/24
    v
Windows Server شرکت (10.77.0.2)
    |-- TCP 13300 -> 127.0.0.1:3300  پنل
    |-- TCP 18190 -> 127.0.0.1:8190  فروشگاه
    |-- TCP 15055 -> 127.0.0.1:5055  GPS، فقط پس از راه‌اندازی
    |
    +-- API :8800 و PostgreSQL :5432 عمومی نمی‌شوند
```

مسیرهای عمومی هدف:
- `https://panel.kiaradhealer.ir` → پنل
- `https://shop.kiaradhealer.ir` → فروشگاه
- `https://gps.kiaradhealer.ir` → GPS، اختیاری و فقط پس از راه‌اندازی و پذیرش Traccar

VPS فقط Relay و Reverse Proxy است. دیتابیس، API و برنامه اصلی روی سرور شرکت باقی می‌مانند.

## ۳. محدودیت منابع VPS

VPS فعلی فقط حدود 1 GiB RAM دارد. WireGuard و Nginx سبک‌اند، اما به‌روزرسانی سیستم، صدور گواهی و بار هم‌زمان ممکن است حافظه را محدود کند. پیشنهاد عملیاتی:
- در صورت امکان، پیش از انتشار عمومی RAM را به 2 GiB افزایش دهید.
- اگر ارتقا ممکن نیست، فقط WireGuard و Nginx را اجرا کنید؛ روی VPS Docker، PostgreSQL، پنل یا برنامه اصلی نصب نکنید.
- پیش از نصب، `free -h`، `df -h /` و `systemctl --failed` را ثبت کنید.
- Ubuntu 26.04 در تصویر سرور دیده شده است؛ دستورات نصب باید با مخازن همین نسخه بررسی شوند. نسخه سیستم‌عامل را صرفاً برای تطبیق با راهنما downgrade نکنید.

## ۴. DNS دامنه در HostIran

تا زمانی که CDN آروان جداگانه فعال و Nameserverهای اختصاصی آن در اختیار نیستند، DNS را در HostIran نگه دارید. پس از تأیید Nginx و آماده‌بودن VPS، رکوردهای زیر را در DNS Zone هاست ایران ایجاد یا اصلاح کنید:

| Type | Name/Host | Value | توضیح |
|---|---|---|---|
| A | `panel` | `37.32.8.23` | پنل |
| A | `shop` | `37.32.8.23` | فروشگاه |
| A | `gps` | `37.32.8.23` | فقط پس از پذیرش GPS |
| A یا ALIAS | `@` | `37.32.8.23` | فقط اگر دامنه ریشه هم باید به VPS برود |
| CNAME یا A | `www` | مطابق سیاست دامنه ریشه | پس از تعیین مقصد وب‌سایت |

- TTL اولیه 300 ثانیه مناسب است، اگر پنل ارائه می‌کند.
- رکوردهای MX، TXT، SPF، DKIM، DMARC و رکوردهای تأیید مالکیت را حذف یا جایگزین نکنید.
- رکورد AAAA نسازید مگر IPv6 واقعاً روی VPS و Nginx پیکربندی شده باشد.
- ابتدا فقط `panel` و `shop` را پس از آماده‌شدن مبدأ منتشر کنید؛ GPS را جداگانه فعال کنید.
- مقدار IP باید از پنل VPS مجدداً تأیید شود؛ IP بالا از خروجی کنسول کاربر ثبت شده است.

## ۵. WireGuard — طرح آدرس‌دهی

شبکه خصوصی پیشنهادی: `10.77.0.0/24`

| سمت | Tunnel IP |
|---|---|
| VPS آروان | `10.77.0.1/24` |
| Windows شرکت | `10.77.0.2/32` |

VPS:
- UDP پورت 51820 روی اینترنت دریافت می‌کند.
- Peer ویندوز فقط `10.77.0.2/32` را مجاز می‌کند.

Windows:
- اتصال به `<ARVAN_VPS_PUBLIC_IP>:51820` را آغاز می‌کند.
- `PersistentKeepalive = 25` برای حفظ mapping پشت NAT تنظیم می‌شود.
- AllowedIPs سمت ویندوز فقط `10.77.0.1/32` است؛ تمام ترافیک اینترنت ویندوز از تونل عبور نمی‌کند.

نمونه مفهومی `/etc/wireguard/wg0.conf` روی VPS (کلیدها باید روی دستگاه ساخته شوند و هرگز در Git قرار نگیرند):

```ini
[Interface]
Address = 10.77.0.1/24
ListenPort = 51820
PrivateKey = <VPS_PRIVATE_KEY>

[Peer]
PublicKey = <COMPANY_PUBLIC_KEY>
AllowedIPs = 10.77.0.2/32
```

نمونه مفهومی کانفیگ WireGuard ویندوز:

```ini
[Interface]
Address = 10.77.0.2/32
PrivateKey = <COMPANY_PRIVATE_KEY>

[Peer]
PublicKey = <VPS_PUBLIC_KEY>
Endpoint = <ARVAN_VPS_PUBLIC_IP>:51820
AllowedIPs = 10.77.0.1/32
PersistentKeepalive = 25
```

کلیدهای خصوصی را فقط با ابزار WireGuard روی همان دستگاه تولید کنید. کانفیگ کامل حاوی PrivateKey نباید در مخزن، پیام، تصویر یا فایل اشتراکی قرار گیرد.

## ۶. Windows PortProxy — فقط پس از برقراری تونل

این مرحله شنبه و روی سرور شرکت انجام می‌شود. ابتدا باید WireGuard handshake موفق و مسیر `10.77.0.1` قابل دسترسی باشد.

پیش‌نیاز:
- Windows service `iphlpsvc` فعال باشد.
- پورت‌های مقصد محلی 3300 و 8190 روی سرور شرکت سالم باشند.
- Windows Firewall دسترسی ورودی فقط از `10.77.0.1` به پورت‌های تونلی را اجازه دهد.

نگاشت پیشنهادی:

| Listen address | Listen port | Connect address | Connect port |
|---|---:|---|---:|
| `10.77.0.2` | 13300 | `127.0.0.1` | 3300 |
| `10.77.0.2` | 18190 | `127.0.0.1` | 8190 |
| `10.77.0.2` | 15055 | `127.0.0.1` | 5055 |

GPS mapping را تا زمانی که Traccar طبق `transfer/07-Configure-Traccar.ps1` با URL عمومی HTTPS پیکربندی و تست نشده، ایجاد نکنید.

نمونه فرمان‌ها برای دو سرویس اصلی (پس از تأیید WireGuard و آزادبودن پورت‌ها):

```powershell
Set-Service iphlpsvc -StartupType Automatic
Start-Service iphlpsvc

netsh interface portproxy add v4tov4 listenaddress=10.77.0.2 listenport=13300 connectaddress=127.0.0.1 connectport=3300
netsh interface portproxy add v4tov4 listenaddress=10.77.0.2 listenport=18190 connectaddress=127.0.0.1 connectport=8190
```

قانون فایروال باید فقط RemoteAddress برابر `10.77.0.1` و LocalAddress برابر `10.77.0.2` را برای TCP پورت‌های 13300 و 18190 مجاز کند. هیچ پورت عمومی روی مودم شرکت باز نشود.

## ۷. Nginx روی VPS

Nginx روی VPS به پورت‌های تونلی ویندوز Proxy می‌کند:
- `panel.kiaradhealer.ir` → `http://10.77.0.2:13300`
- `shop.kiaradhealer.ir` → `http://10.77.0.2:18190`
- `gps.kiaradhealer.ir` → `http://10.77.0.2:15055` فقط پس از پذیرش GPS

در هر Virtual Host:
- `Host`، `X-Forwarded-For` و `X-Forwarded-Proto` درست تنظیم شوند.
- برای پنل و فروشگاه Cache عمومی خاموش باشد؛ به‌ویژه login، سفارش و API.
- اندازه درخواست پنل با نیاز upload واقعی هماهنگ شود؛ فروشگاه JSON کوچک می‌پذیرد.
- WebSocket فقط در صورت نیاز واقعی پنل Proxy شود.
- GPS به‌علت ماهیت دستگاه‌ها و پروتکل آن، تنظیم جداگانه و بدون چالش مرورگری/JS لازم دارد؛ Nginx HTTP reverse proxy به‌تنهایی پورت‌های پروتکل دستگاه Traccar را پوشش نمی‌دهد.

نمونه حداقلی پنل (گواهی و مسیر گواهی پس از صدور تنظیم شود):

```nginx
server {
    listen 443 ssl;
    server_name panel.kiaradhealer.ir;

    ssl_certificate     /etc/letsencrypt/live/panel.kiaradhealer.ir/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.kiaradhealer.ir/privkey.pem;

    location / {
        proxy_pass http://10.77.0.2:13300;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
}
```

برای فروشگاه یک server block جدا با `server_name shop.kiaradhealer.ir` و `proxy_pass http://10.77.0.2:18190` بسازید. برای GPS قبل از تعیین نیاز واقعی Traccar و پروتکل دستگاه، server block عمومی فعال نکنید.

## ۸. TLS و CDN آروان

دامنه در HostIran ثبت شده و خرید VPS از آروان به معنی فعال بودن CDN آروان نیست.

مسیر ساده فعلی:
1. DNS A در HostIran به IP VPS اشاره کند.
2. پورت‌های 80 و 443 روی VPS باز باشند.
3. گواهی Let's Encrypt روی Nginx با HTTP-01 صادر شود؛ در این حالت نیاز به Arvan API Token نیست.
4. HTTP به HTTPS redirect شود و تمدید خودکار گواهی بررسی شود.

اگر بعداً CDN آروان فعال شد:
- دامنه را در سرویس CDN آروان اضافه کنید.
- فقط Nameserverهای دقیقاً اعلام‌شده در پنل آروان را در HostIran ثبت کنید.
- قبل از تغییر NS، همه رکوردهای وب و ایمیل را به‌طور کامل در DNS آروان بازسازی و کنترل کنید.
- TLS کاربر تا Edge و TLS Edge تا VPS هر دو فعال و معتبر باشند؛ حالت ارتباط مبدأ باید HTTPS و اعتبارسنجی گواهی روشن باشد.
- IPهای مبدأ/Proxy و تنظیمات client IP فقط از مستندات جاری آروان گرفته شوند؛ IP range حدسی یا قدیمی در Nginx/Firewall وارد نشود.
- CDN برای پنل، سفارش، نشست و API باید Cache bypass داشته باشد. GPS و درخواست‌های دستگاهی را تا زمان تست سازگاری از CDN عبور ندهید یا مسیر اختصاصی تعریف کنید.

## ۹. فایروال

### VPS
- TCP 22: فقط IP مدیریت مورداعتماد؛ در صورت نامشخص بودن IP، موقتاً فقط تا تکمیل نصب و سپس محدود شود.
- TCP 80: برای HTTP-01 و redirect HTTPS.
- TCP 443: سرویس عمومی HTTPS.
- UDP 51820: WireGuard.
- همه پورت‌های دیگر ورودی بسته باشند.
- SSH با کلید عمومی و کاربر مدیریتی غیر root تأیید شود، سپس ورود Password و root از راه دور غیرفعال شود. پیش از تأیید نشست دوم SSH این تغییر را انجام ندهید.

### شرکت
- هیچ Port Forward روی مودم.
- ورودی Windows فقط روی Interface تونل و از peer تونل.
- PostgreSQL 5432 و Backend 8800 از اینترنت و از VPS در دسترس قرار نگیرند.
- دسترسی مستقیم RDP عمومی ایجاد نشود.

## ۱۰. چک‌لیست اجرا و پذیرش

### آماده‌سازی خارج از شرکت
- [ ] ساخت SSH key روی Surface و افزودن public key به کاربر مدیریتی VPS.
- [ ] تست SSH از Surface؛ نگه‌داشتن کنسول آروان تا پایان تست.
- [ ] بررسی فضای RAM و ارتقای VPS به 2 GiB در صورت امکان.
- [ ] نصب و فعال‌سازی OpenSSH Server، WireGuard و Nginx.
- [ ] تولید کلیدهای WireGuard در VPS و ذخیره امن PublicKey/PrivateKey هر دستگاه.
- [ ] آماده‌سازی کانفیگ WireGuard VPS و Windows، بدون نصب سمت Windows تا شنبه.
- [ ] دریافت اسکرین‌شات DNS و Nameserver فعلی از HostIran؛ هیچ رکوردی حذف نشود.
- [ ] آماده‌سازی Nginx و TLS پس از تأیید مسیر DNS.

### شنبه، روی سرور شرکت
- [ ] بررسی نسخه نصب‌شده و پورت‌های واقعی؛ گزارش فعلی مربوط به `325e0db` است.
- [ ] اطمینان از سلامت سرویس‌های اصلی و تهیه Backup پیش از تغییر شبکه.
- [ ] نصب WireGuard Windows و واردکردن کانفیگ خصوصی.
- [ ] تأیید handshake و ping دوطرفه روی Tunnel IP.
- [ ] ساخت Windows PortProxy و Firewall فقط برای panel/shop.
- [ ] تست از VPS به `10.77.0.2:13300` و `10.77.0.2:18190`.
- [ ] نصب Nginx/TLS و سپس اعمال DNS.
- [ ] تست پنل، ورود، نقش‌ها، فروشگاه، کاتالوگ و ثبت سفارش آزمایشی کنترل‌شده.
- [ ] GPS فقط در یک مرحله جداگانه پس از تنظیم Traccar، HTTPS و تست گوشی.
- [ ] بررسی restart خودکار WireGuard، Nginx و Windows و پایداری بعد از قطع کوتاه اینترنت.
- [ ] ثبت commit نصب‌شده، خروجی تست و نتیجه پذیرش در این سند.

## ۱۱. Rollback

اگر اتصال عمومی مشکل داشت:
1. DNS را به مقادیر قبلی ثبت‌شده برگردانید.
2. سرویس‌های شرکت و Compose را تغییر ندهید؛ WireGuard را می‌توان متوقف کرد بدون آنکه دیتابیس تغییر کند.
3. Nginx VPS را به کانفیگ قبلی برگردانید.
4. PortProxy و Firewall جدید را فقط پس از ثبت وضعیت قبلی حذف کنید.
5. هیچ دیتابیسی Restore یا حذف نشود؛ این کار صرفاً تغییر شبکه است.

## ۱۲. ثبت تغییرات واقعی

هر مرحله فقط پس از مشاهده خروجی موفق، از «در انتظار» به «تأییدشده» تغییر کند. این سند به‌تنهایی اثبات نصب، اتصال، TLS، CDN یا پذیرش شرکت نیست.
