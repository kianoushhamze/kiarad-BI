@echo off
cd /d D:\project\kiaradbi
:loop
D:\project\kiaradbi\.venv\Scripts\python.exe D:\project\kiaradbi\holoo_full_sync.py >> D:\project\kiaradbi\holoo_sync_service.log 2>&1
timeout /t 3600 /nobreak > nul
goto loop
