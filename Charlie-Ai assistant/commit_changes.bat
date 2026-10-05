@echo off
cd /d "%~dp0"
echo Staging and committing changes...
git add -A
git commit -m "feat(v1.0): implement features 1-4: credit add-ons, device pairing, mini HUD, and filmora preflight"
echo.
git status
pause
