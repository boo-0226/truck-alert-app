@echo off
setlocal
cd /d C:\Users\TScot\web-apps\truck-alert-app

REM (optional) activate venv if you use it
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

REM Ensure logs folder exists
if not exist logs mkdir logs

REM -u = unbuffered so logs flush as it runs
REM Use a rolling log per day; adjust date tokens if your locale differs
set LOGFILE=logs\multi_%DATE:~10,4%-%DATE:~4,2%-%DATE:~7,2%.log

echo ==== START %DATE% %TIME% ====>> "%LOGFILE%"
"C:\Users\TScot\AppData\Local\Programs\Python\Python38-32\python.exe" -u run_multi.py >> "%LOGFILE%" 2>>&1
echo ==== EXIT %DATE% %TIME% code=%ERRORLEVEL% ====>> "%LOGFILE%"
endlocal
