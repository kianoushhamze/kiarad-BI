# هنداف اجرایی Codex برای نهایی‌سازی کیاراد BI

**مخزن:** kianoushhamze/kiarad-BI  
**Issue اصلی:** https://github.com/kianoushhamze/kiarad-BI/issues/12  
**PR مستندات و هنداف:** https://github.com/kianoushhamze/kiarad-BI/pull/13  
**شاخه:** codex/release-readiness-docs-20261113  
**SHA مبنای main هنگام تهیه:** f3c7bd4a667421d5c0481b58cfcb8ec8aae38cf9

این فایل دستور کار مستقیم برای Codex است. آن را همراه Issue #12 بخوان و از وضعیت فعلی مخزن ادامه بده. این هنداف مجوز merge، deploy، cutover یا دسترسی به دادهٔ واقعی شرکت نیست.

## 1. هدف و تعریف پایان کار

هدف، آماده‌کردن release candidate قابل‌اعتماد و بستهٔ انتقال قابل‌ردیابی است؛ نه بازنویسی محصول. کار وقتی آمادهٔ تحویل است که:
1. نقص کد بازتولیدپذیرِ شناخته‌شده باقی نمانده باشد، یا هر مورد حل‌نشده با اثر و مالک مشخص ثبت شده باشد.
2. اصلاحات ضروری در شاخهٔ مستقل، با تست رگرسیون، CI کامل و PR بازبینی‌پذیر باشند.
3. PRهای قدیمی و اسناد متناقض تعیین تکلیف شده باشند.
4. release kit از همان SHA دقیق ساخته شده و manifest/checksum/artifactها کنترل شده باشند.
5. ماتریس وضعیت‌ها و دستورالعمل پذیرش شرکت آماده باشد.
6. هیچ عملیات واقعی شرکت یا گوشی کاربر بدون اعلام آمادگی کاربر انجام نشده باشد.

**PR نهایی را merge نکن.** خروجی این مأموریت PR آمادهٔ بازبینی و گزارش دقیق است.

## 2. وضعیت قطعی؛ دوباره نساز

- اصلاحات CMS و فروشگاه در main هستند؛ PRهای #5 و #6 ادغام شده‌اند.
- Traccar bridge در PR #11 ادغام شده است.
- جریان‌های تخصصی/آموزش/اتوماسیون و اپ در PRهای #8 و #10 ادغام شده‌اند.
- بستهٔ انتقال و اصلاحات checkout در PR #7 ادغام شده‌اند.
- اپ بومی KiaradField در پوشهٔ mobile موجود است؛ Expo 58، React Native 0.88.1، version 1.1.0، Android package برابر ir.kiarad.field و versionCode برابر 2.
- CI شامل backend offline، frontend build، PostgreSQL/CMS/storefront regressions، browser storefront، Android pilot APK، iOS Simulator، Persian handbook، transfer-kit و offline Linux images است.
- Android CI خروجی pilot APK می‌سازد؛ امضای تولیدی پایدار نیست و معماری CI فعلی arm64-v8a است.
- iOS CI خروجی Simulator بدون device signing می‌سازد؛ این خروجی IPA قابل نصب روی آیفون نیست.
- اپ اختصاصی KiaradField و اپ آمادهٔ Traccar Client دو مسیر مستقل‌اند؛ یکی را جایگزین دیگری نکن.
- گزارش‌های validation موجود، تست ایزوله/دادهٔ ساختگی و CI را پوشش می‌دهند؛ آن‌ها پذیرش سرور شرکت یا گوشی واقعی نیستند.

## 3. وضعیت PRهای قدیمی و اقدام لازم

