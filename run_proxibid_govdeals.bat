@echo off
setlocal enableextensions enabledelayedexpansion

REM --- set working dir ---
cd /d C:\Users\TScot\web-apps\truck-alert-app

REM --- logging (daily file) ---
if not exist "logs" mkdir "logs"
set "LOG=logs\proxibid_govdeals_%date:~10,4%-%date:~4,2%-%date:~7,2%.log"

REM --- optional: use venv if present ---
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

REM --- unbuffered Python output for live logs ---
set PYTHONUNBUFFERED=1

echo ==== PROXIBID+GOVDEALS RUN START %DATE% %TIME% ====>> "%LOG%"
python -u run_multi.py >> "%LOG%" 2>&1
echo ==== PROXIBID+GOVDEALS RUN EXIT %DATE% %TIME% code=%ERRORLEVEL% ====>> "%LOG%"

endlocal
