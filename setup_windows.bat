@echo off
REM ProofPulse one-time setup for Windows.
REM Needs Python 3.11, 3.12 or 3.13 (NOT 3.14 yet) and Node.js 18+. Python 3.14 users: install 3.13 from python.org alongside it.
setlocal
cd /d "%~dp0"

set PYCMD=
for %%V in (3.13 3.12 3.11) do (
  if not defined PYCMD (
    py -%%V -c "import sys" >nul 2>&1 && set PYCMD=py -%%V
  )
)
if not defined PYCMD (
  python -c "import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>&1 && set PYCMD=python
)
if not defined PYCMD (
  echo.
  echo ERROR: no supported Python found. Install Python 3.13 from https://www.python.org/downloads/windows/
  echo        (tick "Add python.exe to PATH" and keep the "py launcher" option), then run this file again.
  goto :fail
)
echo Using: %PYCMD%
where node >nul 2>&1 || ( echo ERROR: Node.js not found. Install the LTS version from https://nodejs.org/ and run this again. & goto :fail )

echo === Backend: virtual environment and packages ===
cd backend
if exist .venv\Scripts\python.exe ( .venv\Scripts\python.exe -c "import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,13) else 1)" || rmdir /s /q .venv )
if not exist .venv ( %PYCMD% -m venv .venv || goto :fail )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :fail
pip install --only-binary=:all: -r requirements.txt || goto :fail
if not exist .env copy .env.example .env >nul
cd ..

echo === Frontend: npm packages ===
cd frontend
call npm install || goto :fail
cd ..

echo.
echo ============================================================
echo  Setup complete.
echo  1) double-click start_backend.bat   (keep the window open)
echo  2) double-click start_frontend.bat  (keep the window open)
echo  3) double-click seed_demo.bat       (once, loads demo data)
echo  4) open http://localhost:5173
echo ============================================================
pause
exit /b 0

:fail
echo.
echo SETUP FAILED - read the message above. Send me that text if you need help.
pause
exit /b 1