| PR | وضعیت مشاهده‌شده | اقدام Codex |
|---|---|---|
| #3 حفظ سبد هنگام خرابی کاتالوگ | بسته شد؛ بدون merge، به‌عنوان superseded | فقط `site/index.html` قدیمی را تغییر می‌داد؛ مسیر فعال `site-healer/buy.html` است و `tests/node/catalog-recovery.test.mjs` رفتار حفظ سبد/بازیابی را پوشش می‌دهد. در CI run 43325251916 موفق شد. توضیح بستن در PR ثبت شده است. |
| #4 مهاجرت و حذف تخفیف CMS | بسته شد؛ بدون merge، به‌عنوان superseded | حذف صریح تخفیف و حفظ فیلدهای حذف‌نشده در `site_cms.py` و تست‌های جاری CMS وجود دارند؛ تغییر پیام قیمت در PR قدیمی ادعای نادرست دربارهٔ نوشتن به هلو داشت. تست‌های وظایف PR نیز در main موجودند. توضیح بستن در PR ثبت شده است. |
| #5 و #6 | ادغام‌شده | فقط مرجع تغییرات؛ بازنویسی ممنوع. |
| #7 تا #11 | ادغام‌شده | برای ماتریس نهایی بررسی کن؛ دوباره پیاده‌سازی نکن. |
| #13 | Draft مستنداتی | همین PR را با این هنداف تکمیل کن؛ PR موازی نساز و merge نکن. |

PRهای #3 و #4 پس از مقایسهٔ دقیق با main در ۱۳ نوامبر ۲۰۲۶ با توضیح superseded بسته شدند؛ هیچ‌کدام merge نشدند. از بازکردن مجدد یا cherry-pick کردن تغییرات قدیمی خودداری کن مگر نقص تازه و بازتولیدپذیر مشخص شود.

## 4. اصلاح مستندات و شواهد

### 4.1 پورت‌ها و راهنمای انتقال

- راهنمای `deploy/cloudflare/README-KIARAD-CLOUDFLARE.md` راهنمای تاریخی معماری قبلی است؛ دامنه خریداری نشده و اسکریپت آن اجرا نشده است. آن را برای انتشار فعلی اجرا نکن.
- transfer/README-fa.md و transfer/compose.transfer.yml مرجع جاری انتقال stage هستند.
- پورت‌های stage مستندشده: پنل 3300، backend/API 8800، storefront 8190. این‌ها را با پورت‌های تاریخی/محلی 3000، 3100، 8000 و 8090 قاطی نکن.
- docs/Migration_Review_20261112.md هنوز دستور/پورت‌های قدیمی 3000/8000/8090 دارد. آن را صریحاً historical/superseded علامت بزن و به راهنمای جاری لینک بده، یا دقیقاً به‌روزرسانی کن؛ دو دستور عملیاتی متناقض باقی نماند.
- قبل از تغییر دستورها، اسکریپت‌های واقعی transfer/01-Inspect-Server.ps1 تا 07-Configure-Traccar.ps1، transfer/common.ps1، compose و تست‌های tests/test_transfer_kit.ps1 و tests/test_transfer_backups.ps1 را بخوان.
- راهنمای انتقال باید stage موازی، backup/restore، جلوگیری از دو نویسنده و scheduler، آزمون نقش‌ها، تطبیق هلو، سفارش آزمایشی، cutover و rollback با حفظ داده‌های جدید را پوشش دهد.
- دامنه، URL واقعی، مسیر سرور، نام کانتینر، IP، رمز و secret را حدس نزن.

### 4.2 Validation summary
- `transfer/validation/summary.json` یک snapshot تاریخی با مبنای `112153c` است و نباید به‌عنوان آمار CI نسخهٔ جاری معرفی شود. برچسب `evidence_status` و پیوند run جاری در آن افزوده شده است.
- transfer/validation/summary.json را با docs/Completion_Validation_20261113.md، manifestها و CI run همان SHA تطبیق بده.
- شمار تست‌ها را از گزارش تاریخی یا حدس تغییر نده.
- اگر نتیجهٔ دقیق و هم‌نسخه در دسترس نیست، summary قدیمی را صریحاً historical کن و به شواهد همان commit ارجاع بده؛ دادهٔ ساختگی نساز.
- offline subset، SQL/PostgreSQL opt-in، API live، browser، PowerShell، Traccar smoke و physical-device acceptance را جدا گزارش کن. Skip به معنی pass نیست.
- هشدارهای lint موجود را از خطاهای تازه تفکیک کن.

### 4.3 Android/iOS/Traccar
- docs/Agent_Mobile_Handoff_20261113.md، docs/Traccar_Bridge_Handoff_20261113.md و mobile/README-fa.md را با workflow و artifact واقعی تطبیق بده.
- APK را دقیق معرفی کن: pilot/test signing و arm64-only در CI فعلی؛ keystore پایدار سازمان و انتشار فروشگاهی جداست. secret یا keystore را در Git/log/هنداف ننویس.
- iOS Simulator را IPA دستگاه معرفی نکن؛ امضای سازمان/Apple Developer و provisioning جداست.
- GPS خام یا دادهٔ Traccar را معادل حضور قطعی، ویزیت معتبر، عملکرد یا حقوق تلقی نکن.
- رضایت، لغو مجوز، پایان شیفت، حذف اپ و خطر از دست‌رفتن صف آفلاین باید روشن بماند.

