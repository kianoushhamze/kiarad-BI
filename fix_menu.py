# -*- coding: utf-8 -*-
p = r"D:\project\kiaradbi\kiarad-dashboard\components\portal-shell.tsx"
lines = open(p, encoding="utf-8").readlines()

s = next(i for i, l in enumerate(lines) if "const links" in l)
e = next(j for j in range(s + 1, len(lines)) if lines[j].strip().startswith("]"))

new_links = """const links = [
  ["نمای کلی", "/management", "📊"],
  ["گزارش عملکرد و فیش‌ها", "/visitors", "📈"],
  ["تعریف و فرمول ویزیتورها", "/manager", "👥"],
  ["تسک‌ها", "/tasks", "☑"],
  ["گزارش شبانه", "/daily-reports", "📰"],
  ["خزانه‌داری", "/treasury", "◈"],
  ["کالا و کانال‌ها", "/catalog", "⊞"],
  ["پنل عملیات ویزیتور", "/personnel", "💼"]
];
"""

content = "".join(lines[:s] + [new_links] + lines[e + 1:])
content = content.replace('["/visitors", "/tasks"', '["/visitors", "/manager", "/tasks"')
if "export default PortalShell" not in content:
    content += "\nexport default PortalShell;\n"

open(p, "w", encoding="utf-8").write(content)
print("سایدبار با موفقیت به‌روزرسانی شد!")