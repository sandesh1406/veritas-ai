@echo off
REM VERITAS AI Backend Test Runner
REM Run this after installing dependencies

cd /d "%~dp0"

echo ============================
echo VERITAS AI Backend Tests
echo ============================
echo.

REM Check if venv exists
if not exist venv\Scripts\activate.bat (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r requirements.txt
    pip install pytest pytest-asyncio
) else (
    call venv\Scripts\activate.bat
)

echo.
echo Running tests...
python -m pytest tests/ -v --tb=short

echo.
echo Test run complete.
pause