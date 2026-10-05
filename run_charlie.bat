@echo off
setlocal
cd /d "%~dp0"

echo [CHARLIE] Starting Charlie AI Assistant...
cd /d "%~dp0Charlie-Ai assistant"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" main.py
) else if exist "C:\Python314\python.exe" (
    C:\Python314\python.exe main.py
) else (
    python main.py
)

echo.
echo [CHARLIE] Application process ended.
pause