## شکاف واقعی دیجی‌کالا که در این شاخه fail-closed شد

- بررسی کد نشان داد `digikala_api.py::create_product` یک stub بود که با وجود مستندبودن 404 بودن endpoint، همچنان `POST /products` می‌فرستاد. مسیر تأیید در `platform_sync.py` و دکمهٔ UI نیز آن درخواست را واقعاً اجرا می‌کردند.
- این رفتار اصلاح شد: کلاینت اکنون exception مشخص `DigikalaProductCreationUnavailable` می‌دهد؛ endpoint تأیید proposal پیش از هر درخواست شبکه‌ای با HTTP 409 و راهکار ثبت دستی در Seller Center متوقف می‌شود؛ UI دکمهٔ «تأیید و ارسال» را حذف و روش دستی + نگاشت متغیر را توضیح می‌دهد.
- تست رگرسیون `tests/test_digikala_creation_guard.py` اضافه شد تا اثبات کند هیچ درخواست شبکه‌ای به endpoint تأییدنشده ارسال نمی‌شود و endpoint با 409 متوقف می‌ماند.
- محدودیت محصول جدید از طریق Open API همچنان وابسته به انتشار endpoint رسمی دیجی‌کالا است. پس از ثبت دستی در Seller Center، متغیر باید در صفحهٔ نگاشت به کد هلو وصل شود.
- این تغییرات در شاخهٔ PR #13 هستند؛ تا CI کامل و review، تأییدشده محسوب نمی‌شوند. هیچ credential یا API واقعی استفاده نشده است.

## شواهد جاری تأییدشده در main — ۱۳ نوامبر ۲۰۲۶

- SHA مبنا: `f3c7bd4a667421d5c0481b58cfcb8ec8aae38cf9`؛ CI run `43325251916` با هر ۹ job موفق.
- Jobها: Android pilot APK، مرورگر فروشگاه در عرض‌های موبایل/دسکتاپ، backend offline، PDF فارسی، PostgreSQL/CMS/storefront regressions و Traccar smoke، iOS Simulator، frontend typecheck/build، transfer kit و offline Linux images.
- بستهٔ Offline: پنج image روی Linux/amd64؛ artifact `Kiarad-Transfer-20261113-Offline`، SHA-256 آرشیو `5488ed1f5c79de676d96ee2f8a1104a1f55030d7452e8a8df9b5d12012e74398`. شامل بکاپ/دادهٔ شرکت نیست.
- APK پایلوت: artifact `Kiarad-Android-Pilot` با SHA-256 آرشیو `9627ffd565cb6558cb8f1190b2e724d95d213823358eced1df5821ed272bc952`؛ test signing و arm64-only، نه امضای پایدار تولیدی.
- Traccar smoke در محیط ایزوله و دادهٔ ساختگی موفق است؛ پذیرش گوشی واقعی یا HTTPS شرکت نیست.

## 5. تست و release candidate

1. git fetch origin؛ git status --short؛ SHAهای local/remote و تغییرات محلی را ثبت کن. هرگز reset --hard، clean یا overwrite کورکورانه اجرا نکن.
2. main را تازه بخوان؛ اگر جلو رفته، PR13 را reconcile کن و از base قدیمی build نگیر.
3. تست‌های مرتبط را در محیط disposable اجرا کن؛ PostgreSQL باید DB/schema مستقل داشته باشد و هیچ اتصال نوشتنی به DB شرکت نداشته باشد.
4. CI کامل را روی head نهایی اجرا کن و تا پایان همهٔ jobها صبر کن؛ in_progress را موفق اعلام نکن.
5. هر failure را از log/job بررسی کن؛ فقط نقص واقعی را اصلاح کن و CI را دوباره تا سبز کامل دنبال کن.
6. از همان run/head نهایی artifactهای Android pilot، iOS Simulator، handbook، transfer kit و offline images را بگیر. SHA و checksum را با manifest تطبیق بده.
7. transfer kit را با guardهای خودش verify کن؛ مطمئن شو .env، backup شرکت، secret، token، private export و دادهٔ واقعی در artifact عمومی/سورس نیست.
8. در گزارش نهایی exact SHA، run URL، نتیجهٔ هر job، نام artifact و SHA-256 و شمار pass/fail/skip را ثبت کن. خروجی run قدیمی را به SHA جدید نسبت نده.

