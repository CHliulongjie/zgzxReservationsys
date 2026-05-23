@echo off
chcp 65001 >nul
title Zhongguo Middle School Venue Reservation System Startup Script

echo ============================================================
echo Zhongguo Middle School Venue Reservation System Startup Script
echo ============================================================

echo [INFO] If you want to use Chinese language to start the system,please use Linux version

REM Set script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check virtual environment
if exist ".venv\" (
    echo. & echo [INFO] Detected virtual environment: .venv
    
    REM Activate virtual environment
    if exist ".venv\Scripts\activate.bat" (
        call ".venv\Scripts\activate.bat"
        echo [INFO] Virtual environment activated
    ) else (
        echo [ERROR] Virtual environment activation file does not exist
        pause
        exit /b 1
    )
) else (
    echo [WARN] No virtual environment detected, attempting to use system Python
)

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found, please install Python first
    pause
    exit /b 1
)

REM Upgrade pip
echo. & echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

REM Check dependencies
echo. & echo [INFO] Checking dependencies...
python -c "import flask, pandas, openpyxl, yaml, waitress, requests, numpy" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Missing dependencies, installing...
    
    REM Check if requirements.txt exists
    if exist "requirements.txt" (
        echo [INFO] Installing dependencies from requirements.txt...
        python -m pip install -r requirements.txt --timeout 300
    ) else (
        REM Manually install dependencies
        echo [INFO] Installing basic dependencies...
        python -m pip install flask pandas openpyxl pyyaml waitress requests numpy
    )
    
    REM Check if dependencies were installed successfully
    echo [INFO] Verifying dependency installation...
    python -c "import flask, pandas, openpyxl, yaml, waitress, requests, numpy" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed, please check network connection or install manually
        pause
        exit /b 1
    )
)

echo [INFO] Dependencies check completed

REM Start server
echo. & echo [INFO] Starting server...
REM Check if main.py exists and start
if exist "main.py" (
    echo [INFO] Starting main.py
    python main.py
) else (
    echo [ERROR] No startable service file found (main.py)
    pause
    exit /b 1
)

REM Server exit handling
set EXIT_CODE=%errorlevel%
echo. & echo [INFO] Server exited, code: %EXIT_CODE%

if %EXIT_CODE% equ 0 (
    echo [INFO] Server exited normally
) else (
    echo [WARN] Server exited abnormally
)

REM Deactivate virtual environment (if activated)
if defined VIRTUAL_ENV (
    if exist ".venv\Scripts\deactivate.bat" (
        call ".venv\Scripts\deactivate.bat"
        echo [INFO] Virtual environment deactivated
    )
)

echo ============================================================
pause