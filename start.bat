@echo off
REM One-click launcher for Audiobook Studio.
REM Starts the backend (which also serves the built frontend) and opens it in your browser.

setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo.
    echo Backend virtual environment not found at backend\.venv
    echo Run the setup steps in README.md first, then try again.
    echo.
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo Frontend build not found - building it now, this only happens once...
    call npm --prefix frontend install
    if errorlevel 1 (
        echo npm install failed - see README.md for setup steps.
        pause
        exit /b 1
    )
    call npm --prefix frontend run build
    if errorlevel 1 (
        echo Frontend build failed - see README.md for setup steps.
        pause
        exit /b 1
    )
)

echo Starting Audiobook Studio...
start "Audiobook Studio (close this window to stop)" /D "%~dp0backend" "%~dp0backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo Waiting for the server to come up...
timeout /t 3 /nobreak >nul

start "" "http://127.0.0.1:8000"

echo.
echo Audiobook Studio is running at http://127.0.0.1:8000
echo Close the "Audiobook Studio" console window to stop the server.
echo.
