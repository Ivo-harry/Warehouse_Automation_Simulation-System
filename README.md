# Automated Warehouse AGV & ASRS Simulation

A discrete-event simulation of an automated warehouse built with Python and `salabim`. The model simulates a fleet of Automated Guided Vehicles (AGVs) coordinating with Automated Storage and Retrieval Systems (ASRS) to fulfill customer orders, complete with live 2D animation, traffic and deadlock logging, and MP4 video export.

## What This Project Does

In a modern warehouse, orders require collecting items from different storage locations and bringing them to a drop-off point without vehicles blocking one another or waiting unnecessarily. This project builds a digital twin of that operation to test how routing rules, traffic controls, and order-preparation workflows affect speed and congestion.

Specifically, it evaluates two picking workflows:

- **Standard Mode (`INNOVATION = False`):** An AGV travels to each required ASRS pickup node and waits while items are retrieved sequentially.
- **Container Pre-Preparation Mode (`INNOVATION = True`):** As soon as an order arrives, the relevant ASRS units begin picking items into temporary buffer containers in parallel with AGV travel, turning node handoffs into a fixed 15-second transfer whenever items are already ready.

## Simulation Walkthrough Video

- **Animation Recording:**
- [[Watch the warehouse simulation (`media/warehouse_animation.mp4`)](media/warehouse_animation.mp4)](https://github.com/user-attachments/assets/05a7f8ed-ecd4-45b7-b339-8df41408c3c5)

*(Place your compressed file at `media/warehouse_animation.mp4` in the repository so visitors can view or download it directly from the README.)*

## System Description

### Layout & Topology
- **Structure:** 20 aisles arranged in a U-shaped, two-column snake layout (60 aisle nodes total, 3 nodes per aisle: entry, middle, and exit).
- **Special Nodes:** Depot (`Node 0`), Order Drop-off (`Node 61`), and Charging Station (`Node 62`).
- **Multi-Node Picking:** Items can be stored and picked at any of the 3 nodes within an aisle, with an ASRS unit registered to each active pickup node.

### Fleet, Routing & Traffic Control
- **Fleet & Battery Management:** Configurable AGV fleet moving at a constant speed (`2 m/s`) with distance-based battery discharge, decentralized charging triggered below a low-battery threshold, and opportunistic charging after drop-off at `Node 61` when at least 3 other AGVs are already idle at `Node 0` (charging up to max charge or until only 2 or fewer AGVs remain waiting at `Node 0`).
- **Two-Way Navigation & Aisle Direction Locks:** Aisle and corridor connections between warehouse nodes (`1–60`) can be mirrored for two-way movement. Horizontal movement inside an aisle uses direction locks (`L->R` / `R->L`) so opposing AGVs do not enter a single-lane aisle head-on; AGVs wait for the direction to free up before entering, or reroute if they block another AGV.
- **Dynamic Congestion-Aware Routing:** AGVs replan their next hop using a congestion-weighted Dijkstra algorithm that accounts for active ASRS queues, en-route AGVs, and directional/bottleneck penalties.
- **Collision Avoidance & Deadlock Recovery:** Movement runs in `0.5s` micro-steps with bounding-box overlap checks (`AGV_SIZE + 4px`). When two AGVs stay mutually blocked past a timeout threshold, the AGV closer to the nearest aisle exit (or higher ID on ties/extended chains) reverses back to its starting node, releases its aisle lock, steps aside to an unobstructed neighbor—or ducks into the Drop-Off bay (`61`) when node `60` is gridlocked—and replans.
- **Side-Bay Queuing & FIFO Rerouting:** AGVs pull into side-bays when an ASRS node is occupied so vertical corridors remain clear. When a side-bay at an entry/exit node is already occupied and an AGV arrives from the corridor, it can reroute via the aisle's middle node to queue behind existing vehicles in FIFO order.
- **Diagnostics & Reporting:** `DeadlockMonitor` periodically flags any AGV stationary for extended periods and logs when it recovers, while `WarehouseStats` reports throughput, order completion times, battery usage, aisle lock wait counts/durations, entries after waiting, total and FIFO reroutings, and deadlocks cleared.

## What I Learned

- **Local rules vs. system-wide traffic:** Allowing two-way movement and dynamic rerouting improves flexibility, yet high vehicle density can still create queue chains or funnel bottlenecks (such as around drop-off access) if lock release and escape rules are not carefully bounded.
- **Arrival rate shapes bottlenecks:** Testing different order arrival intervals showed how quickly a system shifts from demand-limited (low backlog, fast completion times) to capacity-limited (growing queues and longer lead times).
- **Order preparation changes where time is spent:** Pre-preparing items reduces waiting at pickup stations, shifting attention toward vehicle routing, aisle contention, and charging availability.
- **Verification and logging are essential in simulations:** Tracking specific events—such as aisle lock waits, reroutes, deadlocks cleared, and stationary AGVs—makes it possible to diagnose subtle edge cases instead of guessing from aggregate averages alone.

## Potential Improvements

- **Centralized or reservation-based traffic control:** Replace or supplement local step-aside and timeout rules with time-windowed or reservation-aware path planning to reduce multi-vehicle yield loops under heavy load.
- **More realistic vehicle and charging physics:** Model acceleration, deceleration, turning delays, and multi-charger queues at `Node 62` instead of instant transitions between special nodes.
- **Multi-seed and longer-horizon benchmarking:** Run batch experiments across multiple random seeds and longer time horizons (`INNOVATION = True` vs. `False`) with confidence intervals for stronger statistical comparison.
- **Dynamic order and fleet policies:** Test priority rules for orders, adaptive charging thresholds based on live demand, and sensitivity across different fleet sizes.

## Limitations & Assumptions

- **Simplified Kinematics:** AGVs travel at a constant speed without modeling acceleration, deceleration, or turning radii, and short side-bay/step-aside maneuvers use local interpolated steps.
- **Instant Special-Node Transfers:** Travel between the Drop-off (`61`), Depot (`0`), and Charger (`62`) is modeled as zero-distance instant movement.
- **Discretized Spatial Checks & Heuristic Deadlock Resolution:** Collision detection uses `0.5s` micro-steps and deadlock recovery relies on local step-aside/rerouting rules without global path reservation, so heavy fleet density can still produce temporary queues or congestion chains before recovery triggers.
- **Fallback Data:** If `warehouse_items.csv` is not present in the working directory, the script generates 1,000 synthetic items distributed across the 60 aisle nodes.

## How to Use

### 1. Prerequisites
Install Python 3.9+ and the required dependencies:

```bash
pip install salabim pandas numpy opencv-python
