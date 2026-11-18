@echo off
REM Start InvoiceOps AI, then open http://127.0.0.1:8000
cd /d "%~dp0..\backend"
if not exist ".venv" (echo Run scripts\setup.bat first. & exit /b 1)
call .venv\Scripts\activate.bat
alembic upgrade head || exit /b 1
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app_factory --factory --host 127.0.0.1 --port 8000
