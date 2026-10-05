@echo off
cd /d "%~dp0"
echo Starting CHARLIE...
if exist "C:\Python314\python.exe" (
    "C:\Python314\python.exe" main.py
) else (
    python main.py
)
