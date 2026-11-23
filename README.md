# Automated Warehouse AGV & ASRS Simulation

A discrete-event simulation of an automated warehouse built with Python and `salabim`. The model simulates a fleet of Automated Guided Vehicles (AGVs) coordinating with Automated Storage and Retrieval Systems (ASRS) to fulfill customer orders, with live 2D animation and MP4 video export.

## Project Goal

The objective of this simulation is to evaluate warehouse performance under different operational and traffic-control configurations. Specifically, it measures order throughput, average order completion time, AGV travel distance, waiting times, battery recharging behavior, aisle direction lock contention, reroutings, and deadlock resolution. It also compares two picking workflows:

- **Standard Mode (`INNOVATION = False`):** An AGV arrives at an ASRS node and waits sequentially as items are picked from the shelves.
- **Container Pre-Preparation Mode (`INNOVATION = True`):** As soon as an order enters the system, the relevant ASRS units begin picking items into temporary buffer containers in parallel with AGV travel, reducing transfer time at the node to a fixed 15-second handoff.

## System Description

### Layout & Topology
- **Structure:** 20 aisles arranged in a U-shaped, two-column snake layout (60 aisle nodes total, 3 nodes per aisle: entry, middle, and exit).
- **Special Nodes:** Depot (`Node 0`), Order Drop-off (`Node 61`), and Charging Station (`Node 62`).
- **Multi-Node Picking:** Items can be stored and picked at any of the 3 nodes within an aisle, with an ASRS unit registered to each active pickup node.

### Fleet, Routing & Traffic Control
- **Fleet & Battery Management:** Fleet & Battery Management: Configurable AGV fleet moving at a constant speed (2 m/s) with distance-based battery discharge, decentralized charging triggered below a low-battery threshold, and opportunistic charging after drop-off at Node 61 when at least 3 other AGVs are already idle at Node 0 (charging up to max charge or until only 2 or fewer AGVs remain waiting at Node 0).
- **Two-Way Navigation & Aisle Direction Locks:** Aisle and corridor connections between warehouse nodes (`1–60`) can be mirrored for two-way movement. Horizontal movement inside an aisle uses direction locks (`L->R` / `R->L`) so opposing AGVs do not enter a single-lane aisle head-on; AGVs wait for the direction to free up before entering, or reroute if they block another AGV.
- **Dynamic Congestion-Aware Routing:** AGVs replan their next hop using a congestion-weighted Dijkstra algorithm that accounts for active ASRS queues, en-route AGVs, and directional/bottleneck penalties.
- **Collision Avoidance & Deadlock Recovery:** Movement runs in `0.5s` micro-steps with bounding-box overlap checks (`AGV_SIZE + 4px`). When two AGVs stay mutually blocked past a timeout threshold, the AGV closer to the nearest aisle exit (or higher ID on ties/extended chains) reverses back to its starting node, releases its aisle lock, steps aside to an unobstructed neighbor—or ducks into the Drop-Off bay (`61`) when node `60` is gridlocked—and replans.
- **Side-Bay Queuing & FIFO Rerouting:** AGVs pull into side-bays when an ASRS node is occupied so vertical corridors remain clear. When a side-bay at an entry/exit node is already occupied and an AGV arrives from the corridor, it can reroute via the aisle's middle node to queue behind existing vehicles in FIFO order.
- **Diagnostics & Reporting:** `DeadlockMonitor` periodically flags any AGV stationary for extended periods and logs when it recovers, while `WarehouseStats` reports aisle lock wait counts/durations, entries after waiting, total and FIFO reroutings, and deadlocks cleared.

## Limitations & Assumptions

- **Simplified Kinematics:** AGVs travel at a constant speed without modeling acceleration, deceleration, or turning radii, and short side-bay/step-aside maneuvers use local interpolated steps.
- **Instant Special-Node Transfers:** Travel between the Drop-off (`61`), Depot (`0`), and Charger (`62`) is modeled as zero-distance instant movement.
- **Discretized Spatial Checks & Heuristic Deadlock Resolution:** Collision detection uses `0.5s` micro-steps and deadlock recovery relies on local step-aside/rerouting rules rather than global centralized path reservation, so heavy fleet density can still produce temporary queues or multi-AGV congestion chains before recovery triggers.
- **Fallback Data:** If `warehouse_items.csv` is not present in the working directory, the script generates 1,000 synthetic items distributed across the 60 aisle nodes.

## How to Use

### 1. Prerequisites
Install Python 3.9+ and the required dependencies:

```bash
pip install salabim pandas numpy opencv-python
