@echo off
setlocal enableextensions enabledelayedexpansion
cd /d C:\Users\TScot\web-apps\truck-alert-app

REM Optional: activate venv
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

echo ==== GOVDEALS START %DATE% %TIME% ====
python -u govdeals_scraper.py
echo ==== GOVDEALS EXIT %DATE% %TIME% code=%ERRORLEVEL% ====
endlocal