## 6. ممیزی‌های کد و پیکربندی

- کنترل دسترسی و جداسازی مدیر/ویزیتور/مالی؛ تست cross-user و مالکیت وظیفه/مشتری/مسیر/فایل.
- مسیرهای نوشتنی حساس: پیش‌فاکتور، خزانه، حقوق، پیام خروجی، وظایف دستیار، CMS، سفارش و اتصال سکوها؛ approval، idempotency و unknown-result handling.
- Holoo: authentication/availability را با تازگی داده، reconciliation، invoice/returns/receipts و attribution یکی ندان. sync واقعی یا write به هلو اجرا نکن.
- Digikala/marketplaces: نگاشت کالا، رزرو موجودی، جلوگیری از oversell و برگشت/لغو؛ تست mock کافی برای قرارداد integration است، نه پذیرش واقعی سکو.
- Storefront: مسیر site-healer، catalog fallback، حفظ cart، recovery، checkout retry، order receipt و اتصال رسید فروشگاه به پنل.
- Tracking: رضایت و مالکیت دستگاه، shift boundaries، revoke، deduplication، backfill و محدودیت داده؛ موقعیت قدیمی را live نشان نده.
- Backup/restore و migration: restore فقط روی مقصد disposable؛ حفظ رسانه، secrets خارج از Git، checksum و سازگاری PostgreSQL.
- Windows deployment: اسکریپت‌ها برای PowerShell 5.1 هستند. در commit `ada93cc411b45cb7ec73423f1c64deec68d4ccb3` یک job مستقل `Windows PowerShell 5.1 transfer-kit compatibility` به workflow افزوده شد: تمام فایل‌های PowerShell ثبت‌شده در Git را با parser خود Windows PowerShell 5.1 بررسی می‌کند، بستهٔ آزمایشی را از snapshot همان checkout می‌سازد و guardهای کیت را روی Windows اجرا می‌کند. این job در CI اجرای PR شمارهٔ ۱۳ روی merge commit `6a3c7aefd8cc0f14e4298ff50f5ffbe53b094e1e` در ۱۳ نوامبر ۲۰۲۶ موفق شد: ۴۵ فایل PowerShell با Windows PowerShell `5.1.20348.5773` parse شدند، بستهٔ fixture با ۶۵۵ فایل سورس ساخته شد و چهار guard شامل `valid_kit`، `kit_corruption_guard`، `source_excludes_runtime` و `sync_acceptance_guard` همگی pass شدند. این فقط سازگاری اسکریپت/بسته در runner ویندوز را تأیید می‌کند؛ Docker Desktop ویندوز، بکاپ/restore واقعی، سرور شرکت و cutover همچنان نیازمند پذیرش جدا هستند.
- امنیت: secret، رمز ثابت، token، private export، دادهٔ مشتری و مختصات GPS در commit/log/artifact منتشر نشود. تاریخچهٔ Git را بدون مجوز جداگانه rewrite نکن.

## 7. تست دستگاه اندروید صریحاً به آخر کار موکول است

**تا وقتی کاربر صریحاً اعلام نکرده برای تست و عملیاتی‌سازی آماده است، تست روی گوشی واقعی انجام نده و نصب APK روی گوشی او درخواست نکن.** این موارد فقط در آخرین مرحلهٔ پذیرش شرکت بررسی شوند:
- نصب APK با امضای مورد تأیید شرکت و سازگاری به‌روزرسانی؛
- مجوز دقیق/پس‌زمینه، foreground service و قفل صفحه؛
- محدودیت باتری، force-stop و restart؛
- قطع اینترنت، صف SQLite، ارسال مجدد، dedup و حفظ timestamp اصلی؛
- شروع/پایان شیفت، revoke، logout/account switch و پاک‌سازی امن؛
- مصرف باتری و پایداری روی مدل‌های واقعی گوشی شرکت.

