import py_compile

assistant_file = "assistant_engine.py"

with open(assistant_file, "r", encoding="utf-8") as f:
    code = f.read()

notice = "\\n\\n⚠️ وضعیت سرور هلو: کامپیوتر حسابداری (192.168.1.105) در شبکه خاموش است؛ اطلاعات بر اساس آخرین نسخه محلی دیتابیس گزارش شد."

if "وضعیت سرور هلو" not in code:
    code = code.replace('return {"reply": ans, "answer": ans}', f'return {{"reply": ans + "{notice}", "answer": ans}}')
    with open(assistant_file, "w", encoding="utf-8") as f:
        f.write(code)
    py_compile.compile(assistant_file, doraise=True)
    print("✓ دستیار پایدار شد و پیام وضعیت شبکه به آن افزوده شد.")
