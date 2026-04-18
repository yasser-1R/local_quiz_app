@echo off
REM One-click start for Windows.
REM First run: creates a venv and installs dependencies.
REM Subsequent runs: just starts the server.
cd /d %~dp0

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Python was not found. Install Python 3.10+ from https://python.org and try again.
        pause
        exit /b 1
    )
    call ".venv\Scripts\activate.bat"
    echo Installing dependencies (this only happens once)...
    pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)

python run.py
pause
