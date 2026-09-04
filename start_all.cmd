@echo off
REM ReviveFlow one-click dev launcher (Windows).
REM Starts the FastAPI backend and the Vite frontend, then opens the dashboard.
REM Requires: Python 3.10+ and Node 18+.

setlocal
cd /d "%~dp0"

echo [1/3] Installing / checking backend dependencies...
cd backend
if not exist "venv" (
    python -m venv venv
    call venv\Scripts\pip.exe install -r requirements.txt
) else (
    echo      venv already present.
)
cd ..

echo [2/3] Checking frontend dependencies...
cd frontend
if not exist "node_modules" (
    call npm install
) else (
    echo      node_modules already present.
)
cd ..

echo [3/3] Launching servers...

start "ReviveFlow API" cmd /k "cd backend && venv\Scripts\python.exe run_api.py"
timeout /t 8 /nobreak >nul
start "ReviveFlow Dashboard" cmd /k "cd frontend && npm run dev"
timeout /t 10 /nobreak >nul

start "" "http://localhost:5173"

echo.
echo Backend  : http://localhost:8000
echo Dashboard: http://localhost:5173
echo.
endlocal
