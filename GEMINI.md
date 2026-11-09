# Kiarad BI — Project Context & Architecture
- **Company**: Kiarad Shefa Andish (شرکت پخش کیاراد شفا اندیش - کرمان)
- **Domain**: Capillary distribution of dermatology, hair care, and mesotherapy products (Swalin Vira, Dermalist, Total Derm, MC Cosmetics).
- **Backend (D:/project/kiaradbi)**: FastAPI (api.py), JWT Auth & Operations (operations.py), Cashflow & Checks (treasury.py), BI & Pareto/FEFO (assistant_engine.py), Holoo ERP Integration (holo_api.py at 192.168.1.105:8080), PostgreSQL on port 5432 (db.py, config.py).
- **Frontend (D:/project/kiaradbi/kiarad-dashboard)**: Next.js 16 (App Router + Turbopack), Tailwind CSS, Persian RTL, Dark/Purple UI. Sidebar in components/portal-shell.tsx.
