@echo off
REM One-time setup for Windows. Run from the project folder: scripts\setup.bat
setlocal
cd /d "%~dp0.."
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env - open it in Notepad and set DATABASE_URL password, then run this script again.
  exit /b 0
)
cd backend
if not exist ".venv" py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || exit /b 1
if not exist "%LOCALAPPDATA%\InvoiceOps\paddle_models\PP-OCRv6_medium_det" call ..\scripts\download_models.bat || exit /b 1
alembic upgrade head || (echo Database migration failed - check DATABASE_URL in .env and that PostgreSQL is running. & exit /b 1)
python -c "from app.config import OcrSettings, load_dotenv; load_dotenv(); from app.extraction.ocr import check_ocr; s=check_ocr(OcrSettings.from_env()); print('OCR ready:', s.ready); [print(' -', p) for p in s.problems]"
echo.
echo Setup finished. Start the app with scripts\start.bat
