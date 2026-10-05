@echo off
setlocal
cd /d "%~dp0"

echo [CHARLIE] Starting Charlie AI Assistant...
set PYTHONUNBUFFERED=1
cd /d "%~dp0Charlie-Ai assistant"

if exist "%~dp0.venv\Scripts\python.exe" (
    echo [CHARLIE] Running via .venv\Scripts\python.exe...
    "%~dp0.venv\Scripts\python.exe" -u main.py
) else if exist "C:\Python314\python.exe" (
    echo [CHARLIE] Running via C:\Python314\python.exe...
    C:\Python314\python.exe -u main.py
) else (
    echo [CHARLIE] Running via system python...
    python -u main.py
)

echo.
echo [CHARLIE] Application process ended with exit code %ERRORLEVEL%.
pause
