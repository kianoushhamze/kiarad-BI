# Kiarad BI - Fix Pack 2026-08-17

## Phase 2 additions

- Redesigned the CEO dashboard with a dense dark/purple command-center layout.
- Added the first AI Copilot interaction shell.
- Added user, role, salesperson, task, task history, and daily report models.
- Added secure password hashing and token-based authentication endpoints.
- Added treasury accounts, receivable/payable documents, fixed expenses, and cash-flow forecasting.
- Added role restrictions for operational and treasury endpoints.
- Removed the obsolete Docker Compose version field.

## Fixed

- Added the `/dashboard/full` endpoint expected by the management dashboard.
- Aligned staff invoice counts with the frontend contract.
- Limited salesperson achievement calculations to the active target period.
- Added structured management recommendations.
- Added inventory KPIs and low-stock data.
- Added product sales aggregation from `sale_items`.
- Added missing FastAPI, Uvicorn, and Requests dependencies.
- Centralized the frontend API base URL with `NEXT_PUBLIC_API_URL` support.
- Updated Persian document metadata and RTL direction.
- Prevented duplicate customer-score snapshots.
- Completed target and recommendation schema upgrade scripts.
- Made Holoo connection settings configurable through environment variables.

## Replace safely on Windows

Back up the current project, then copy the contents of this package over
`D:\project\kiaradbi`. Keep the existing `config.py`, because it contains the
local database connection settings and is intentionally not included here.

## Runtime verification

After copying the files, start PostgreSQL and pgAdmin with Docker Compose. Then
run the schema upgrade scripts before starting the API:

```powershell
python upgrade_targets.py
python create_recommendations.py
python create_customer_scores.py
python -m uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Verify `http://127.0.0.1:8000/health` and
`http://127.0.0.1:8000/dashboard/full`, then start the dashboard:

```powershell
Set-Location .\kiarad-dashboard
npm install
npm run build
npm run dev
```
