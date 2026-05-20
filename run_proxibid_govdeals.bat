@echo off
setlocal enableextensions enabledelayedexpansion

REM --- set working dir ---
cd /d C:\Users\TScot\web-apps\truck-alert-app

REM --- legacy daily file logging disabled ---
REM Let the service host capture stdout/stderr.

REM --- optional: use venv if present ---
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

REM --- unbuffered Python output for live logs ---
set PYTHONUNBUFFERED=1

echo ==== PROXIBID+GOVDEALS RUN START %DATE% %TIME% ====
python -u run_multi.py
echo ==== PROXIBID+GOVDEALS RUN EXIT %DATE% %TIME% code=%ERRORLEVEL% ====

endlocal
