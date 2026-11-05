@echo off
cd /d "%~dp0"

echo Starting fireFairy backend...
start "fireFairy Backend" cmd /k "cd /d backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001"

echo Starting fireFairy frontend...
start "fireFairy Frontend" cmd /k "cd /d frontend && npm.cmd run dev -- --host 127.0.0.1"

echo Opening fireFairy...
timeout /t 8 /nobreak >nul

start "" "http://127.0.0.1:5174/"