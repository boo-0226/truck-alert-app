@echo off
cd /d C:\Users\TScot\web-apps\truck-alert-app
set PYTHONUTF8=1
set ALERTS_SMS_ENABLED=1
set DIGEST_SMS_ENABLED=1
python run_multi.py