تا آن زمان CI، typecheck، unit/policy tests، prebuild و simulator build مجازند. این موارد را دقیقاً با برچسب **Deferred — final operational acceptance** گزارش کن؛ نه pass و نه نقص کد.

## 8. مرزهای عملیاتی غیرقابل‌نقض

بدون اجازهٔ صریح و آمادگی کاربر:
- روی سرور شرکت، دیتابیس اصلی، Cloudflare/DNS، تونل، firewall، پورت عمومی یا حساب‌های واقعی تغییری نده.
- sync واقعی Holoo/Digikala، سفارش/پیام واقعی، تماس با مشتری یا انتشار محتوا انجام نده.
- دادهٔ واقعی را restore، overwrite، پاک یا به دیتابیس stage وارد نکن.
- scheduler/worker جدید را کنار worker قدیمی فعال نکن.
- cutover، rollback دیتابیس، تغییر hostname یا فعال‌سازی GPS شرکت انجام نده.
- به خاطر اختلاف امضا، اپ نصب‌شده‌ای را که صف آفلاین دارد حذف نکن.
- پیش از فرمان نوشتنی، اثر جانبی را مشخص کن و تا تأیید شرکت اجرا نکن.

## 9. خروجی نهایی الزامی از Codex

یک گزارش فارسی و PR ارائه کن که شامل این موارد باشد:

| دسته | خروجی قابل قبول |
|---|---|
| انجام‌شده و CI-pass | قابلیت/فایل + SHA + run/job سبز |
| پیاده‌سازی‌شده، پذیرش واقعی لازم | کد و تست خودکار موجود + تست میدانی مشخص |
| وابسته به شرکت/کاربر | دامنه، secret، امضای APK/iOS، حساب‌ها، سیاست و تصمیم شرکت |
| نقص واقعی کد | مراحل بازتولید، علت ریشه‌ای، اصلاح حداقلی، تست رگرسیون |
| مسدود/نامعلوم | دلیل دقیق، مدرک لازم و علت عدم امکان حدس |

همراه گزارش:
- فهرست PRهای باز/بسته و علت تعیین تکلیف #3/#4؛
- فایل‌های تغییرکرده و دلیل هر تغییر؛
- SHA مبنا و نهایی، commitها، لینک CI و نتیجهٔ تک‌تک jobها؛
- artifactهای همان run و SHA-256؛
- تست‌های اجراشده، pass/fail/skip و تست‌های خارج از scope؛
- موارد Deferred برای پذیرش نهایی گوشی و شرکت؛
- دستورهای PowerShell 5.1 لازم برای مرحلهٔ بعد، هر کدام در بلوک مستقل با $ErrorActionPreference = "Stop"، فقط پس از تأیید مسیر/نام واقعی و بدون secret.

**معیار موفقیت:** PR کوچک و قابل بازبینی، بدون بازنویسی تکراری، CI کامل سبز روی SHA نهایی، بستهٔ انتقال قابل‌راستی‌آزمایی و فهرست شفاف پذیرش‌های باقی‌مانده. merge و بهره‌برداری به کاربر واگذار شود.

## 10. ممیزی تکمیلی GPS و نتیجهٔ CI پس از تغییرات — ۱۳ نوامبر ۲۰۲۶

- در بررسی مسیرهای Native GPS مشخص شد کنترل مجوز ماژول نقشه در middleware عمومی وجود دارد، اما خود router باید نیز دفاع مستقل داشته باشد. در `live_tracking.py` مجوز `can_write` برای شروع شیفت/heartbeat/upload و مجوز `can_read` برای live/history اضافه شد.
- در `traccar_bridge.py` مجوز `can_read` برای مشاهدهٔ دستگاه‌ها/افراد و `can_write` برای bind/revoke دستگاه اضافه شد. این کنترل‌ها علاوه بر middleware هستند، نه جایگزین آن.
- تست‌های رگرسیون جدید در `tests/test_agent_tracking_db.py` و `tests/test_traccar_bridge_db.py` اضافه شدند.
- اجرای CI روی SHA `c04d3faa10cea21495a651e506e34f52de7cd269` شکست تست دیتابیسی را نشان داد: توابع permission در ماژول `operations` به engine سراسری وصل بودند و در تست schema ایزوله patch نشده بودند. این یک نقص fixture تست بود؛ log job `CMS PostgreSQL and storefront regressions` آن را با `relation role_permissions does not exist` نشان داد.
- برای رفع، در هر دو تست، ماژول `operations` نیز به همان اتصال/engine ایزوله patch شد. commitهای اصلاح fixture: `b5ea4331a87f6a27bcdafabfe9a1ae3975a902fb` و `a8aa65026f21f5c377fc5ae56ba18c9c56e347fb`.
- CI run مجدد `43460813654` روی SHA `a8aa65026f21f5c377fc5ae56ba18c9c56e347fb` ایجاد شده است. در زمان ثبت این یادداشت jobها در حال اجرا/صف بودند؛ **هیچ pass نهایی برای این SHA اعلام نشده است**. لاگ همهٔ jobها را بررسی و فقط پس از اتمام کامل نتیجه را ثبت کن.
- هیچ تغییر روی `main`، سرور شرکت، دیتابیس واقعی، دامنه یا sync بیرونی انجام نشده است.

