@echo off
echo ===================================================
echo  Starting Supply Chain Resilience Control Tower
echo ===================================================
echo.
echo Starting Backend (FastAPI on http://127.0.0.1:8000)...
start "SCDA Backend (FastAPI)" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo.
echo Starting Frontend (Vite + React on http://localhost:5173)...
start "SCDA Frontend (Vite)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ===================================================
echo  Both local servers are launching in separate windows!
echo  - Frontend App:   http://localhost:5173
echo  - Backend API:    http://127.0.0.1:8000
echo  - Swagger UI:     http://127.0.0.1:8000/docs
echo ===================================================
echo.
pause
