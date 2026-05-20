@echo off
setlocal enableextensions enabledelayedexpansion
cd /d C:\Users\TScot\web-apps\truck-alert-app

REM Optional: activate venv (for both windows spawned shells)
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

REM Launch each site in its own background shell.
REM Legacy file logging is disabled; let the service host capture stdout/stderr.

REM GovDeals (your existing script)
start "GovDeals" cmd /c ^
  "echo ==== GOVDEALS START %DATE% %TIME% ==== & ^
   python -u govdeals_scraper.py"

REM Proxibid (new)
start "Proxibid" cmd /c ^
  "echo ==== PROXIBID START %DATE% %TIME% ==== & ^
   python -u run_proxibid.py"

REM Add more sites later as separate processes the same way.
echo Started GovDeals and Proxibid in separate processes.
endlocal
