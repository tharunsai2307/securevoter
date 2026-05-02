@echo off
echo =========================================
echo   Starting VoteSecure Server...
echo =========================================
echo.
echo 1) Checking for required packages...
pip install -r requirements.txt
echo.
echo 2) Opening Google Chrome automatically...
start chrome "http://127.0.0.1:8000"
echo.
echo 3) Starting the server (DO NOT CLOSE THIS BLACK WINDOW!)
python app.py
echo.
echo =========================================
echo   SERVER STOPPED OR CRASHED!
echo =========================================
pause
