# N2SUB.py — Node 2 Subscriber (DDS float32 -> UDP double)
#
# Subscribes to DDS topic 'DatosSMTopic' (CoSimTypes::PingSM, float32),
# drains all available samples each cycle, and forwards ONLY the latest one
# via UDP (4 doubles, 32 bytes) to the MATLAB/Simulink model on Node 2.
#
# DDS input  : PingSM {I_demanda, V_SM, P_SM, I_SM} (float32)
# UDP output : 127.0.0.1:25000 | 32 bytes | struct '<dddd' (double, little-endian)
#
import os, socket, struct, time, sys, traceback
import rti.connextdds as dds
from CoSimTypes import CoSimTypes

# --------------------------------------------------
# Configuration — overridable via environment variables
# --------------------------------------------------
DOMAIN_ID      = int(os.getenv("DDS_DOMAIN_ID", "0"))           # DDS domain ID
TOPIC_NAME_IN  = os.getenv("DDS_TOPIC_PINGSM", "DatosSMTopic")  # DDS topic to subscribe to
UDP_DEST_IP    = os.getenv("UDP_DEST_IP_N2", "127.0.0.1")       # UDP destination (Simulink N2)
UDP_DEST_PORT  = int(os.getenv("UDP_DEST_PORT_N2", "25000"))     # UDP destination port
PACK_FMT_OUT   = "<dddd"                                          # 4 x double, little-endian
OUT_LEN        = struct.calcsize(PACK_FMT_OUT)                   # 32 bytes per packet
LOG_EVERY_N    = int(os.getenv("LOG_EVERY_N", "50"))             # print status every N samples

# --------------------------------------------------
# UDP output socket — sends data to Simulink Node 2
# --------------------------------------------------
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)  # 1 MB send buffer
dest = (UDP_DEST_IP, UDP_DEST_PORT)
print(f"[N2SUB] UDP destination: {dest} | Packet {OUT_LEN} B "
      f"(I_demanda, V_SM, P_SM, I_SM) [double]")

# --------------------------------------------------
# DDS DataReader — KEEP_LAST depth=1, BEST_EFFORT
# Anti-queue design: only the most recent PingSM sample is forwarded.
# --------------------------------------------------
PingSM = CoSimTypes.PingSM
participant = dds.DomainParticipant(DOMAIN_ID)
topic_in    = dds.Topic(participant, TOPIC_NAME_IN, PingSM)

reader_qos = dds.DataReaderQos()
reader_qos.reliability.kind   = dds.ReliabilityKind.BEST_EFFORT  # no retransmission
reader_qos.history.kind       = dds.HistoryKind.KEEP_LAST
reader_qos.history.depth      = 1                                  # keep only latest sample
reader_qos.resource_limits.max_samples                 = 4
reader_qos.resource_limits.initial_samples             = 4
reader_qos.reader_resource_limits.max_samples_per_read = 4

reader = dds.DataReader(participant.implicit_subscriber, topic_in, reader_qos)
print(f"[N2SUB] DDS ready | Domain={DOMAIN_ID} Topic='{TOPIC_NAME_IN}' "
      f"Type='PingSM' [float32, KEEP_LAST depth=1]")

# --------------------------------------------------
# Main loop: drain DDS queue, forward only the latest sample via UDP
# --------------------------------------------------
count = 0
last_hb = 0.0  # timestamp of last heartbeat print

try:
    while True:
        # Drain all available DDS samples, keep only the last valid one
        last = None
        while True:
            samples = reader.take()
            if not samples:
                break  # no more samples available
            for data, info in samples:
                if info.valid:
                    last = data  # overwrite with each valid sample

        if last is None:
            # No new data — wait 1 ms before retrying
            time.sleep(0.001)
            continue

        # Pack the latest sample as 4 doubles and send via UDP to Simulink Node 2
        payload = struct.pack(
            PACK_FMT_OUT,
            float(last.I_demanda),  # demand current from Node 1
            float(last.V_SM),       # voltage at master subsystem
            float(last.P_SM),       # active power at master subsystem
            float(last.I_SM),       # current at master subsystem
        )
        sock.sendto(payload, dest)

        count += 1
        if count % LOG_EVERY_N == 0:
            print(f"[N2SUB] DDS(float)->UDP(double) #{count} {dest} | "
                  f"I_demanda={last.I_demanda:.6f}, V_SM={last.V_SM:.6f}, "
                  f"P_SM={last.P_SM:.6f}, I_SM={last.I_SM:.6f}")

        # Periodic heartbeat every 5 seconds to confirm subscriber is alive
        now = time.time()
        if now - last_hb > 5.0:
            last_hb = now
            print(f"[N2SUB][HB] alive | domain={DOMAIN_ID} "
                  f"topic='{TOPIC_NAME_IN}' count={count}")

except KeyboardInterrupt:
    print("\n[N2SUB] Stopped by user.")
except Exception as e:
    print("[N2SUB][FATAL]", e)
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        sock.close()
    except Exception:
        pass
