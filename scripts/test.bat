@echo off
cd /d "%~dp0..\backend"
call .venv\Scripts\activate.bat
pip install -r requirements-dev.txt
python -m pytest -q
