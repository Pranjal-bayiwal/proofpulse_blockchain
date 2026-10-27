@echo off
cd /d "%~dp0backend"
if not exist .venv\Scripts\activate.bat ( echo Run setup_windows.bat first. & pause & exit /b 1 )
call .venv\Scripts\activate.bat
echo API: http://127.0.0.1:8000   (docs: /docs)   Ctrl+C to stop
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
