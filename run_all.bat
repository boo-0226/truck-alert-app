@echo off
setlocal enableextensions enabledelayedexpansion
cd /d C:\Users\TScot\web-apps\truck-alert-app
if not exist "logs" mkdir "logs"

REM Optional: activate venv (for both windows spawned shells)
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

REM Launch each site in its own background shell with its own log.
REM Using start + cmd /c so each gets independent lifetime and log redirection.

REM GovDeals (your existing script)
start "GovDeals" cmd /c ^
  "echo ==== GOVDEALS START %DATE% %TIME% ====>> logs\govdeals.log & ^
   python -u govdeals_scraper.py >> logs\govdeals.log 2>&1"

REM Proxibid (new)
start "Proxibid" cmd /c ^
  "echo ==== PROXIBID START %DATE% %TIME% ====>> logs\proxibid.log & ^
   python -u run_proxibid.py >> logs\proxibid.log 2>&1"

REM Add more sites later as separate processes the same way.
echo Started GovDeals and Proxibid in separate processes. Check the logs\*.log files.
endlocal
