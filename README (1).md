# Distributed Real-Time Co-Simulation Architecture
## OPAL-RT + RTI Connext DDS + MATLAB/Simulink

**Author:** Sebastián Escobar Rojas  
**Institution:** Universidad de O'Higgins, Chile  
**Degree:** Civil Electrical Engineer (2025)  
**Thesis title:** *Implementation and validation of a geographically distributed real-time co-simulation scheme for electrical systems analysis based on OPAL-RT and RTI Connext DDS*  
**Academic advisor:** Dr. Claudio Burgos Mellado  
**RTI University Program** — License granted by RTI (Real-Time Innovations)

---

## Overview

This repository contains the Python scripts developed for the thesis project. The architecture implements a **two-node distributed real-time co-simulation** of electrical systems, where:

- **Node 1** hosts the Master Subsystem (SM) and the Communication Subsystem (SC), running on MATLAB/Simulink 2019 and OPAL-RT OP4200.
- **Node 2** hosts the Load model (R-L-C circuit), receiving Thévenin equivalent signals from Node 1 and returning demand current.

Communication between nodes is handled via **RTI Connext DDS**, using Python UDP↔DDS bridges due to hardware constraints (OPAL-RT OP4200 + RT-LAB 2020 are only compatible with MATLAB/Simulink 2019, which does not include the native DDS Blockset).

---

## Signal Contract

Two DDS topics are defined in `CoSimTypes.idl`:

| Topic | Direction | Signals |
|-------|-----------|---------|
| `DatosSMTopic` (PingSM) | Node 1 → DDS | `I_demanda`, `V_SM`, `P_SM`, `I_SM` |
| `DatosN2Topic` (PongN2) | Node 2 → Node 1 | `I_demanda_eco2`, `I_demanda` |

DDS QoS configuration: `Reliability = BEST_EFFORT`, `History = KEEP_LAST (depth=1)` — prioritizes the most recent sample and avoids queue buildup.

---

## Repository Structure

```
├── CoSimTypes.idl       # DDS data type definitions (IDL)
├── CoSimTypes.py        # Auto-generated Python bindings (rtiddsgen 4.5.0)
├── N1PUB.py             # Node 1 Publisher: UDP → DDS (float32), with drain + pacing
├── N1SUB.py             # Node 1 Subscriber: DDS → UDP (double), drain anti-queue
├── N1_csv.py            # Data logger: UDP binary → CSV (temporal metrics)
├── Launch_N1.py         # Launcher: opens N1PUB, N1SUB and N1_csv in 3 consoles
└── README.md            # This file
```

---

## File Descriptions

### `CoSimTypes.idl`
IDL definition of the two DDS data types used in the co-simulation:
- `PingSM`: signals sent from Node 1 to the DDS network (demand current, voltage, active power, current from SM).
- `PongN2`: signals returned by Node 2 to Node 1 (echo and confirmed demand current).

### `CoSimTypes.py`
Auto-generated Python bindings from `CoSimTypes.idl` using RTI Code Generator (rtiddsgen) v4.5.0. Do not modify manually.

### `N1PUB.py`
Node 1 Publisher. Receives 4 doubles (32 bytes) via UDP from the OPAL-RT Simulink model, converts them to float32, and publishes them to the DDS topic `DatosSMTopic`. Key features:
- Configurable communication period (`Ts_comm`) via argument, environment variable, or interactive prompt.
- Drain + pacing loop: always publishes the most recent UDP sample at the exact configured period.
- Optional binary copy to local UDP logger (N1_csv.py).
- Windows timer resolution boost for sub-millisecond periods.

### `N1SUB.py`
Node 1 Subscriber. Reads DDS topic `DatosN2Topic` (PongN2, float32), drains all available samples and keeps only the latest, then forwards it as 2 doubles (16 bytes) via UDP to the OPAL-RT model. Anti-queue design: `KEEP_LAST depth=1`, prevents backlog accumulation.

### `N1_csv.py`
Data logger. Listens for 4 doubles per UDP packet from N1PUB and writes them to a CSV file with wall-clock timestamps (nanosecond resolution). Supports block-based flushing for performance. Used to capture temporal metrics (latency, jitter, packet loss).

### `Launch_N1.py`
Launcher script. Asks the user for a filename and communication period, then opens three separate console windows running N1PUB, N1SUB, and N1_csv simultaneously. Compatible with Windows and Linux.

---

## Requirements

- **RTI Connext DDS** (University Program License — [apply here](https://www.rti.com/university))
- **Python 3.x** with `rti.connextdds` package
- **MATLAB/Simulink 2019** (for Simulink models)
- **OPAL-RT RT-LAB 2020** (for hardware-in-the-loop scenarios)

---

## Experimental Setup

| Parameter | Value |
|-----------|-------|
| OPAL-RT platform | OP4200 |
| RT-LAB version | 2020 |
| MATLAB/Simulink | 2019 |
| Communication network | 3G/5G mobile hotspot (university multicast blocked) |
| Ts_core (OPAL step) | 0.5 ms |
| Ts_comm tested | 0.5 / 1.0 / 1.5 / 2.5 ms |
| Simulation duration | ~40 s per run |
| Repetitions per case | 4 |

**Key result:** Stable operation (0% packet loss) achieved from Ts_comm = 1.0 ms onward. At Ts_comm = 0.5 ms, packet loss reached ~36% due to network limitations — this is documented and analyzed in the thesis.

---

## Note on Simulink Models

The Simulink models (DC and AC R-L-C circuits) are not included in this repository due to version compatibility constraints (MATLAB/Simulink 2019 + RT-LAB 2020). The models are simple R-L-C circuits and can be reconstructed from the signal contract defined in `CoSimTypes.idl` and the thesis document.

---

## Citation

If you use this work, please cite:

> Escobar Rojas, S. (2025). *Implementación y validación de un esquema de co-simulación distribuida geográficamente para el análisis de sistemas eléctricos en tiempo real basada en OPAL-RT y RTI Connext DDS*. Undergraduate thesis, Universidad de O'Higgins, Chile.

---

## Acknowledgements

This work was supported by the **RTI University Program** (Real-Time Innovations). Special thanks to Ángel Martínez Bernal for the license management and technical feedback.

Funded in part by **ANID/FONDEQUIP/EQM230041** (Agencia Nacional de Investigación y Desarrollo, Chile).
