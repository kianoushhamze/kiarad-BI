# نصب مرحله عملیاتی کیاراد BI

این نسخه چهار بخش عملیاتی را اضافه می‌کند:

- ورود نقش‌محور مدیرعامل، مدیر فروش، مالی و ویزیتور
- پنل ویزیتورها و ساخت حساب ورود
- ایجاد، تخصیص و به‌روزرسانی تسک‌ها
- ثبت و مشاهده گزارش شبانه ویزیتورها
- خزانه‌داری، اسناد دریافتنی/پرداختنی، هزینه ثابت و پیش‌بینی ۶۰ روزه نقدینگی

## ترتیب اجرا

1. از پروژه و دیتابیس نسخه پشتیبان بگیرید.
2. محتویات پوشه `work` این بسته را روی `D:\project\kiaradbi` کپی کنید.
3. در پوشه اصلی پروژه اجرا کنید:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe init_db.py
```

4. اگر فایل `.env` ندارید، یک `KIARAD_JWT_SECRET` با حداقل ۳۲ کاراکتر در آن قرار دهید.
5. اگر حساب مدیرعامل نساخته‌اید، اجرا کنید:

```powershell
.\.venv\Scripts\python.exe create_admin.py
```

6. API را مجدداً اجرا کنید:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload --env-file .env
```

7. در پوشه داشبورد اجرا کنید:

```powershell
Set-Location .\kiarad-dashboard
npm install
npm run build
npm run dev
```

8. از نشانی `http://localhost:3000/login` وارد شوید.

## نکته

حساب ویزیتور در دو مرحله ساخته می‌شود: ابتدا پروفایل ویزیتور و سپس حساب ورود متصل به همان پروفایل. اطلاعات ورود ویزیتورها را در پیام‌رسان عمومی ارسال نکنید.
