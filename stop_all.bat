@echo off
chcp 65001 >nul
title Stop Kiarad BI
echo Stopping Kiarad BI services...
taskkill /FI "WINDOWTITLE eq Kiarad Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Kiarad Frontend*" /T /F >nul 2>&1
cd /d "D:\project\kiaradbi"
docker compose stop postgres pgadmin
echo All Kiarad BI services stopped cleanly.
pause
