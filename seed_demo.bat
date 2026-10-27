@echo off
REM Run AFTER start_backend.bat is up. Loads demo users and records through the API.
cd /d "%~dp0backend"
call .venv\Scripts\activate.bat
python seed.py
pause
