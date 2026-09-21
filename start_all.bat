@echo off
echo Starting Kiarad BI stack...
docker compose -f D:\project\kiaradbi\docker-compose.yml up -d postgres pgadmin
start "kiarad-backend" /min powershell -NoExit -Command "Set-Location D:\project\kiaradbi; .\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000"
start "kiarad-frontend" /min powershell -NoExit -Command "Set-Location D:\project\kiaradbi\kiarad-dashboard; npm run dev"
echo Backend: http://127.0.0.1:8000   Frontend: http://localhost:3000
pause
