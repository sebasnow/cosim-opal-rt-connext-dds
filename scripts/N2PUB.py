# N2PUB.py — Node 2 Publisher (UDP double -> DDS float32) with anti-queue drain
#
# Receives 2 doubles (16 bytes) per UDP packet from the MATLAB/Simulink model
# on Node 2 (I_demanda_eco2, I_demanda), drains the UDP buffer to keep only
# the latest packet, and publishes CoSimTypes::PongN2 (float32) to DDS.
#
# UDP input  : 0.0.0.0:21001 | 16 bytes | struct '<dd' (double, little-endian)
# DDS output : Domain 0, Topic 'DatosN2Topic', Type CoSimTypes::PongN2 (float32)
#
import os, socket, struct, time, sys, traceback
import rti.connextdds as dds
from CoSimTypes import CoSimTypes

# --------------------------------------------------
# Configuration — overridable via environment variables
# --------------------------------------------------
DOMAIN_ID     = int(os.getenv("DDS_DOMAIN_ID", "0"))            # DDS domain ID
TOPIC_NAME    = os.getenv("DDS_TOPIC_PONGN2", "DatosN2Topic")   # DDS topic to publish to
TYPE_NAME     = "PongN2"

UDP_BIND_IP   = os.getenv("UDP_BIND_IP_N2PUB", "0.0.0.0")       # listen on all interfaces
UDP_BIND_PORT = int(os.getenv("UDP_BIND_PORT_N2PUB", "21001"))   # UDP listen port

PACK_FMT_IN   = "<dd"                                             # 2 x double, little-endian
IN_LEN        = struct.calcsize(PACK_FMT_IN)                     # 16 bytes expected per packet
LOG_EVERY_N   = int(os.getenv("LOG_EVERY_N", "20"))              # print status every N samples

# --------------------------------------------------
# UDP socket (non-blocking) — receives data from Simulink Node 2
# Anti-queue: non-blocking mode allows draining all buffered packets
# --------------------------------------------------
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)  # 1 MB receive buffer
sock.bind((UDP_BIND_IP, UDP_BIND_PORT))
sock.setblocking(False)  # non-blocking: drain loop reads all available packets
print(f"[N2PUB] Listening for UDP on {UDP_BIND_IP}:{UDP_BIND_PORT} "
      f"({IN_LEN} B per packet: I_demanda_eco2, I_demanda) "
      f"[double -> float32 | anti-queue ENABLED]")

# --------------------------------------------------
# DDS DataWriter — KEEP_LAST depth=1, BEST_EFFORT
# Publishes PongN2 samples to DDS topic 'DatosN2Topic'
# QoS: always publish the most recent sample, no queue buildup
# --------------------------------------------------
PongN2 = CoSimTypes.PongN2

participant = dds.DomainParticipant(DOMAIN_ID)
topic       = dds.Topic(participant, TOPIC_NAME, PongN2)

writer_qos = dds.DataWriterQos()
writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT  # no retransmission
writer_qos.history.kind     = dds.HistoryKind.KEEP_LAST
writer_qos.history.depth    = 1                                  # keep only the latest sample
writer_qos.resource_limits.max_samples     = 4
writer_qos.resource_limits.initial_samples = 4

writer = dds.DataWriter(participant.implicit_publisher, topic, writer_qos)
print(f"[N2PUB] DDS ready | Domain={DOMAIN_ID} Topic='{TOPIC_NAME}' "
      f"Type='{TYPE_NAME}' [float32, KEEP_LAST depth=1]")

# --------------------------------------------------
# Main loop: drain UDP buffer, publish only the latest sample to DDS
# --------------------------------------------------
count = 0
last_hb = 0.0  # timestamp of last heartbeat print

try:
    while True:
        # Drain all buffered UDP packets, keep only the last valid one
        last = None
        while True:
            try:
                data, addr = sock.recvfrom(256)
            except (BlockingIOError, InterruptedError):
                break  # no more packets available
            if len(data) == IN_LEN:
                last = (data, addr)  # overwrite with each valid packet

        if last is None:
            # No new data — yield CPU for 1 ms
            time.sleep(0.001)
            continue

        data, addr = last
        try:
            I_eco2_d, I_dem_d = struct.unpack(PACK_FMT_IN, data)
        except struct.error:
            continue  # malformed packet — discard

        # Publish to DDS as float32
        sample = PongN2()
        sample.I_demanda_eco2 = float(I_eco2_d)  # echo current returned by Node 2
        sample.I_demanda      = float(I_dem_d)   # demand current computed by Node 2
        writer.write(sample)

        count += 1
        if count % LOG_EVERY_N == 0:
            print(f"[N2PUB] UDP->DDS #{count} {addr} | "
                  f"I_demanda_eco2={I_eco2_d:.6f}, I_demanda={I_dem_d:.6f}")

        # Periodic heartbeat every 5 seconds to confirm publisher is alive
        now = time.time()
        if now - last_hb > 5.0:
            last_hb = now
            print(f"[N2PUB][HB] alive | domain={DOMAIN_ID} "
                  f"topic='{TOPIC_NAME}' count={count}")

except KeyboardInterrupt:
    print("\n[N2PUB] Stopped by user.")
except Exception as e:
    print("[N2PUB][FATAL]", e)
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        sock.close()
    except Exception:
        pass
