# N1SUB.py — Node 1 Subscriber (DDS -> UDP) with anti-queue drain
#
# Subscribes to DDS topic 'DatosN2Topic' (CoSimTypes::PongN2, float32),
# drains all available DDS samples each cycle, and forwards ONLY the latest
# one via UDP (2 doubles, 16 bytes) to the OPAL-RT/Simulink model on Node 1.
#
# UDP output: 127.0.0.1:25001 | 16 bytes | struct '<dd' (I_demanda_eco2, I_demanda)
#
import os, socket, struct, time, sys, traceback
import rti.connextdds as dds
from CoSimTypes import CoSimTypes

# --------------------------------------------------
# Configuration — overridable via environment variables
# --------------------------------------------------
DOMAIN_ID      = int(os.getenv("DDS_DOMAIN_ID", "0"))           # DDS domain ID
TOPIC_NAME_IN  = os.getenv("DDS_TOPIC_PONGN2", "DatosN2Topic")  # DDS topic to subscribe to
UDP_DEST_IP    = os.getenv("UDP_DEST_IP_N1", "127.0.0.1")       # UDP destination IP (Simulink)
UDP_DEST_PORT  = int(os.getenv("UDP_DEST_PORT_N1", "25001"))     # UDP destination port
PACK_FMT_OUT   = "<dd"                                            # 2 x double, little-endian
OUT_LEN        = struct.calcsize(PACK_FMT_OUT)                   # 16 bytes per packet
LOG_EVERY_N    = int(os.getenv("LOG_EVERY_N", "20"))             # print status every N samples

# --------------------------------------------------
# UDP output socket — sends data back to Simulink/OPAL-RT
# --------------------------------------------------
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)  # 1 MB send buffer
dest = (UDP_DEST_IP, UDP_DEST_PORT)
print(f"[N1SUB] UDP destination: {dest} | Packet {OUT_LEN} B (I_demanda_eco2, I_demanda) [double]")

# --------------------------------------------------
# DDS DataReader — KEEP_LAST depth=1, BEST_EFFORT
# Anti-queue design: depth=1 ensures only the most recent sample is kept.
# Previous setting of depth=32 caused backlog accumulation at high frequencies.
# --------------------------------------------------
PongN2 = CoSimTypes.PongN2
participant = dds.DomainParticipant(DOMAIN_ID)
topic_in    = dds.Topic(participant, TOPIC_NAME_IN, PongN2)

reader_qos = dds.DataReaderQos()
reader_qos.reliability.kind   = dds.ReliabilityKind.BEST_EFFORT  # no retransmission
reader_qos.history.kind       = dds.HistoryKind.KEEP_LAST
reader_qos.history.depth      = 1                                  # keep only latest sample
reader_qos.resource_limits.max_samples                 = 4
reader_qos.resource_limits.initial_samples             = 4
reader_qos.reader_resource_limits.max_samples_per_read = 4

reader = dds.DataReader(participant.implicit_subscriber, topic_in, reader_qos)
print(f"[N1SUB] DDS ready | Domain={DOMAIN_ID} Topic='{TOPIC_NAME_IN}' Type='PongN2' "
      f"[float32, KEEP_LAST depth=1]")

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

        # Pack the latest sample as 2 doubles and send via UDP
        payload = struct.pack(
            PACK_FMT_OUT,
            float(last.I_demanda_eco2),  # echo current from Node 2
            float(last.I_demanda),       # demand current confirmed by Node 2
        )
        sock.sendto(payload, dest)

        count += 1
        if count % LOG_EVERY_N == 0:
            print(f"[N1SUB] DDS(float)->UDP(double) #{count} {dest} | "
                  f"I_demanda_eco2={last.I_demanda_eco2:.6f}, I_demanda={last.I_demanda:.6f}")

        # Periodic heartbeat every 5 seconds to confirm the subscriber is alive
        now = time.time()
        if now - last_hb > 5.0:
            last_hb = now
            print(f"[N1SUB][HB] alive | domain={DOMAIN_ID} topic='{TOPIC_NAME_IN}' count={count}")

except KeyboardInterrupt:
    print("\n[N1SUB] Stopped by user.")
except Exception as e:
    print("[N1SUB][FATAL]", e)
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        sock.close()
    except Exception:
        pass
