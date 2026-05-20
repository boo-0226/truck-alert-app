@echo off
setlocal
cd /d C:\Users\TScot\web-apps\truck-alert-app

REM (optional) activate venv if you use it
IF EXIST ".venv\Scripts\activate.bat" (
  call .venv\Scripts\activate.bat
)

REM -u = unbuffered so logs flush as it runs
REM Legacy daily file logging is disabled; let the service host capture stdout/stderr.

echo ==== START %DATE% %TIME% ====
"C:\Users\TScot\AppData\Local\Programs\Python\Python38-32\python.exe" -u run_multi.py
echo ==== EXIT %DATE% %TIME% code=%ERRORLEVEL% ====
endlocal
