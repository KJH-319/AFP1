@echo off
rem AFP Designer launcher (no Claude needed). Close this window to stop the app.
title AFP Designer
cd /d "%~dp0"

set "PY=%USERPROFILE%\afp-venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] Virtual environment not found: %PY%
    echo See README.md "Quick start" to create it.
    pause
    exit /b 1
)

echo Starting AFP Designer... a browser tab will open at http://localhost:8501
echo Keep this window open while using the app. Close it to stop.
echo.
"%PY%" -m streamlit run app/Home.py --server.port 8501
if errorlevel 1 pause
