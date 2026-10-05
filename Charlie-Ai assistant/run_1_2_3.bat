@echo off
cd /d "%~dp0"
echo ========================================================
echo STEP 1/3: Running Test Suite (Features 1-4)...
echo ========================================================
python -m unittest tests/test_features_1234.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Unit tests failed! Halting pipeline.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================
echo STEP 2/3: Building Production EXE and Code Signing...
echo ========================================================
python build_production.py --skip-installer
if exist dist\CHARLIE\CHARLIE.exe (
    python scripts\sign_installer.py --file dist\CHARLIE\CHARLIE.exe
)

echo.
echo ========================================================
echo STEP 3/3: Staging and Committing to Git...
echo ========================================================
git add -A
git commit -m "feat(v1.0): implement features 1-4: credit add-ons, device pairing, mini HUD, and filmora preflight"
git status -s

echo.
echo ========================================================
echo PIPELINE COMPLETE: Steps 1, 2, and 3 Finished Successfully!
echo ========================================================
pause
