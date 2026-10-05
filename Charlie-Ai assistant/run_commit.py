"""run_commit.py — Click the green 'Run Python File' play button in VS Code to commit."""
import subprocess
import sys
from pathlib import Path

repo_dir = Path(__file__).resolve().parent

print("=" * 60)
print("Executing Git Commit for Charlie changes...")
print("=" * 60)

try:
    r1 = subprocess.run(["git", "add", "-A"], cwd=repo_dir, capture_output=True, text=True)
    print("[1/2] git add -A:", "OK" if r1.returncode == 0 else r1.stderr)

    msg = "feat(core): calibrate FACS digital human, boost brain cache, and add DAG planner"
    r2 = subprocess.run(["git", "commit", "-m", msg], cwd=repo_dir, capture_output=True, text=True)
    print("[2/2] git commit:")
    print(r2.stdout or r2.stderr)

    r3 = subprocess.run(["git", "status", "-s"], cwd=repo_dir, capture_output=True, text=True)
    print("Status:\n", r3.stdout or "Clean working directory.")
except Exception as e:
    print(f"Error executing git: {e}")

input("\nPress Enter to exit...")
