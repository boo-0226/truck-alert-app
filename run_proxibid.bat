@echo off
setlocal enableextensions enabledelayedexpansion
cd /d C:\Users\TScot\web-apps\truck-alert-app

if not exist "logs" mkdir "logs"

REM Optional: activate venv
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

echo ==== PROXIBID START %DATE% %TIME% ====>> "logs\proxibid.log"
python -u run_proxibid.py >> "logs\proxibid.log" 2>&1
echo ==== PROXIBID EXIT %DATE% %TIME% code=%ERRORLEVEL% ====>> "logs\proxibid.log"
endlocal
