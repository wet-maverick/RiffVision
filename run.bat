@echo off
title RiffVision
cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [RiffVision] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Install / upgrade dependencies on first run or when needed
echo [RiffVision] Checking dependencies...
python -m pip install -q -r requirements.txt

:: Launch the app
echo [RiffVision] Starting...
python main.py
