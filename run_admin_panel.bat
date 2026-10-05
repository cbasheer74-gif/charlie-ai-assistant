@echo off
setlocal
title CHARLIE AI Commercial Admin Server

cd /d "%~dp0Charlie-Ai assistant"

echo ====================================================
echo   CHARLIE AI Commercial Admin Server
echo   Port: 8400
echo ====================================================

set "CHARLIE_ENV=production"
if "%CHARLIE_ADMIN_KEY%"=="" set "CHARLIE_ADMIN_KEY=a7d2e8b9f1c4038a5e921d7b6c04f8e29a3b7c1d5e4f0a2b"
if "%CHARLIE_JWT_SECRET%"=="" set "CHARLIE_JWT_SECRET=f3b8c19d4e72a05f6e8b2c4d9a1f7e3b5c0d2e4f6a8b1c3d5e7f9a0b2c4d6e8f"
set "PYTHONPATH=%~dp0Charlie-Ai assistant"

rem Locate Python virtual environment
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_BIN=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0Charlie-Ai assistant\.venv\Scripts\python.exe" (
    set "PY_BIN=%~dp0Charlie-Ai assistant\.venv\Scripts\python.exe"
) else (
    set "PY_BIN=python"
)

echo Python interpreter: "%PY_BIN%"
echo Opening: http://localhost:8400/admin-panel/
echo.

rem Launch browser automatically in background
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8400/admin-panel/"

"%PY_BIN%" -m uvicorn licensing_server.app:app --host 127.0.0.1 --port 8400 --reload

echo.
echo [SERVER STOPPED]
pause