## 11. کنترل وضعیت سفارش فروشگاه — ۱۳ نوامبر ۲۰۲۶

- ممیزی endpoint \`PATCH /site-orders/{order_id}/status\` یک شکاف واقعی در چرخهٔ سفارش نشان داد: سفارش «ارسال شد» قابل لغو بود؛ در نتیجه رزرو موجودی آن آزاد می‌شد، درحالی‌که کالا قبلاً از انبار خارج شده است.
- در \`site_orders.py\` اکنون تغییر سفارش ارسال‌شده به هر وضعیت دیگری با HTTP 409 رد می‌شود. تکرار همان وضعیت ارسال‌شده همچنان idempotent است.
- تست PostgreSQL ایزوله \`test_shipped_order_cannot_be_cancelled_or_reopened\` اضافه شد: وضعیت و رزرو فعال پس از تلاش برای لغو/بازگشایی حفظ می‌شوند.
- commit اصلاح کد: \`72a273f4b13300a2e7d81e9ea55a6c2587359bfc\`; commit تست: \`81d6506ef4159f3e23b12daa52d174af81622a65\`.
- CI run \`43461718162\` روی SHA تست در حال اجرا/صف است. نتیجهٔ jobهای PostgreSQL، browser، frontend، Android، iOS، handbook و Windows باید از همان run استخراج شود؛ هنوز هیچ نتیجهٔ کامل نهایی اعلام نشده است.
- این اصلاح فقط منطق وضعیت سفارش فروشگاه را محدود می‌کند؛ رزرو سفارش ارسال‌شده عمداً باقی می‌ماند تا موجودی ERP به‌طور معتبر به‌روزرسانی شود. هیچ sync واقعی هلو/دیجی‌کالا یا دادهٔ شرکت اجرا نشده است.

## 12. رفع برخورد شناسهٔ سفارش بین سکوها — ۱۳ نوامبر ۲۰۲۶

- ممیزی قرارداد ثبت دستی فاکتور در هلو نشان داد endpoint قبلی فقط \`order_ref\` را فیلتر می‌کرد؛ درحالی‌که شناسهٔ سفارش فقط در محدودهٔ هر پلتفرم یکتا است. اگر سایت و دیجی‌کالا شناسهٔ یکسان داشته باشند، یک کلیک می‌توانست هر دو پیش‌فاکتور را \`holoo_registered\` علامت بزند.
- endpoint اکنون \`POST /platforms/orders/{platform}/{order_ref}/holoo-registered\` است و هر دو کلید را در UPDATE بررسی می‌کند؛ پلتفرم نامعتبر HTTP 400 می‌گیرد.
- UI صفحهٔ سکوها اکنون platform را نیز در مسیر می‌فرستد.
- دو تست واحد برای اثبات scope دوکلیدی و رد platform ناشناخته افزوده شد.
- commitهای این اصلاح: \`20bdc4a46f18fb8f2db1d1d85525f493144c6c80\`، \`efdd25b171d7955b026af55172c19da32560f976\`، \`b6756fb985417caf464566c4cd70a2078b076af2\`.
- CIهای قبلی در اثر push commitهای جدید با concurrency لغو شده‌اند؛ اجرای تازه \`43464137371\` روی SHA فعلی \`b6756fb985417caf464566c4cd70a2078b076af2\` در صف است. تا اتمام آن نتیجهٔ نهایی اعلام نشود.
