@echo off
setlocal enableextensions enabledelayedexpansion
cd /d C:\Users\TScot\web-apps\truck-alert-app

if not exist "logs" mkdir "logs"

REM Optional: activate venv
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

echo ==== GOVDEALS START %DATE% %TIME% ====>> "logs\govdeals.log"
python -u govdeals_scraper.py >> "logs\govdeals.log" 2>&1
echo ==== GOVDEALS EXIT %DATE% %TIME% code=%ERRORLEVEL% ====>> "logs\govdeals.log"
endlocal
