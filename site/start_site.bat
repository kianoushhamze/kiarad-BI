@echo off
rem KIARAD - start the shop site locally
cd /d "%~dp0"
where node >nul 2>nul
if not %errorlevel%==0 goto node_missing
start "Kiarad shop" http://127.0.0.1:8081
node server.mjs
goto end

:node_missing
echo Node.js was not found. Install Node.js and try again.
exit /b 1

:end
