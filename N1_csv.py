# N1_csv.py — UDP binary logger -> CSV (block-based write)
#
# Listens for UDP packets containing 4 doubles (I_demanda, V_SM, P_SM, I_SM)
# sent by N1PUB.py, and writes them to a CSV file with nanosecond wall-clock
# timestamps. Used to capture temporal metrics (latency, jitter, packet loss).
#
# Output format: logs/<name>.csv
# CSV columns: t_wall_ns, I_demanda, V_SM, P_SM, I_SM
#
# Usage:
#   python N1_csv.py                        # interactive prompt for filename
#   N1CSV_OUTPUT_CSV=logs/test.csv python N1_csv.py   # filename via env (used by launcher)
#   N1CSV_OUTDIR=my_folder python N1_csv.py            # custom output directory
#
import socket, struct, threading, queue, time, os, argparse


def _ask_output_csv() -> str:
    """
    Resolves the output CSV file path.
    Priority:
    1) N1CSV_OUTPUT_CSV environment variable — used by Launch_N1.py to avoid the prompt.
    2) Interactive prompt — asks the user for a base name (without .csv extension).
    """
    # Priority 1: path provided by the launcher via environment variable
    env_path = os.getenv("N1CSV_OUTPUT_CSV", "").strip()
    if env_path:
        out_dir = os.path.dirname(env_path) or "."
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception:
            pass
        print(f"[N1_CSV] Output path (from env): {env_path}")
        return env_path

    # Priority 2: interactive prompt
    base_name = ""
    while not base_name:
        base_name = input("Output filename (without .csv): ").strip()
    if base_name.lower().endswith(".csv"):
        base_name = base_name[:-4]

    # Sanitize filename — remove characters invalid on Windows/Linux
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        base_name = base_name.replace(ch, "_")

    out_dir = os.getenv("N1CSV_OUTDIR", "logs")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    path = os.path.join(out_dir, f"{base_name}.csv")
    print(f"[N1_CSV] Output path: {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0",
                    help="UDP listen address (default: 0.0.0.0)")
    ap.add_argument("--port", type=int, default=26001,
                    help="UDP listen port (default: 26001, must match N1PUB LOG_UDP_PORT)")
    ap.add_argument("--flush", type=int, default=2000,
                    help="Number of rows per write block (default: 2000)")
    ap.add_argument("--rcvbuf", type=int, default=4*1024*1024,
                    help="UDP receive buffer size in bytes (default: 4 MB)")
    args = ap.parse_args()

    OUTPUT_PATH = _ask_output_csv()

    # --------------------------------------------------
    # UDP socket — receives binary data from N1PUB
    # --------------------------------------------------
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, args.rcvbuf)
    sock.bind((args.host, args.port))

    # Thread-safe queue between receiver loop and file writer thread
    q = queue.SimpleQueue()
    stop = threading.Event()

    def writer():
        """
        Background thread: dequeues formatted CSV lines and writes them
        to disk in blocks for performance. Flushes on block size or on stop signal.
        """
        pending = []
        with open(OUTPUT_PATH, "w", buffering=1024*1024, newline="") as f:
            f.write("t_wall_ns,I_demanda,V_SM,P_SM,I_SM\n")  # CSV header
            while not stop.is_set() or not q.empty():
                try:
                    line = q.get(timeout=0.1)
                except queue.Empty:
                    line = None
                if line is not None:
                    pending.append(line)
                # Write block when full or when stopping
                if len(pending) >= args.flush or (stop.is_set() and pending):
                    f.writelines(pending)
                    pending.clear()
                    f.flush()

    threading.Thread(target=writer, daemon=True).start()

    print(f"[N1_CSV] Listening on UDP {args.host}:{args.port} "
          f"(4 doubles per packet) -> {OUTPUT_PATH}")

    drops = 0   # packets with wrong size or unpack error
    total = 0   # successfully received and queued samples
    PACK_FMT = "<dddd"
    PACK_LEN = struct.calcsize(PACK_FMT)  # 32 bytes

    try:
        while True:
            data, _ = sock.recvfrom(4096)
            tns = time.perf_counter_ns()  # wall-clock timestamp (nanoseconds)

            # Discard packets shorter than expected
            if len(data) < PACK_LEN:
                drops += 1
                continue

            # Unpack 4 doubles from the binary payload
            try:
                I_dem, V, P, I = struct.unpack(PACK_FMT, data[:PACK_LEN])
            except struct.error:
                drops += 1
                continue

            # Enqueue formatted CSV line
            q.put(f"{tns},{I_dem:.9f},{V:.9f},{P:.9f},{I:.9f}\n")
            total += 1

            if total % 1000 == 0:
                print(f"[N1_CSV] samples={total} drops={drops}")

    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        time.sleep(0.2)  # allow writer thread to flush remaining data
        sock.close()
        loss_pct = (drops / max(1, drops + total)) * 100.0
        print(f"[N1_CSV] Done. Received={total} | Drops={drops} ({loss_pct:.2f}%)")


if __name__ == "__main__":
    main()
