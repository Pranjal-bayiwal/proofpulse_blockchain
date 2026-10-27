@echo off
cd /d "%~dp0frontend"
if not exist node_modules ( echo Run setup_windows.bat first. & pause & exit /b 1 )
echo Web app: http://localhost:5173
call npm run dev -- --host 127.0.0.1
pause
