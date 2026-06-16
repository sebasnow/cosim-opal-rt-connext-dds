# N1PUB.py — Node 1 Publisher (UDP double -> DDS float32) with drain + pacing
#
# Receives 4 doubles (32 bytes) per UDP packet from the OPAL-RT/Simulink model,
# converts them to float32, and publishes them to the DDS topic 'DatosSMTopic'.
#
# Communication period (Ts_comm) can be set via:
#   --ts-comm-ms <value>          command-line argument (in ms)
#   OUT_TS=<value>                environment variable (in seconds)
#   interactive prompt            if neither of the above is provided
#
# Usage:
#   python N1PUB.py                        # interactive prompt
#   python N1PUB.py --ts-comm-ms 1.0       # 1 ms period
#   set OUT_TS=0.001 && python N1PUB.py    # Windows, 1 ms period
#
import os, socket, struct, sys, traceback, argparse, platform
from time import perf_counter_ns, sleep
import rti.connextdds as dds
from CoSimTypes import CoSimTypes


def _parse_ts_comm(args_ts_ms: float | None):
    """
    Resolves the publication period (in seconds), using the following priority:
    1) --ts-comm-ms argument (in ms)
    2) OUT_TS environment variable (in seconds)
    3) Interactive console prompt (accepts '0.5', '0.5 ms', '1 ms', '0.001 s', etc.)
    """
    # Priority 1: explicit command-line argument (ms)
    if args_ts_ms is not None:
        return float(args_ts_ms) / 1000.0

    # Priority 2: environment variable (seconds)
    env_ts = os.getenv("OUT_TS", "").strip()
    if env_ts:
        try:
            return float(env_ts)
        except ValueError:
            pass  # fall through to interactive prompt

    # Priority 3: interactive prompt
    while True:
        raw = input("Publication period (e.g.: 0.5 ms, 1 ms, 2 ms or 0.001 s): ").strip().lower()
        raw = raw.replace(",", ".")
        if not raw:
            continue
        try:
            if raw.endswith("ms"):
                v = float(raw[:-2].strip()) / 1000.0
                if v > 0: return v
            elif raw.endswith("s"):
                v = float(raw[:-1].strip())
                if v > 0: return v
            else:
                # no unit specified — assume ms
                v = float(raw) / 1000.0
                if v > 0: return v
        except ValueError:
            pass
        print("Invalid value. Examples: '0.5 ms', '1 ms', '1.5 ms', '0.001 s'.")


