# Launch_N1.py — Node 1 launcher
#
# Starts all three Node 1 processes in separate console windows:
#   - N1PUB.py  : DDS publisher (UDP -> DDS)
#   - N1SUB.py  : DDS subscriber (DDS -> UDP)
#   - N1_csv.py : data logger (UDP -> CSV)
#
# The user is prompted for:
#   1) Output CSV filename (without .csv extension)
#   2) Communication period Ts_comm (e.g. 0.5 ms, 1 ms, 2 ms, 0.001 s)
#
# Both values are passed to the child processes via environment variables
# to avoid redundant prompts.
#
import os, sys, subprocess, platform
from pathlib import Path


# --------------------------------------------------
# Step 1: ask for output filename
# --------------------------------------------------
while True:
    base_name = input("Output filename (without .csv): ").strip()
    if base_name:
        break

# Sanitize filename — remove characters invalid on Windows/Linux
for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
    base_name = base_name.replace(ch, "_")

out_dir = os.getenv("N1CSV_OUTDIR", "logs")
Path(out_dir).mkdir(parents=True, exist_ok=True)
output_csv = str(Path(out_dir) / f"{base_name}.csv")


# --------------------------------------------------
# Step 2: ask for communication period
# --------------------------------------------------
def parse_period_to_ms(txt: str) -> float:
    """
    Parses a period string and returns the value in milliseconds.
    Accepts formats like: '1', '1 ms', '0.5ms', '0.001 s', '1s'
    If no unit is specified, milliseconds are assumed.
    """
    raw = txt.strip().lower().replace(",", ".")
    if raw.endswith("ms"):
        return float(raw[:-2].strip())
    if raw.endswith("s"):
        return float(raw[:-1].strip()) * 1000.0
    return float(raw)  # no unit -> assume ms


ts_comm_ms = None
while ts_comm_ms is None:
    raw = input("Publication period (e.g.: 0.5 ms, 1 ms, 1.5 ms, 2 ms, 0.001 s): ")
    try:
        ts_comm_ms = parse_period_to_ms(raw)
        if ts_comm_ms <= 0:
            print("Period must be > 0.")
            ts_comm_ms = None
    except Exception:
        print("Invalid value. Examples: 0.5 ms | 1 ms | 1.5 ms | 2 ms | 0.001 s")

ts_comm_s = ts_comm_ms / 1000.0

print(f"[LAUNCH] Output file : {output_csv}")
print(f"[LAUNCH] Ts_comm     : {ts_comm_ms:.3f} ms")


# --------------------------------------------------
# Script paths
# --------------------------------------------------
base = Path(__file__).resolve().parent
PY   = os.getenv("PY", sys.executable)  # Python interpreter (overridable via env)

PUB = base / "N1PUB.py"    # DDS publisher
SUB = base / "N1SUB.py"    # DDS subscriber
CSV = base / "N1_csv.py"   # data logger

# Verify all scripts exist before launching
for script in [PUB, SUB, CSV]:
    if not script.exists():
        print(f"ERROR: script not found: {script}")
        sys.exit(1)


# --------------------------------------------------
# Helper: launch a script in a new console window
# --------------------------------------------------
def launch_new_console(cmd: list, extra_env: dict | None = None, title: str = ""):
    """
    Launches a command in a new console window.
    - Windows: uses CREATE_NEW_CONSOLE flag.
    - Linux: tries common terminal emulators (gnome-terminal, konsole, xterm, alacritty).
             Falls back to background subprocess if none are found.
    """
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    system = platform.system().lower()
    if system.startswith("win"):
        CREATE_NEW_CONSOLE = 0x00000010
        subprocess.Popen(cmd, creationflags=CREATE_NEW_CONSOLE, cwd=str(base), env=env)
    else:
        tried = False
        for term in [["gnome-terminal", "--"], ["konsole", "-e"],
                     ["xterm", "-e"], ["alacritty", "-e"]]:
            try:
                subprocess.Popen(term + cmd, cwd=str(base), env=env)
                tried = True
                break
            except FileNotFoundError:
                continue
        if not tried:
            # No terminal emulator found — launch in background
            subprocess.Popen(cmd, cwd=str(base), env=env)


# --------------------------------------------------
# Build commands and environment variables for each process
# --------------------------------------------------

# Logger: receives the full CSV path via env to skip its own prompt
csv_env = {"N1CSV_OUTPUT_CSV": output_csv}
csv_cmd = [PY, str(CSV)]

# Publisher: receives Ts_comm in both seconds (OUT_TS) and ms (TS_COMM_MS)
# Both formats provided for maximum compatibility
pub_env = {"OUT_TS": str(ts_comm_s), "TS_COMM_MS": str(ts_comm_ms)}
pub_cmd = [PY, str(PUB)]

# Subscriber: no extra parameters needed
sub_cmd = [PY, str(SUB)]


# --------------------------------------------------
# Launch all three processes
# --------------------------------------------------
launch_new_console(pub_cmd, extra_env=pub_env, title="N1PUB")
launch_new_console(sub_cmd, title="N1SUB")
launch_new_console(csv_cmd, extra_env=csv_env, title="N1_LOGGER")

print("[LAUNCH] Started 3 console windows: N1PUB, N1SUB, N1_LOGGER")
