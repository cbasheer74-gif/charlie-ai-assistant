@echo off
echo ============================================================
echo  CHARLIE v1.3.0 — Cleanup ^& Rebuild
echo ============================================================
cd /d "%~dp0"

echo.
echo [1/4] Removing duplicate installer (CHARLIE-Setup.exe)...
if exist "dist\CHARLIE-Setup.exe" (
    del /f /q "dist\CHARLIE-Setup.exe"
    echo       Done.
) else (
    echo       Already gone.
)

echo.
echo [2/4] Removing old release folders (v1.0.0 through v1.2.2)...
for %%V in (v1.0.0-rc.1 v1.0.0 v1.1.0 v1.2.0 v1.2.1 v1.2.2) do (
    if exist "release\%%V" (
        rd /s /q "release\%%V"
        echo       Deleted release\%%V
    )
)
echo       Old releases cleaned.

echo.
echo [3/4] Building CHARLIE v1.3.0 EXE...
C:\Python314\python.exe build_production.py --skip-installer
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check above for details.
    pause
    exit /b 1
)

echo.
echo [4/4] Copying new installer to release\v1.3.0...
if not exist "release\v1.3.0" mkdir "release\v1.3.0"
if exist "dist\CHARLIE-Setup-1.3.0.exe" (
    copy /y "dist\CHARLIE-Setup-1.3.0.exe" "release\v1.3.0\"
    echo       Copied CHARLIE-Setup-1.3.0.exe
)

echo.
echo ============================================================
echo  Done! dist\CHARLIE\CHARLIE.exe  ^&  dist\CHARLIE-Setup-1.3.0.exe
echo ============================================================
pause