def _maybe_boost_timer_resolution(ts_comm_s: float):
    """
    On Windows, if Ts_comm <= 1 ms, increases the OS timer resolution
    using timeBeginPeriod(1). This reduces sleep jitter for sub-ms periods.
    The boost is reverted on exit.
    """
    if platform.system().lower().startswith("win") and ts_comm_s <= 0.0015:
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
            return True
        except Exception:
            return False
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts-comm-ms", type=float, default=None,
                    help="Publication period in milliseconds (e.g. 1.0). "
                         "If not provided, falls back to OUT_TS env var or interactive prompt.")
    args = ap.parse_args()

    # --------------------------------------------------
    # Configuration — overridable via environment variables
    # --------------------------------------------------
    DOMAIN_ID     = int(os.getenv("DDS_DOMAIN_ID", "0"))       # DDS domain ID
    TOPIC_NAME    = os.getenv("DDS_TOPIC_PINGSM", "DatosSMTopic")  # DDS topic name
    UDP_BIND_IP   = os.getenv("UDP_BIND_IP", "0.0.0.0")        # UDP listen address
    UDP_BIND_PORT = int(os.getenv("UDP_BIND_PORT", "21000"))    # UDP listen port
    PACK_FMT_IN   = "<dddd"                                      # 4 x double, little-endian
    IN_LEN        = struct.calcsize(PACK_FMT_IN)                 # 32 bytes expected per packet
    LOG_EVERY_N   = int(os.getenv("LOG_EVERY_N", "50"))         # print status every N samples

    LOG_UDP_ENABLE = os.getenv("LOG_UDP_ENABLE", "1") == "1"    # enable binary copy to logger
    LOG_UDP_HOST   = os.getenv("LOG_UDP_HOST", "127.0.0.1")     # logger destination IP
    LOG_UDP_PORT   = int(os.getenv("LOG_UDP_PORT", "26001"))     # logger destination port
    PACK_FMT_LOG   = "<dddd"                                     # 4 x double for logger

    ts_comm_s = _parse_ts_comm(args.ts_comm_ms)
    print(f"[N1PUB] Selected publication period: {ts_comm_s*1000:.3f} ms")

    # --------------------------------------------------
    # UDP socket (non-blocking) — receives data from Simulink/OPAL-RT
    # --------------------------------------------------
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)  # 4 MB receive buffer
    sock.bind((UDP_BIND_IP, UDP_BIND_PORT))
    sock.setblocking(False)  # non-blocking: drain loop reads all available packets
    print(f"[N1PUB] Listening for UDP on {UDP_BIND_IP}:{UDP_BIND_PORT} "
          f"({IN_LEN} B per packet: I_demanda, V_SM, P_SM, I_SM) [double -> float32 | drain+pacing]")

    # --------------------------------------------------
    # Optional UDP logger socket — forwards raw data to N1_csv.py
    # --------------------------------------------------
    log_sock = None
    log_addr = None
    if LOG_UDP_ENABLE:
        log_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        log_addr = (LOG_UDP_HOST, LOG_UDP_PORT)
        print(f"[N1PUB] UDP logger enabled -> {LOG_UDP_HOST}:{LOG_UDP_PORT} (binary, 4 doubles)")

    # --------------------------------------------------
    # DDS DataWriter — KEEP_LAST depth=1, BEST_EFFORT
    # Publishes PingSM samples to DDS topic 'DatosSMTopic'
    # QoS: always publish the most recent sample, no queue buildup
    # --------------------------------------------------
    PingSM = CoSimTypes.PingSM
    participant = dds.DomainParticipant(DOMAIN_ID)
    topic       = dds.Topic(participant, TOPIC_NAME, PingSM)

    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind  = dds.ReliabilityKind.BEST_EFFORT  # no retransmission
    writer_qos.history.kind      = dds.HistoryKind.KEEP_LAST
    writer_qos.history.depth     = 1                                  # keep only the latest sample
    writer_qos.resource_limits.max_samples     = 4
    writer_qos.resource_limits.initial_samples = 4

    writer = dds.DataWriter(participant.implicit_publisher, topic, writer_qos)
    print(f"[N1PUB] DDS ready | Domain={DOMAIN_ID} Topic='{TOPIC_NAME}' Type='PingSM' "
          f"[float32, depth=1, Ts_comm={ts_comm_s}s]")

    boosted = _maybe_boost_timer_resolution(ts_comm_s)

    # --------------------------------------------------
    # Main loop: drain + pacing
    #
    # Design rationale:
    # - Drain: read ALL available UDP packets each cycle, keep only the latest.
    #   This prevents queue buildup when Simulink sends faster than DDS publishes.
    # - Pacing: publish exactly once per Ts_comm tick using high-resolution
    #   monotonic clock (perf_counter_ns). Missed ticks are skipped forward.
    # --------------------------------------------------
    count = 0
    last_values = None          # most recent sample as tuple of 4 doubles
    TICK_NS = max(1, int(ts_comm_s * 1_000_000_000))  # period in nanoseconds
    next_ns = perf_counter_ns()

    try:
        while True:
            # Step 1: drain all available UDP packets, keep only the last one
            last_pkt = None
            while True:
                try:
                    data, addr = sock.recvfrom(256)
                    last_pkt = data
                except (BlockingIOError, InterruptedError):
                    break  # no more packets available
                except Exception as e:
                    print("[N1PUB][UDP][ERROR]", e)
                    last_pkt = None
                    break

            # Unpack the latest packet if valid (exactly 32 bytes = 4 doubles)
            if last_pkt is not None and len(last_pkt) == IN_LEN:
                try:
                    last_values = struct.unpack(PACK_FMT_IN, last_pkt)
                except struct.error:
                    pass

            now_ns = perf_counter_ns()

            # Step 2: publish at the exact tick boundary
            if now_ns >= next_ns:
                if last_values is not None:
                    I_demanda_d, V_SM_d, P_SM_d, I_SM_d = last_values

                    # Publish to DDS as float32
                    sample = PingSM()
                    sample.I_demanda = float(I_demanda_d)
                    sample.V_SM      = float(V_SM_d)
                    sample.P_SM      = float(P_SM_d)
                    sample.I_SM      = float(I_SM_d)
                    writer.write(sample)

                    # Forward raw doubles to the CSV logger (N1_csv.py)
                    if log_sock is not None:
                        try:
                            log_sock.sendto(
                                struct.pack(PACK_FMT_LOG, I_demanda_d, V_SM_d, P_SM_d, I_SM_d),
                                log_addr
                            )
                        except Exception:
                            pass

                    count += 1
                    if count % LOG_EVERY_N == 0:
                        print(f"[N1PUB] UDP->DDS #{count} | "
                              f"I_dem={I_demanda_d:.6f}, V_SM={V_SM_d:.6f}, "
                              f"P_SM={P_SM_d:.6f}, I_SM={I_SM_d:.6f}")

                # Advance to next tick — skip missed ticks if we fell behind
                ticks_missed = (now_ns - next_ns) // TICK_NS
                next_ns += (1 + ticks_missed) * TICK_NS

            else:
                # Coarse sleep + micro-spin for sub-ms precision
                remain = (next_ns - now_ns) / 1e9
                if remain > 0.0002:
                    sleep(remain - 0.0001)  # sleep until ~100 µs before the tick
                # final ~100 µs left to the OS scheduler (busy wait)

    except KeyboardInterrupt:
        print("\n[N1PUB] Stopped by user.")
    except Exception as e:
        print("[N1PUB][FATAL]", e)
        traceback.print_exc()
        sys.exit(1)
    finally:
        try: sock.close()
        except Exception: pass
        try:
            if log_sock is not None:
                log_sock.close()
        except Exception: pass
        # Restore Windows timer resolution
        if boosted:
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


if __name__ == "__main__":
    main()
