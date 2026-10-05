@echo off
setlocal
echo ==============================================================================
echo  CHARLIE Code Signing Pipeline
echo ==============================================================================
python "%~dp0sign_installer.py" --all
pause
