# Automated Warehouse AGV & ASRS Simulation

A discrete-event simulation of an automated warehouse built with Python and `salabim`. The model simulates a fleet of Automated Guided Vehicles (AGVs) coordinating with Automated Storage and Retrieval Systems (ASRS) to fulfill customer orders, with live 2D animation and MP4 video export.

## Project Goal

The objective of this simulation is to evaluate warehouse performance under different operational and traffic-control configurations. Specifically, it measures order throughput, average order completion time, AGV travel distance, waiting times, and battery recharging behavior. It also compares two picking workflows:

- **Standard Mode (`INNOVATION = False`):** An AGV arrives at an ASRS node and waits sequentially as items are picked from the shelves.
- **Container Pre-Preparation Mode (`INNOVATION = True`):** As soon as an order enters the system, the relevant ASRS units begin picking items into temporary buffer containers in parallel with AGV travel, reducing transfer time at the node to a fixed 15-second handoff.

## System Description

### Layout & Topology
- **Structure:** 20 aisles arranged in a U-shaped, two-column snake layout (60 aisle nodes total, 3 nodes per aisle: entry, middle, and exit).
- **Special Nodes:** Depot (`Node 0`), Order Drop-off (`Node 61`), and Charging Station (`Node 62`).
- **Multi-Node Picking:** Items can be stored and picked at any of the 3 nodes within an aisle, with an ASRS unit registered to each active pickup node.

### Fleet, Routing & Traffic Control
- **Fleet & Battery Management:** Configurable AGV fleet (default: 20 AGVs) moving at a constant speed (`2 m/s`) with distance-based battery discharge and decentralized charging triggered below a 45% threshold.
- **Dynamic Congestion-Aware Routing:** AGVs replan their next hop at each node using a congestion-weighted Dijkstra algorithm. Intermediate ASRS nodes with active queues or en-route AGVs receive distance-equivalent penalties so pass-through traffic avoids busy aisles when alternative paths exist.
- **Collision Avoidance & Overtaking:** Movement is discretized into micro-steps (`0.5s`) with bounding-box overlap checks (`AGV_SIZE + 4px`) to prevent vehicles from overlapping or passing through each other on the same lane.
- **Side-Bay Queuing & Bypassing:** AGVs actively loading at an ASRS pull into the loading bay, and AGVs waiting at entry/exit nodes pull inward into the aisle. This keeps the vertical corridors clear so other AGVs can overtake and continue along their routes without unnecessary blocking.

## Limitations & Assumptions

- **One-Way Snake Constraints:** In a strict one-way snake graph, dynamic routing can only detour where alternative edges exist in `adjacency.csv` (such as vertical corridors or cross-column links). AGVs targeting even-numbered aisles still must traverse the preceding feeder aisle unless outer corridors or two-way aisle rules are added.
- **Simplified Kinematics:** AGVs travel at a constant speed without modeling acceleration, deceleration, or turning radii.
- **Instant Special-Node Transfers:** Travel between the Drop-off (`61`), Depot (`0`), and Charger (`62`) is modeled as zero-distance instant movement.
- **Discretized Spatial Checks:** Collision avoidance relies on fixed `0.5s` micro-steps, which balances visual accuracy against runtime speed for long headless runs.
- **Fallback Data:** If `warehouse_items.csv` is not present in the working directory, the script generates 1,000 synthetic items distributed across the 60 aisle nodes.

## How to Use

### 1. Prerequisites
Install Python 3.9+ and the required dependencies:

```bash
pip install salabim pandas numpy opencv-python
