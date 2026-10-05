@echo off
cd /d "%~dp0Charlie-Ai assistant"
echo ========================================================
echo Building updated CHARLIE Production EXE...
echo ========================================================
C:\Python314\python.exe build_production.py --skip-installer
echo.
echo ========================================================
echo Build Complete! Output located in dist\CHARLIE\CHARLIE.exe
echo ========================================================
pause
