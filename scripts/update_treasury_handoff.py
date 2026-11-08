"""Prepend the verified release note, preserving prior handoff history."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
handoff=root/'Kiarad Handoff V9.md'
note=(root/'docs/treasury-release-2026-10-20.md').read_text(encoding='utf-8')
previous=handoff.read_text(encoding='utf-8-sig')
marker='## وضعیت جاری — خزانه و اکسل؛ بامداد ۲۰ اکتبر ۲۰۲۶'
if marker not in previous:
    historical=previous.split('\n',1)[1]
    section=note.split('\n',1)[1]
    handoff.write_text('# هندآف پروژهٔ کیاراد شفا اندیش — به‌روزرسانی ۲۰ اکتبر ۲۰۲۶\n\n'+marker+'\n'+section+'\n\n## یادداشت‌های مراحل پیشین\n'+historical,encoding='utf-8')
guide=root/'docs/treasury-financial-management.md'
body=guide.read_text(encoding='utf-8-sig')
if 'treasury-release-2026-10-20.md' not in body:
    guide.write_text(body+'\n\n## ادامهٔ بامداد ۲۰ اکتبر؛ بودجه، افر و اکسل\n\nوضعیت تازه و حدود پذیرش در [گزارش این ادامه](treasury-release-2026-10-20.md) ثبت است؛ بر شمارهای تاریخی بالا اولویت دارد. بودجهٔ ۳۰۰ میلیون تومان مصوب است، ولی سود تاریخی و کفایت قطعی وجه هنوز تأیید نشده‌اند.\n',encoding='utf-8')
print('Handoff and financial guide updated; prior history preserved.')
