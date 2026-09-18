@echo off
chcp 65001 >nul
title Kiarad BI Launcher
cd /d "D:\project\kiaradbi"

echo ===================================================
echo [1/4] Starting Database (PostgreSQL & pgAdmin)...
echo ===================================================
docker compose up -d postgres pgadmin

echo.
echo ===================================================
echo [2/4] Starting FastAPI Backend (Port 8000)...
echo ===================================================
start "Kiarad Backend" cmd /k "cd /d D:\project\kiaradbi && .venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload --env-file .env"

echo.
echo ===================================================
echo [3/4] Starting Next.js Dashboard (Port 3000)...
echo ===================================================
start "Kiarad Frontend" cmd /k "cd /d D:\project\kiaradbi\kiarad-dashboard && npm run dev"

echo.
echo ===================================================
echo [4/4] Waiting for services and opening browser...
echo ===================================================
timeout /t 4 >nul
start http://localhost:3000/login

echo.
echo >>> Kiarad BI is successfully up and running!
