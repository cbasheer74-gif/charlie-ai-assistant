@echo off
echo ========================================================
echo Building updated CHARLIE Production EXE...
echo ========================================================
cd /d "%~dp0"
python build_production.py --skip-installer
echo.
echo ========================================================
echo Signing CHARLIE.exe...
echo ========================================================
python scripts\sign_installer.py --file dist\CHARLIE\CHARLIE.exe
echo.
echo ========================================================
echo Build & Signing Complete!
echo ========================================================
pause
