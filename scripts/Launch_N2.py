# Launch_N2.py — Node 2 launcher
#
# Starts both Node 2 processes in separate console windows:
#   - N2SUB.py : DDS subscriber (DDS -> UDP) — receives PingSM from Node 1
#   - N2PUB.py : DDS publisher  (UDP -> DDS) — sends PongN2 back to Node 1
#
# No user input required — both scripts use default ports unless
# overridden via environment variables.
#
import subprocess
import os
from pathlib import Path

base = Path(__file__).resolve().parent
SCRIPT_PUB = str(base / "N2PUB.py")
SCRIPT_SUB = str(base / "N2SUB.py")


def launch_in_terminal(script: str):
    """
    Launches a Python script in a new console window.
    - Windows: opens a new cmd window using 'start'.
    - Linux/Mac: tries gnome-terminal; falls back to xterm or background process.
    """
    if os.name == "nt":  # Windows
        subprocess.Popen(
            ["start", "cmd", "/k", f"python {script}"],
            shell=True
        )
    else:  # Linux / macOS
        for term in [["gnome-terminal", "--"], ["xterm", "-e"], ["konsole", "-e"]]:
            try:
                subprocess.Popen(term + ["python3", script])
                return
            except FileNotFoundError:
                continue
        # Fallback: run in background if no terminal emulator found
        subprocess.Popen(["python3", script])


if __name__ == "__main__":
    print("[LAUNCH N2] Starting Node 2: Publisher and Subscriber...")
    launch_in_terminal(SCRIPT_SUB)  # start subscriber first
    launch_in_terminal(SCRIPT_PUB)
    print("[LAUNCH N2] Started 2 console windows: N2SUB, N2PUB")
