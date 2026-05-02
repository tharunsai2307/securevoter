@echo off
echo =========================================
echo   Starting VoteSecure Server...
echo =========================================
echo.
echo 1) Checking for required packages...
pip install -r public\requirements.txt >nul 2>&1
echo.
echo 2) Opening Google Chrome automatically...
start chrome "http://127.0.0.1:8000"
echo.
echo 3) Starting the server...
echo.
python public\app.py > server_error.log 2>&1
if %errorlevel% neq 0 (
    py public\app.py >> server_error.log 2>&1
)
if %errorlevel% neq 0 (
    python3 public\app.py >> server_error.log 2>&1
)
echo.
echo =========================================
echo   SERVER STOPPED OR CRASHED!
echo =========================================
pause
