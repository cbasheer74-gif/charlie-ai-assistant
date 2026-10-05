import subprocess
import sys
from pathlib import Path

cwd = Path(r"c:\Users\aney\Downloads\Charlie-main-1.0\Charlie-Ai assistant")
py = Path(r"c:\Users\aney\Downloads\Charlie-main-1.0\.venv\Scripts\python.exe")

proc = subprocess.Popen(
    [str(py), "main.py"],
    cwd=str(cwd),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="replace"
)

try:
    stdout, stderr = proc.communicate(timeout=25)
    print("EXIT_CODE:", proc.returncode)
    print("STDOUT_TAIL:\n", stdout[-600:] if stdout else "")
    print("STDERR_TAIL:\n", stderr[-600:] if stderr else "")
except subprocess.TimeoutExpired:
    proc.terminate()
    print("STILL_RUNNING_AFTER_25S: OK")
