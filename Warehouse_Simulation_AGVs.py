"""
COMMENTS FOR IMPORVEMENT/DEVELOPMNT



"""
import salabim as sim
import random
import csv
import numpy as np
import pandas as pd

# ===============================================================================
# GLOBAL PARAMETERS - Main settings that control the entire simulation
# ===============================================================================

INNOVATION = True                           # Switch between old method (False) and new container method (True)
AGV_SPEED = 2                               # How fast AGVs move in meters per second
MAX_CHARGE = 100                            # Full battery is 100%
CHARGE_THRESHOLD = 45                       # AGVs need charging when battery drops below 45%
CHARGE_RATE = 4.5 / 60                      # How fast batteries charge (4.5% per minute converted to per second)
SIM_DURATION = 24 * 60 * 60                 # How long simulation runs (24 hours in seconds)
CSV_FILE = 'warehouse_items.csv'            # File containing all warehouse items
#ADJACENCY_CSV = 'adjacency.csv'             # File showing which nodes connect to which nodes -> SNAKE PATTERN
ADJACENCY_CSV = 'adjacency_two_way.csv'     # File showing which nodes connect to which nodes -> ALLOWS FOR DOUBLE
AGV_NUMBR = 18                              # Set the number of AGVs
arrival_time_seconds = 24                   # 24 seconds between orders, means 3600 orders for the day
# arrival_time_seconds = 208.2              # 208.2 seconds between orders, means 415 orders per day
SEED = 31122002                             # My Birthday if you wonder from where it came 
random.seed(SEED)                           # For salabim distributions and Python random
np.random.seed(SEED)                        # For numpy-based selections

NODE_CONGESTION_PENALTY = 100.0             # meters-equivalent per AGV currently at a node
ASRS_QUEUE_PENALTY = 120.0                  # extra meters-equivalent per AGV queued at an ASRS

# ===============================================================================
# ANIMATION SETTINGS - Controls how the warehouse looks on screen
# ===============================================================================

class AnimationConfig:
    # Window size
    WINDOW_WIDTH = 1600
    WINDOW_HEIGHT = 950

    # Layout measurements
    AISLE_WIDTH = 400               # How wide each aisle appears
    AISLE_HEIGHT = 30               # How tall each aisle appears
    NODE_RADIUS = 12                # Size of dots representing locations
    AGV_SIZE = 15                   # Size of AGV squares
    FONT_SIZE = 10                  # Text size
    AGV_TRAVEL_OFFSET = 25          # How far below aisles AGVs travel

    # Where things are positioned
    LEFT_COLUMN_X = 250             # X position of left aisles
    RIGHT_COLUMN_X = 800            # X position of right aisles
    AISLE_SPACING_Y = 55            # Vertical space between aisles
    TOP_MARGIN = 80                 # Space from top of screen

    # Colors for different things
    AISLE_COLOR = "lightgray"
    NODE_COLOR = "lightblue"
    DEPOT_COLOR = "orange"          # Where AGVs start
    DROPOFF_COLOR = "orange"        # Where AGVs deliver orders
    CHARGER_COLOR = "darkgreen"     # Charging station
    ASRS_ACTIVE_COLOR = "firebrick" # ASRS when working
    ASRS_IDLE_COLOR = "orange"      # ASRS when not working
    TEXT_COLOR = "black"

    # AGV colors based on what they're doing
    AGV_IDLE = "green"              # AGV waiting for work
    AGV_MOVING = "orange"           # AGV traveling
    AGV_PICKING = "red"             # AGV getting items
    AGV_QUEUED = "orange"           # AGV waiting in line
    AGV_CHARGING = "blue"           # AGV charging battery

    # Container colors
    CONTAINER_READY = "green"       # Container has items ready
    CONTAINER_EMPTY = "orange"      # Container is empty

# ===============================================================================
# WAREHOUSE LAYOUT SETTINGS - Physical warehouse structure
# ===============================================================================

NUM_AISLES = 20                     # Total number of aisles in warehouse
AISLE_LENGTH = 50                   # How long each aisle is in meters
ENERGY_PER_METER = 0.042            # How much battery AGVs use per meter traveled

# Special locations in warehouse
DEPOT_NODE = 0                      # Where AGVs start and return to
DROP_OFF_NODE = 61                  # Where AGVs deliver completed orders
CHARGER_NODE = 62                   # Where AGVs go to charge batteries

# ===============================================================================
# WAREHOUSE SYSTEM - Main brain that coordinates everything
# ===============================================================================

class WarehouseSystem:
    """Main coordinator for order states, ASRS units, AGVs, dispatcher, and aisle locks."""
    def __init__(self):
        self.order_states = {}
        self.asrs_dict = {}
        self.agv_list = []
        self.dispatcher = None
        # Direction locks per aisle to prevent head-on deadlocks in narrow 2-way aisles
        self.aisle_locks = {
            aisle: {'dir': None, 'count': 0}
            for aisle in range(1, NUM_AISLES + 1)
        }

    def register_asrs(self, node, asrs):
        self.asrs_dict[node] = asrs

    def register_agv(self, agv):
        self.agv_list.append(agv)

    def register_dispatcher(self, dispatcher):
        self.dispatcher = dispatcher

    def can_enter_aisle(self, aisle_num, direction):
        lock = self.aisle_locks[aisle_num]
        return lock['count'] == 0 or lock['dir'] == direction

    def enter_aisle(self, aisle_num, direction):
        lock = self.aisle_locks[aisle_num]
        if lock['count'] == 0:
            lock['dir'] = direction
        lock['count'] += 1

    def leave_aisle(self, aisle_num):
        lock = self.aisle_locks[aisle_num]
        lock['count'] = max(0, lock['count'] - 1)
        if lock['count'] == 0:
            lock['dir'] = None

    def can_start_preparation(self, order_id, node):
        if order_id not in self.order_states:
            self.order_states[order_id] = {}
        current_state = self.order_states[order_id].get(node, 'not_started')
        return current_state == 'not_started'

    def set_order_state(self, order_id, node, state):
        if order_id not in self.order_states:
            self.order_states[order_id] = {}
        self.order_states[order_id][node] = state
        SimLogger.log(f"Order state changed to '{state}' at node {node}",
                      order_id=order_id, component_type="WarehouseSystem")

    def get_order_state(self, order_id, node):
        return self.order_states.get(order_id, {}).get(node, 'not_started')

    def cleanup_completed_order(self, order_id):
        if order_id in self.order_states:
            del self.order_states[order_id]

warehouse_system = WarehouseSystem()

# ===============================================================================
# COORDINATE SYSTEM - Converts node numbers to screen positions
# ===============================================================================

def get_node_coordinates(node_number):
    """Convert a node number to x,y coordinates on screen."""
    if node_number == DEPOT_NODE:
        return (AnimationConfig.RIGHT_COLUMN_X - AnimationConfig.AISLE_WIDTH // 2, 30)
    elif node_number == DROP_OFF_NODE:
        return (AnimationConfig.LEFT_COLUMN_X + AnimationConfig.AISLE_WIDTH // 2, 30)
    elif node_number == CHARGER_NODE:
        return ((AnimationConfig.RIGHT_COLUMN_X - AnimationConfig.AISLE_WIDTH // 2 +
                 AnimationConfig.LEFT_COLUMN_X + AnimationConfig.AISLE_WIDTH // 2) // 2, 30)
    else:
        aisle_num = ((node_number - 1) // 3) + 1
        position_in_aisle = (node_number - 1) % 3  # 0=entry, 1=middle, 2=exit

        if aisle_num <= NUM_AISLES // 2:  # Right column (aisles 1-10)
            base_x = AnimationConfig.RIGHT_COLUMN_X
            base_y = AnimationConfig.TOP_MARGIN + (aisle_num - 1) * AnimationConfig.AISLE_SPACING_Y
        else:  # Left column (aisles 11-20)
            base_x = AnimationConfig.LEFT_COLUMN_X
            base_y = AnimationConfig.TOP_MARGIN + (NUM_AISLES - aisle_num) * AnimationConfig.AISLE_SPACING_Y

        if aisle_num <= NUM_AISLES // 2:
            if aisle_num % 2 == 1:  # Odd aisles (1, 3, 5, 7, 9): LEFT TO RIGHT
                if position_in_aisle == 0:
                    return (base_x - AnimationConfig.AISLE_WIDTH // 2, base_y)
                elif position_in_aisle == 1:
                    return (base_x, base_y)
                else:
                    return (base_x + AnimationConfig.AISLE_WIDTH // 2, base_y)
            else:  # Even aisles (2, 4, 6, 8, 10): RIGHT TO LEFT
                if position_in_aisle == 0:
                    return (base_x + AnimationConfig.AISLE_WIDTH // 2, base_y)
                elif position_in_aisle == 1:
                    return (base_x, base_y)
                else:
                    return (base_x - AnimationConfig.AISLE_WIDTH // 2, base_y)
        else:
            if aisle_num % 2 == 1:  # Odd aisles (11, 13, 15, 17, 19): RIGHT TO LEFT
                if position_in_aisle == 0:
                    return (base_x + AnimationConfig.AISLE_WIDTH // 2, base_y)
                elif position_in_aisle == 1:
                    return (base_x, base_y)
                else:
                    return (base_x - AnimationConfig.AISLE_WIDTH // 2, base_y)
            else:  # Even aisles (12, 14, 16, 18, 20): LEFT TO RIGHT
                if position_in_aisle == 0:
                    return (base_x - AnimationConfig.AISLE_WIDTH // 2, base_y)
                elif position_in_aisle == 1:
                    return (base_x, base_y)
                else:
                    return (base_x + AnimationConfig.AISLE_WIDTH // 2, base_y)

def get_aisle_and_direction(from_node, to_node):
    """Return (aisle_num, direction) if moving horizontally within the same aisle, else (None, None)."""
    if not (1 <= from_node <= 60 and 1 <= to_node <= 60):
        return None, None
    aisle_from = ((from_node - 1) // 3) + 1
    aisle_to = ((to_node - 1) // 3) + 1
    if aisle_from != aisle_to:
        return None, None
    x1, _ = get_node_coordinates(from_node)
    x2, _ = get_node_coordinates(to_node)
    if x2 == x1:
        return None, None
    return aisle_from, ('L->R' if x2 > x1 else 'R->L')

def get_asrs_queue_position(node_number, queue_index=0):
    """Return (x, y) pulled inside the aisle so queued AGVs don't block the vertical corridor."""
    node_x, node_y = get_node_coordinates(node_number)
    lane_y = node_y - AnimationConfig.AGV_TRAVEL_OFFSET

    if not (1 <= node_number <= 60):
        return (node_x, node_y)

    aisle_num = ((node_number - 1) // 3) + 1
    base_x = (
        AnimationConfig.RIGHT_COLUMN_X
        if aisle_num <= NUM_AISLES // 2
        else AnimationConfig.LEFT_COLUMN_X
    )

    pull_in_offset = 25  # > box_gap (19px) so vertical corridor traffic can pass freely
    slot_spacing = AnimationConfig.AGV_SIZE + 4

    if node_x < base_x:
        wait_x = node_x + pull_in_offset + queue_index * slot_spacing
    elif node_x > base_x:
        wait_x = node_x - pull_in_offset - queue_index * slot_spacing
    else:
        wait_x = node_x

    return (wait_x, lane_y)

def get_asrs_color(node_number):
    """Return color based on whether ASRS is working or not"""
    asrs = warehouse_system.asrs_dict.get(node_number)
    if asrs and asrs.is_active:
        return AnimationConfig.ASRS_ACTIVE_COLOR
    else:
        return AnimationConfig.ASRS_IDLE_COLOR

# ===============================================================================
# ANIMATION HELPER FUNCTIONS - Create visual elements on screen
# ===============================================================================

def create_node_animation(node_number, node_type="normal"):
    """Create a visual dot and label for a location in the warehouse"""
    x, y = get_node_coordinates(node_number)

    if node_type == "asrs":
        color = lambda t: get_asrs_color(node_number)
        radius = AnimationConfig.NODE_RADIUS
        line_color = "maroon"
    elif node_type == "depot":
        color = AnimationConfig.DEPOT_COLOR
        radius = AnimationConfig.NODE_RADIUS + 3
        line_color = "maroon"
    elif node_type == "dropoff":
        color = AnimationConfig.DROPOFF_COLOR
        radius = AnimationConfig.NODE_RADIUS + 3
        line_color = "maroon"
    elif node_type == "charger":
        color = AnimationConfig.CHARGER_COLOR
        radius = AnimationConfig.NODE_RADIUS + 3
        line_color = "limegreen"
    else:
        color = AnimationConfig.NODE_COLOR
        radius = AnimationConfig.NODE_RADIUS
        line_color = "darkblue"

    sim.AnimateCircle(
        radius=radius,
        x=x, y=y,
        fillcolor=color,
        linecolor=line_color,
        linewidth=2
    )

    text_color = "white" if node_type == "charger" else AnimationConfig.TEXT_COLOR
    sim.AnimateText(
        text=str(node_number if node_number != CHARGER_NODE else "62"),
        x=x, y=y,
        fontsize=12,
        textcolor=text_color,
        text_anchor="c"
    )

def create_aisle_animation(aisle_num):
    """Create visual representation of one complete aisle with its 3 nodes"""
    if aisle_num <= NUM_AISLES // 2:
        x = AnimationConfig.RIGHT_COLUMN_X
        y = AnimationConfig.TOP_MARGIN + (aisle_num - 1) * AnimationConfig.AISLE_SPACING_Y
    else:
        x = AnimationConfig.LEFT_COLUMN_X
        y = AnimationConfig.TOP_MARGIN + (NUM_AISLES - aisle_num) * AnimationConfig.AISLE_SPACING_Y

    sim.AnimateRectangle(
        spec=(x - AnimationConfig.AISLE_WIDTH // 2, y - AnimationConfig.AISLE_HEIGHT // 2,
              x + AnimationConfig.AISLE_WIDTH // 2, y + AnimationConfig.AISLE_HEIGHT // 2),
        fillcolor=AnimationConfig.AISLE_COLOR,
        linecolor="black",
        linewidth=2
    )

    entry_node = (aisle_num - 1) * 3 + 1
    middle_node = (aisle_num - 1) * 3 + 2
    exit_node = (aisle_num - 1) * 3 + 3

    create_node_animation(entry_node, "asrs")
    create_node_animation(middle_node, "asrs")
    create_node_animation(exit_node, "asrs")

def setup_animation():
    """Create all the visual elements for the warehouse"""
    for aisle_num in range(1, NUM_AISLES + 1):
        create_aisle_animation(aisle_num)

    create_node_animation(DEPOT_NODE, "depot")
    create_node_animation(DROP_OFF_NODE, "dropoff")
    create_node_animation(CHARGER_NODE, "charger")

# ===============================================================================
# PATH FINDING SYSTEM - Loads warehouse layout and finds shortest routes
# ===============================================================================

def distance_to_nearest_aisle_exit(agv):
    """Return horizontal pixel distance from the AGV to the closest vertical corridor (aisle exit)."""
    left_col_left = AnimationConfig.LEFT_COLUMN_X - AnimationConfig.AISLE_WIDTH // 2
    left_col_right = AnimationConfig.LEFT_COLUMN_X + AnimationConfig.AISLE_WIDTH // 2
    right_col_left = AnimationConfig.RIGHT_COLUMN_X - AnimationConfig.AISLE_WIDTH // 2
    right_col_right = AnimationConfig.RIGHT_COLUMN_X + AnimationConfig.AISLE_WIDTH // 2

    exits_x = (left_col_left, left_col_right, right_col_left, right_col_right)
    return min(abs(agv.cur_x - ex) for ex in exits_x)

def get_aisle_middle_node(node_number):
    """Return the middle node of the aisle if node_number is an entry/exit node, else None."""
    if not (1 <= node_number <= 60):
        return None
    aisle_num = ((node_number - 1) // 3) + 1
    middle_node = (aisle_num - 1) * 3 + 2
    return middle_node if node_number != middle_node else None

def load_adjacency_matrix():
    """Load the map of how locations connect to each other."""
    try:
        adj_df = pd.read_csv(ADJACENCY_CSV, index_col=0)
        adjacency_dict = {}

        for from_node in adj_df.index:
            from_node_int = int(from_node)
            adjacency_dict[from_node_int] = {}

            for to_node in adj_df.columns:
                to_node_int = int(to_node)
                if pd.notna(adj_df.loc[from_node, to_node]) and adj_df.loc[from_node, to_node] != 0:
                    distance_value = float(adj_df.loc[from_node, to_node])
                    adjacency_dict[from_node_int][to_node_int] = distance_value

        SimLogger.log(f"Loaded adjacency matrix with {len(adj_df)} nodes")
        return adjacency_dict
    except FileNotFoundError:
        SimLogger.log(f"Warning: {ADJACENCY_CSV} not found.")
        raise

def dijkstra_shortest_path(start, end, adjacency_dict):
    """Find the shortest path between two locations using Dijkstra's algorithm"""
    if start == end:
        return [start]

    distances = {node: float('inf') for node in adjacency_dict.keys()}
    distances[start] = 0
    previous = {}
    unvisited = set(adjacency_dict.keys())

    while unvisited:
        current = min(unvisited, key=lambda node: distances[node])
        if distances[current] == float('inf') or current == end:
            break
        unvisited.remove(current)

        for neighbor, weight in adjacency_dict.get(current, {}).items():
            if neighbor in unvisited:
                new_distance = distances[current] + weight
                if new_distance < distances[neighbor]:
                    distances[neighbor] = new_distance
                    previous[neighbor] = current

    if end not in previous and end != start:
        return []

    path = []
    current = end
    while current is not None:
        path.append(current)
        current = previous.get(current)

    path.reverse()
    return path

def calculate_distance_between_nodes(from_node, to_node, adjacency_dict):
    """Calculate distance between two connected locations"""
    try:
        special_nodes = {DEPOT_NODE, DROP_OFF_NODE, CHARGER_NODE}
        if from_node in special_nodes and to_node in special_nodes:
            return 0

        lookup_from = DEPOT_NODE if from_node == CHARGER_NODE else from_node
        lookup_to = DEPOT_NODE if to_node == CHARGER_NODE else to_node

        if lookup_from in adjacency_dict and lookup_to in adjacency_dict[lookup_from]:
            return adjacency_dict[lookup_from][lookup_to]
        else:
            return abs(lookup_from - lookup_to) * 10
    except:
        return abs(from_node - to_node) * 10

def get_node_congestion_penalty(node, target_node, requesting_agv, from_node=None):
    """Penalize busy ASRS aisles, stuck AGVs, and opposite-direction aisle locks."""
    if node == target_node or node in (DEPOT_NODE, DROP_OFF_NODE, CHARGER_NODE):
        return 0.0

    penalty = 0.0

    if node == 60 and target_node not in (60, DROP_OFF_NODE):
        penalty += 500.0

    is_asrs_node = node in warehouse_system.asrs_dict

    # Penalize entering an aisle locked in the opposite direction
    if from_node is not None:
        aisle_num, direction = get_aisle_and_direction(from_node, node)
        if aisle_num is not None and not warehouse_system.can_enter_aisle(aisle_num, direction):
            penalty += 300.0

    for other in warehouse_system.agv_list:
        if other is requesting_agv:
            continue

        if is_asrs_node:
            if other.current_node == node or other.next_node == node:
                penalty += NODE_CONGESTION_PENALTY
        else:
            if other.current_node == node and other.agv_status == "queued":
                penalty += 25.0

    if is_asrs_node:
        asrs = warehouse_system.asrs_dict[node]
        penalty += asrs.agv_queue.length() * ASRS_QUEUE_PENALTY
        if asrs.is_active:
            penalty += NODE_CONGESTION_PENALTY

    return penalty

def dijkstra_dynamic_shortest_path(
    start, end, adjacency_dict, requesting_agv, avoid_nodes=None, blocked_edge=None
):
    """Find the lowest-cost path using live congestion and direction-lock penalties."""
    if start == end:
        return [start]

    avoid_nodes = avoid_nodes or set()
    distances = {node: float('inf') for node in adjacency_dict.keys()}
    distances[start] = 0.0
    previous = {}
    unvisited = set(adjacency_dict.keys())

    while unvisited:
        current = min(unvisited, key=lambda node: distances[node])
        if distances[current] == float('inf') or current == end:
            break

        unvisited.remove(current)

        for neighbor, weight in adjacency_dict.get(current, {}).items():
            # Hard-skip the blocked edge (e.g., entering a busy side-bay from the front)
            if blocked_edge and (current, neighbor) == blocked_edge:
                continue

            if neighbor in unvisited:
                loop_penalty = 500.0 if neighbor in avoid_nodes else 0.0
                congestion_penalty = get_node_congestion_penalty(
                    neighbor, end, requesting_agv, from_node=current
                )
                new_distance = distances[current] + weight + congestion_penalty + loop_penalty

                if new_distance < distances[neighbor]:
                    distances[neighbor] = new_distance
                    previous[neighbor] = current

    if end not in previous and end != start:
        return []

    path = []
    current = end
    while current is not None:
        path.append(current)
        current = previous.get(current)

    path.reverse()
    return path

# ===============================================================================
# DATA LOADING SYSTEM - Loads warehouse items from files
# ===============================================================================

def load_warehouse_data():
    """Load list of all items in the warehouse from CSV file"""
    items = []
    try:
        with open(CSV_FILE, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                items.append({
                    'ItemID': row['ItemID'],
                    'ItemName': row['ItemName'],
                    'Category': row['Category'],
                    'Aisle': row['Aisle'],
                    'AisleLocation': int(row['AisleLocation'])
                })
        SimLogger.log(f"Loaded {len(items)} items from {CSV_FILE}")
        return items
    except FileNotFoundError:
        SimLogger.log(f"Warning: {CSV_FILE} not found. Using simulated data.")
        return generate_simulated_items()

def generate_simulated_items():
    """Create fake items across all 3 nodes of every aisle"""
    items = []
    for i in range(1000):
        aisle_num = random.randint(1, NUM_AISLES)
        position_in_aisle = random.choice([1, 2, 3])  # 1=entry, 2=middle, 3=exit
        aisle_location = (aisle_num - 1) * 3 + position_in_aisle
        items.append({
            'ItemID': f'ITEM_{i:04d}',
            'ItemName': f'Product_{i}',
            'Category': random.choice(['Electronics', 'Clothing', 'Books', 'Home']),
            'Aisle': f'Aisle-{aisle_num}',
            'AisleLocation': aisle_location
        })
    return items

# ===============================================================================
# ORDER GENERATOR - Creates new customer orders randomly (Precomputed for consistency)
# ===============================================================================

def generate_orders_ahead(seed, duration_seconds, items_pool):
    """Precompute all order arrival times and item selections"""
    random.seed(seed)
    np.random.seed(seed)

    inter_arrival_time_dist = sim.Exponential(arrival_time_seconds)
    items_per_order_dist = sim.Poisson(5)

    time = 0
    order_defs = []

    while time < duration_seconds:
        iat = inter_arrival_time_dist.sample()
        num_items = max(1, int(items_per_order_dist.sample()))
        item_indices = np.random.choice(len(items_pool), size=num_items, replace=False)
        selected_items = [items_pool[i] for i in item_indices]

        order_defs.append((time, selected_items))
        time += iat

    return order_defs

class OrderFeeder(sim.Component):
    """Feeds precomputed orders into the simulation at scheduled times"""
    def setup(self, order_definitions):
        self.order_definitions = order_definitions

    def process(self):
        for timestamp, items in self.order_definitions:
            wait_time = timestamp - env.now()
            if wait_time > 0:
                self.hold(wait_time)

            order = Order(items=items, timestamp=env.now())
            all_orders.append(order)
            env.stats.orders_created += 1

            if INNOVATION:
                order.trigger_container_preparation()

            order.enter(order_queue)
            dispatcher.activate()

# ===============================================================================
# ORDER CLASS - Represents a customer order
# ===============================================================================

class Order(sim.Component):
    order_counter = 0

    def setup(self, items, timestamp):
        Order.order_counter += 1
        self.order_id = Order.order_counter
        self.items = items
        self.timestamp = timestamp
        self.completion_time = None
        self.is_completed = False

        self.items_by_node = {}
        nodes_to_visit = set()

        for item in self.items:
            pickup_node = item['AisleLocation']
            nodes_to_visit.add(pickup_node)
            if pickup_node not in self.items_by_node:
                self.items_by_node[pickup_node] = []
            self.items_by_node[pickup_node].append(item)

        self.load_plan = self.calculate_complete_path_with_adjacency(list(nodes_to_visit))
        self.pickup_nodes = list(nodes_to_visit)
        self.num_items = len(items)

    def calculate_complete_path_with_adjacency(self, pickup_nodes):
        if not pickup_nodes:
            return [DEPOT_NODE, DROP_OFF_NODE]

        sorted_pickup_nodes = sorted(pickup_nodes)
        complete_path = [DEPOT_NODE]
        current_position = DEPOT_NODE

        for pickup_node in sorted_pickup_nodes:
            path_to_pickup = dijkstra_shortest_path(current_position, pickup_node, adjacency_matrix)
            if len(path_to_pickup) > 1:
                complete_path.extend(path_to_pickup[1:])
            elif len(complete_path) == 0:
                complete_path.extend(path_to_pickup)
            current_position = pickup_node

        path_to_dropoff = dijkstra_shortest_path(current_position, DROP_OFF_NODE, adjacency_matrix)
        if len(path_to_dropoff) > 1:
            complete_path.extend(path_to_dropoff[1:])

        return complete_path

    def trigger_container_preparation(self):
        node_details = []
        for node in self.pickup_nodes:
            items_at_node = self.items_by_node[node]
            item_names = [item['ItemName'] for item in items_at_node]
            node_details.append(f"{node}: {', '.join(item_names)}")

        SimLogger.log(f"Triggering item preparation for {len(self.pickup_nodes)} nodes: [{'], ['.join(node_details)}]",
                      order_id=self.order_id)

        for node in self.pickup_nodes:
            if not warehouse_system.can_start_preparation(self.order_id, node):
                SimLogger.log(f"Preparation already in progress for node {node}, skipping",
                              order_id=self.order_id, component_type="Order")
                continue

            warehouse_system.set_order_state(self.order_id, node, 'preparing')

            asrs = next((a for a in asrs_list if a.node_number == node), None)
            if asrs:
                request_data = {
                    'order_id': self.order_id,
                    'node_number': node,
                    'items_list': self.items_by_node[node],
                    'request_time': env.now(),
                    'num_items': len(self.items_by_node[node])
                }
                asrs.prep_process.preparation_queue.append(request_data)
                if asrs.prep_process.status() == sim.passive:
                    asrs.prep_process.activate()

    def process(self):
        self.passivate()

    def mark_completed(self):
        if not self.is_completed:
            self.completion_time = env.now()
            self.is_completed = True
            env.stats.orders_completed += 1
            order_time = self.completion_time - self.timestamp
            env.stats.total_order_time += order_time
            env.stats.order_times.append(order_time)
            warehouse_system.cleanup_completed_order(self.order_id)

# ===============================================================================
# DISPATCHER - Assigns orders to available AGVs
# ===============================================================================

class Dispatcher(sim.Component):
    def setup(self):
        self.order_queue = order_queue
        self.available_agvs = available_agvs

    def process(self):
        while True:
            if len(self.order_queue) > 0 and len(self.available_agvs) > 0:
                suitable_agv = self.available_agvs[0]
                order = self.order_queue.pop()
                self.available_agvs.remove(suitable_agv)
                SimLogger.log(f"Dispatching to AGV {suitable_agv.agv_id}",
                              order_id=order.order_id, component_type="Dispatcher")
                suitable_agv.assign_order(order)
            else:
                self.passivate()

# ===============================================================================
# ASRS CLASS - Automated Storage and Retrieval System
# ===============================================================================

class ASRS(sim.Component):
    def setup(self, node_number):
        self.node_number = node_number
        self.agv_queue = sim.Queue(f"ASRS_Node_{node_number}_Queue")
        self.pick_time = sim.Normal(60, 45)
        self.is_active = False
        self.current_picking_order = None
        self.current_picking_items = 0

        self.container = Container(node_number=self.node_number, asrs=self)
        self.prep_process = ASRSContainerInterface(node_number=self.node_number, asrs=self)
        self.prep_process.activate()

        self.animation_manager = ASRSAnimationManager(self)

    def hand_items_to_container(self, order_id, items_list, prep_time=None):
        self.container.receive_items_from_asrs(order_id, items_list, prep_time)

    def process(self):
        while True:
            if self.agv_queue.length() > 0:
                agv = self.agv_queue.pop()
                agv.agv_status = "picking_up"

                asrs_x, asrs_y = get_node_coordinates(self.node_number)
                agv.cur_x, agv.cur_y = asrs_x, asrs_y
                agv.animation_object.x = asrs_x
                agv.animation_object.y = asrs_y

                SimLogger.log(f"AGV {agv.agv_id} moved to ASRS position for pickup",
                              component_type="ASRS Node", component_id=self.node_number)

                order = agv.current_order

                if order and self.node_number in order.items_by_node:
                    if INNOVATION:
                        current_state = warehouse_system.get_order_state(order.order_id, self.node_number)

                        if current_state == 'ready':
                            self.container.request_transfer_to_agv(agv, order.order_id)
                            self.passivate()
                            env.stats.container_ready_transfers += 1
                        elif current_state == 'preparing':
                            SimLogger.log(f"AGV {agv.agv_id} waiting for ongoing preparation",
                                          order_id=order.order_id, component_type="ASRS Node",
                                          component_id=self.node_number)
                            while warehouse_system.get_order_state(order.order_id, self.node_number) != 'ready':
                                self.hold(1)
                            self.container.request_transfer_to_agv(agv, order.order_id)
                            self.passivate()
                            env.stats.container_wait_transfers += 1
                        else:
                            if warehouse_system.can_start_preparation(order.order_id, self.node_number):
                                self.is_active = True
                                items_at_node = len(order.items_by_node[self.node_number])
                                self.current_picking_order = order.order_id
                                self.current_picking_items = items_at_node

                                warehouse_system.set_order_state(order.order_id, self.node_number, 'preparing')

                                SimLogger.log(f"Container not ready, AGV {agv.agv_id} waiting for new preparation",
                                              order_id=order.order_id, component_type="ASRS Node",
                                              component_id=self.node_number)

                                for i, item in enumerate(order.items_by_node[self.node_number]):
                                    item_prep_time = max(0, self.pick_time.sample())
                                    SimLogger.log(
                                        f"picking item {i + 1}/{items_at_node}: {item['ItemName']} (took {item_prep_time:.1f}s)",
                                        order_id=order.order_id, component_type="ASRS Node",
                                        component_id=self.node_number)
                                    self.hold(item_prep_time)

                                self.hand_items_to_container(order.order_id, order.items_by_node[self.node_number])
                                warehouse_system.set_order_state(order.order_id, self.node_number, 'ready')
                                self.container.request_transfer_to_agv(agv, order.order_id)
                                self.passivate()
                                env.stats.container_wait_transfers += 1
                            else:
                                while warehouse_system.get_order_state(order.order_id, self.node_number) != 'ready':
                                    self.hold(1)
                                self.container.request_transfer_to_agv(agv, order.order_id)
                                self.passivate()
                    else:
                        self.is_active = True
                        items_at_node = order.items_by_node[self.node_number]
                        self.current_picking_order = order.order_id
                        self.current_picking_items = len(items_at_node)

                        SimLogger.log(
                            f"AGV {agv.agv_id} waiting for sequential preparation of {len(items_at_node)} items",
                            order_id=order.order_id, component_type="ASRS Node", component_id=self.node_number)

                        total_prep_time = 0
                        for i, item in enumerate(items_at_node):
                            item_prep_time = max(0, self.pick_time.sample())
                            total_prep_time += item_prep_time
                            SimLogger.log(
                                f"picking item {i + 1}/{len(items_at_node)}: {item['ItemName']})",
                                order_id=order.order_id, component_type="ASRS Node", component_id=self.node_number)
                            self.hold(item_prep_time)

                        SimLogger.log(
                            f"completed sequential preparation of {len(items_at_node)} items (total picking took {total_prep_time:.1f}s)",
                            order_id=order.order_id, component_type="ASRS Node", component_id=self.node_number)

                        self.current_picking_order = None
                        self.current_picking_items = 0
                        self.is_active = False

                        env.stats.sequential_transfers += 1
                        agv.loading_complete()

                SimLogger.log(f"AGV {agv.agv_id} moved back to travel position",
                              component_type="ASRS Node", component_id=self.node_number)
            else:
                self.passivate()

    def enqueue_agv(self, agv):
        agv.enter(self.agv_queue)
        self.activate()

# ===============================================================================
# CONTAINER CLASS - Stores items temporarily (new method only)
# ===============================================================================

class Container(sim.Component):
    def setup(self, node_number, asrs):
        self.node_number = node_number
        self.asrs = asrs
        self.items_ready = {}
        self.transfer_queue = []

    def receive_items_from_asrs(self, order_id, items_list, prep_time=None):
        if order_id not in self.items_ready:
            self.items_ready[order_id] = []
        self.items_ready[order_id].extend(items_list)

        item_names = [item['ItemName'] for item in items_list]
        items_detail = ', '.join(item_names)

        if prep_time is not None:
            SimLogger.log(
                f"received {len(items_list)} item(s) from ASRS - Items: [{items_detail}] (took {prep_time:.1f}s)",
                order_id=order_id, component_type="Container", component_id=self.node_number)
        else:
            SimLogger.log(f"received {len(items_list)} item(s) from ASRS - Items: [{items_detail}]",
                          order_id=order_id, component_type="Container", component_id=self.node_number)

    def request_transfer_to_agv(self, agv, order_id):
        self.transfer_queue.append((agv, order_id))
        self.activate()

    def process(self):
        while True:
            if self.transfer_queue:
                agv, order_id = self.transfer_queue.pop(0)

                if order_id in self.items_ready:
                    items_list = self.items_ready[order_id]
                    item_names = [item['ItemName'] for item in items_list]
                    items_detail = ', '.join(item_names)

                    self.hold(15)

                    SimLogger.log(f"dropped items to AGV {agv.agv_id} - Items: [{items_detail}]",
                                  order_id=order_id, component_type="Container", component_id=self.node_number)

                    del self.items_ready[order_id]
                    warehouse_system.set_order_state(order_id, self.node_number, 'transferred')

                    agv.loading_complete()
                    self.asrs.activate()
                else:
                    agv.loading_complete()
                    self.asrs.activate()
            else:
                self.passivate()

    def has_items_for_order(self, order_id):
        return order_id in self.items_ready

    def has_items(self):
        return len(self.items_ready) > 0

# ===============================================================================
# ASRS CONTAINER INTERFACE - Handles item preparation (new method only)
# ===============================================================================

class ASRSContainerInterface(sim.Component):
    def setup(self, node_number, asrs):
        self.node_number = node_number
        self.asrs = asrs
        self.preparation_queue = []

    def process(self):
        while True:
            while len(self.preparation_queue) == 0:
                self.passivate()

            prep_request = self.preparation_queue.pop(0)
            self.asrs.is_active = True
            self.asrs.current_picking_order = prep_request['order_id']
            self.asrs.current_picking_items = prep_request['num_items']

            current_state = warehouse_system.get_order_state(prep_request['order_id'], self.node_number)
            if current_state != 'preparing':
                SimLogger.log(f"Skipping preparation - state changed to {current_state}",
                              order_id=prep_request['order_id'], component_type="ASRS Node",
                              component_id=self.node_number)
                self.asrs.current_picking_order = None
                self.asrs.current_picking_items = 0
                self.asrs.is_active = False
                continue

            item_names = [item['ItemName'] for item in prep_request['items_list']]
            items_detail = ', '.join(item_names)

            SimLogger.log(f"starting item preparation - Items: [{items_detail}]",
                          order_id=prep_request['order_id'], component_type="ASRS Node", component_id=self.node_number)

            items_list = prep_request['items_list']
            total_prep_time = 0

            for i, item in enumerate(items_list):
                item_prep_time = max(0, self.asrs.pick_time.sample())
                total_prep_time += item_prep_time

                SimLogger.log(f"picking item {i + 1}/{len(items_list)}: {item['ItemName']}",
                              order_id=prep_request['order_id'], component_type="ASRS Node",
                              component_id=self.node_number)

                self.hold(item_prep_time)
                self.asrs.hand_items_to_container(prep_request['order_id'], [item], item_prep_time)

            warehouse_system.set_order_state(prep_request['order_id'], self.node_number, 'ready')

            self.asrs.current_picking_order = None
            self.asrs.current_picking_items = 0
            self.asrs.is_active = False

            SimLogger.log(f"completed preparation of {len(items_list)} items (total prep took {total_prep_time:.1f}s)",
                          order_id=prep_request['order_id'], component_type="ASRS Node", component_id=self.node_number)

# ===============================================================================
# AGV CLASS - Automated Guided Vehicle
# ===============================================================================

class AGV(sim.Component):
    def setup(self, agv_id):
        self.agv_id = agv_id
        self.battery = MAX_CHARGE
        self.current_order = None
        self.next_node = None
        self.current_node = DEPOT_NODE
        self.total_distance = 0.0
        self.total_waiting_time = 0.0
        self.recharge_count = 0
        self.path_to_follow = []
        self.current_path_index = 0
        self.is_available = True
        self.agv_status = "idle"
        self.items_picked_up = 0
        self.total_items_in_order = 0

        depot_x, depot_y = get_node_coordinates(DEPOT_NODE)
        self.cur_x = depot_x
        self.cur_y = depot_y

        self.animation_manager = AGVAnimationManager(self)

    def assign_order(self, order):
        self.current_order = order
        self.path_to_follow = order.load_plan.copy()
        self.current_path_index = 0
        self.is_available = False
        self.agv_status = "moving"
        self.items_picked_up = 0
        self.total_items_in_order = order.num_items
        self.activate()

    def is_path_blocked(self, next_x, next_y):
        """Return the blocking AGV ahead if (next_x, next_y) overlaps it, else None."""
        box_gap = AnimationConfig.AGV_SIZE + 4  # 15px AGV + 4px safety margin
        special_nodes = (DEPOT_NODE, DROP_OFF_NODE, CHARGER_NODE)

        for other in warehouse_system.agv_list:
            if other is self:
                continue
            if other.current_node in special_nodes or other.agv_status == "picking_up":
                continue

            ox, oy = other.cur_x, other.cur_y

            if abs(next_x - ox) < box_gap and abs(next_y - oy) < box_gap:
                curr_dist_sq = (self.cur_x - ox) ** 2 + (self.cur_y - oy) ** 2
                next_dist_sq = (next_x - ox) ** 2 + (next_y - oy) ** 2
                if next_dist_sq < curr_dist_sq:
                    return other
        return None

    def _count_waiting_at_depot(self):
        """Count other AGVs currently idle/waiting for orders at the depot."""
        return sum(
            1
            for other in warehouse_system.agv_list
            if other is not self
            and other.agv_status == "idle"
            and other.current_node == DEPOT_NODE
        )

    def _opportunistic_charge_after_dropoff(self, opportunistic_threshold=3, min_waiting_to_keep_charging=2):
        """Charge opportunistically after drop-off when >= threshold AGVs are already waiting at node 0."""
        if self.battery >= MAX_CHARGE or self._count_waiting_at_depot() < opportunistic_threshold:
            return False

        SimLogger.log(
            f"opportunistic charging at node {CHARGER_NODE} (battery={self.battery:.1f}%, waiting at depot={self._count_waiting_at_depot()})",
            component_type="AGV",
            component_id=self.agv_id,
        )
        self.agv_status = "charging"
        self.current_node = CHARGER_NODE
        cx, cy = get_node_coordinates(CHARGER_NODE)
        self.cur_x, self.cur_y = cx, cy
        self.animation_object.x = cx
        self.animation_object.y = cy

        self.recharge_count += 1
        env.stats.total_recharges += 1

        step_dt = 1.0
        while self.battery < MAX_CHARGE and self._count_waiting_at_depot() > min_waiting_to_keep_charging:
            self.hold(step_dt)
            self.battery = min(MAX_CHARGE, self.battery + CHARGE_RATE * step_dt)

        SimLogger.log(
            f"finished opportunistic charging (battery={self.battery:.1f}%, waiting at depot={self._count_waiting_at_depot()})",
            component_type="AGV",
            component_id=self.agv_id,
        )
        return True

    def process(self):
        """Main AGV operation loop with dynamic congestion-aware routing, deadlock recovery, and side-bay queuing"""
        while True:
            if self.current_order is None:
                if not self.is_available:
                    self.is_available = True
                    self.agv_status = "idle"
                    available_agvs.append(self)
                    dispatcher.activate()
                self.passivate()
            else:
                if self.current_node != DEPOT_NODE:
                    self.return_to_depot()

                pickup_nodes = set(self.current_order.pickup_nodes)
                targets = sorted(self.current_order.pickup_nodes) + [DROP_OFF_NODE]

                SimLogger.log(
                    f"starting order with dynamic routing to targets: {targets}",
                    order_id=self.current_order.order_id,
                    component_type="AGV",
                    component_id=self.agv_id,
                )

                for target in targets:
                    visited_on_leg = {self.current_node}
                    temp_avoid = set()
                    prev_node = self.current_node

                    while self.current_node != target:
                        dynamic_path = dijkstra_dynamic_shortest_path(
                            self.current_node,
                            target,
                            adjacency_matrix,
                            self,
                            avoid_nodes=visited_on_leg | temp_avoid,
                        )

                        if len(dynamic_path) < 2:
                            if temp_avoid:
                                temp_avoid.clear()
                                self.hold(1.0)
                                continue
                            break

                        next_node = dynamic_path[1]
                        self.agv_status = "moving"
                        origin = self.current_node
                        reached = self.travel_to_node_with_animation(next_node)

                        if reached:
                            prev_node = origin
                            visited_on_leg.add(next_node)
                            temp_avoid.discard(next_node)
                        else:
                            stepped = self.step_aside_from_aisle(next_node)
                            if stepped:
                                visited_on_leg = {self.current_node}
                                temp_avoid.add(next_node)
                            else:
                                temp_avoid.add(next_node)

                    if target in pickup_nodes:
                        self.agv_status = "queued"
                        asrs = next((a for a in asrs_list if a.node_number == target), None)
                        if asrs:
                            wait_start = env.now()
                            middle_node = get_aisle_middle_node(target)

                            # Check if another AGV is already picking up or queued at this node
                            asrs_busy = (
                                asrs.agv_queue.length() > 0
                                or any(
                                    other is not self
                                    and other.current_node == target
                                    and other.agv_status == "picking_up"
                                    for other in warehouse_system.agv_list
                                )
                            )

                            if asrs_busy:
                                if middle_node is not None and asrs.agv_queue.length() > 0 and prev_node != middle_node:
                                    self.reroute_behind_queue(target, middle_node, asrs)
                                else:
                                    wait_x, wait_y = get_asrs_queue_position(target, queue_index=asrs.agv_queue.length())
                                    self.move_smoothly_to(wait_x, wait_y)

                            asrs.enqueue_agv(self)
                            self.passivate()
                            wait_time = env.now() - wait_start
                            self.total_waiting_time += wait_time

                self.current_order.mark_completed()
                SimLogger.log(
                    "completed order",
                    order_id=self.current_order.order_id,
                    component_type="AGV",
                    component_id=self.agv_id,
                )

                self.current_order = None
                self.path_to_follow = []
                self.current_path_index = 0
                self.items_picked_up = 0
                self.total_items_in_order = 0

                if self.battery < CHARGE_THRESHOLD:
                    SimLogger.log(
                        f"battery low ({self.battery:.1f}%), going to charge after completing order",
                        component_type="AGV",
                        component_id=self.agv_id,
                    )
                    self.go_to_charger()
                elif self.current_node == DROP_OFF_NODE and self._opportunistic_charge_after_dropoff():
                    self.current_node = DEPOT_NODE
                    depot_x, depot_y = get_node_coordinates(DEPOT_NODE)
                    self.cur_x, self.cur_y = depot_x, depot_y
                    self.animation_object.x = depot_x
                    self.animation_object.y = depot_y
                    SimLogger.log(
                        "arrived at depot",
                        component_type="AGV",
                        component_id=self.agv_id,
                    )
                else:
                    self.return_to_depot()

                self.agv_status = "idle"

    def return_to_depot(self):
        if self.current_node == DEPOT_NODE:
            return

        SimLogger.log(f"returning to depot from node {self.current_node}",
                      component_type="AGV", component_id=self.agv_id)

        if self.current_node == DROP_OFF_NODE:
            SimLogger.log(f"instant travel from drop-off to depot",
                          component_type="AGV", component_id=self.agv_id)
            self.current_node = DEPOT_NODE
            depot_x, depot_y = get_node_coordinates(DEPOT_NODE)
            self.cur_x, self.cur_y = depot_x, depot_y
            self.animation_object.x = depot_x
            self.animation_object.y = depot_y
            SimLogger.log("arrived at depot",
                          component_type="AGV", component_id=self.agv_id)
            return

        path_to_depot = dijkstra_shortest_path(self.current_node, DEPOT_NODE, adjacency_matrix)
        for i, node in enumerate(path_to_depot):
            if i == 0:
                continue
            self.travel_to_node_with_animation(node)

        SimLogger.log("arrived at depot",
                      component_type="AGV", component_id=self.agv_id)

    def loading_complete(self):
        if self.current_order and self.current_node in self.current_order.pickup_nodes:
            items_at_this_node = len(self.current_order.items_by_node.get(self.current_node, []))
            self.items_picked_up += items_at_this_node

            SimLogger.log(
                f"picked up {items_at_this_node} items, total: {self.items_picked_up}/{self.total_items_in_order}",
                order_id=self.current_order.order_id, component_type="AGV", component_id=self.agv_id)

        if 1 <= self.current_node <= 60:
            asrs_x, asrs_y = get_node_coordinates(self.current_node)
            self.cur_x, self.cur_y = asrs_x, asrs_y - AnimationConfig.AGV_TRAVEL_OFFSET
            self.animation_object.x = self.cur_x
            self.animation_object.y = self.cur_y
            SimLogger.log(f"moved back to travel position after pickup",
                          component_type="AGV", component_id=self.agv_id)

        self.agv_status = "moving"
        self.activate()

    def go_to_charger(self):
        self.recharge_count += 1
        env.stats.total_recharges += 1
        self.agv_status = "moving"

        SimLogger.log(f"going to charger (battery: {self.battery:.1f}%)",
                      component_type="AGV", component_id=self.agv_id)

        if self.current_node == DROP_OFF_NODE:
            SimLogger.log(f"instant travel from drop-off to charger",
                          component_type="AGV", component_id=self.agv_id)
            charger_x, charger_y = get_node_coordinates(CHARGER_NODE)
            self.cur_x, self.cur_y = charger_x, charger_y
            self.animation_object.x = charger_x
            self.animation_object.y = charger_y
        else:
            path_to_charger = dijkstra_shortest_path(self.current_node, DEPOT_NODE, adjacency_matrix)
            for i, node in enumerate(path_to_charger):
                if i == 0:
                    continue
                self.travel_to_node_with_animation(node)

        self.current_node = CHARGER_NODE
        self.agv_status = "charging"

        charge_time = (MAX_CHARGE - self.battery) / CHARGE_RATE
        self.hold(charge_time)

        self.battery = MAX_CHARGE
        SimLogger.log(f"finished charging, battery: {self.battery}%",
                      component_type="AGV", component_id=self.agv_id)

        self.current_node = DEPOT_NODE
        self.agv_status = "idle"
        depot_x, depot_y = get_node_coordinates(DEPOT_NODE)
        self.cur_x, self.cur_y = depot_x, depot_y
        self.animation_object.x = depot_x
        self.animation_object.y = depot_y

    def step_aside_from_aisle(self, blocked_node):
        """Move to a free corridor neighbor to physically vacate the node for an incoming AGV."""
        neighbors = list(adjacency_matrix.get(self.current_node, {}).keys())
        blocked_aisle = ((blocked_node - 1) // 3) + 1 if 1 <= blocked_node <= 60 else None

        # Prefer neighbors outside the blocked aisle (vertical corridor or cross-link)
        candidates = [
            n for n in neighbors
            if n != blocked_node
            and n not in (DEPOT_NODE, DROP_OFF_NODE, CHARGER_NODE)
            and (((n - 1) // 3) + 1 if 1 <= n <= 60 else None) != blocked_aisle
        ]

        # Sort so unoccupied neighbors are tried first
        def is_occupied(node):
            return any(
                other is not self and (other.current_node == node or other.next_node == node)
                for other in warehouse_system.agv_list
            )

        candidates.sort(key=is_occupied)

        for escape_node in candidates:
            start_node = self.current_node
            SimLogger.log(
                f"stepping aside {start_node} -> {escape_node} to clear blocked node {blocked_node}",
                component_type="AGV",
                component_id=self.agv_id,
            )
            if self.travel_to_node_with_animation(escape_node):
                env.stats.deadlocks_cleared += 1
                SimLogger.log(
                    f"DEADLOCK AVOIDED: vacated node {start_node} -> now at {escape_node}",
                    component_type="AGV",
                    component_id=self.agv_id,
                )
                return True

        # Fallback for node 60 bottleneck: duck into Drop-Off bay (61) so queued traffic can drain
        if self.current_node == 60:
            env.stats.deadlocks_cleared += 1
            SimLogger.log(
                "node 60 gridlocked -> ducking into Drop-Off bay (61) to let traffic clear",
                component_type="AGV",
                component_id=self.agv_id,
            )
            drop_x, drop_y = get_node_coordinates(DROP_OFF_NODE)
            self.move_smoothly_to(drop_x, drop_y)
            self.current_node = DROP_OFF_NODE
            self.agv_status = "queued"

            # Wait briefly for jammed AGVs to clear node 60
            self.hold(10.0)
            while any(
                other is not self and other.current_node == 60
                for other in warehouse_system.agv_list
            ):
                self.hold(1.0)

            # Pull back up to node 60 travel lane and resume
            self.current_node = 60
            x60, y60 = get_node_coordinates(60)
            self.move_smoothly_to(x60, y60 - AnimationConfig.AGV_TRAVEL_OFFSET)
            SimLogger.log(
                "DEADLOCK AVOIDED: returned to node 60 after traffic cleared",
                component_type="AGV",
                component_id=self.agv_id,
            )
            return True

        return False

    def reroute_behind_queue(self, target_node, middle_node, asrs):
        """Loop around to middle_node so this AGV approaches the side-bay from behind the queue."""
        env.stats.reroute_count += 1
        env.stats.fifo_reroute_count += 1
        SimLogger.log(
            f"side-bay at node {target_node} occupied -> rerouting via middle node {middle_node} for FIFO queuing",
            order_id=self.current_order.order_id,
            component_type="AGV",
            component_id=self.agv_id,
        )

        # 1. Travel to middle_node without crossing the occupied side-bay edge (target_node -> middle_node)
        visited = {self.current_node}
        while self.current_node != middle_node:
            detour_path = dijkstra_dynamic_shortest_path(
                self.current_node,
                middle_node,
                adjacency_matrix,
                self,
                avoid_nodes=visited,
                blocked_edge=(target_node, middle_node),
            )
            if len(detour_path) < 2:
                break
            next_hop = detour_path[1]
            if self.travel_to_node_with_animation(next_hop):
                visited.add(next_hop)
            else:
                self.step_aside_from_aisle(next_hop)

        # 2. Approach target_node from middle_node and stop at the back of the FIFO queue
        slot_index = asrs.agv_queue.length()
        wait_x, wait_y = get_asrs_queue_position(target_node, queue_index=slot_index)
        self.move_smoothly_to(wait_x, wait_y)
        self.current_node = target_node

    def move_smoothly_to(self, target_x, target_y, step_dt=0.25):
        """Smoothly animate a short local move (e.g., pulling into a side-bay) without teleporting."""
        start_x, start_y = self.cur_x, self.cur_y
        pixel_dist = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
        if pixel_dist < 1.0:
            self.cur_x, self.cur_y = target_x, target_y
            self.animation_object.x = target_x
            self.animation_object.y = target_y
            return

        # Convert pixels to approximate meters (400px aisle = 50m -> 8px per meter)
        meters = pixel_dist / 8.0
        total_time = max(step_dt, meters / AGV_SPEED)
        steps = max(1, int(round(total_time / step_dt)))

        for i in range(1, steps + 1):
            progress = i / steps
            self.cur_x = start_x + (target_x - start_x) * progress
            self.cur_y = start_y + (target_y - start_y) * progress
            self.animation_object.x = self.cur_x
            self.animation_object.y = self.cur_y
            self.hold(total_time / steps)

    def is_blocking_another_agv(self):
        """Return True if another AGV is trying to enter this node or is queued right next to us."""
        for other in warehouse_system.agv_list:
            if other is self or other.agv_status in ("idle", "charging", "picking_up"):
                continue
            # Another AGV is heading directly to our current node (e.g., exiting the locked aisle)
            if other.next_node == self.current_node:
                return True
            # Another AGV is queued right next to our bounding box
            if (
                other.agv_status == "queued"
                and abs(self.cur_x - other.cur_x) < AnimationConfig.AGV_SIZE + 15
                and abs(self.cur_y - other.cur_y) < AnimationConfig.AGV_SIZE + 15
            ):
                return True
        return False

    def travel_to_node_with_animation(self, destination_node):
        """Travel step-by-step with aisle locks, collision avoidance, and deadlock recovery.
        Returns True if destination_node was reached, False if aborted to resolve a deadlock.
        """
        if self.current_node == destination_node:
            return True

        self.next_node = destination_node

        # Acquire aisle direction lock if traveling horizontally inside an aisle
        aisle_num, direction = get_aisle_and_direction(self.current_node, destination_node)
        lock_acquired = False
        if aisle_num is not None:
            wait_for_lock = 0.0
            waited_on_aisle = False
            while not warehouse_system.can_enter_aisle(aisle_num, direction):
                if not waited_on_aisle:
                    env.stats.aisle_lock_waits += 1
                    waited_on_aisle = True
                self.agv_status = "queued"
                self.total_waiting_time += 0.5
                env.stats.aisle_lock_wait_time += 0.5
                wait_for_lock += 0.5
                self.hold(0.5)
                if wait_for_lock >= 2.0 and self.is_blocking_another_agv():
                    env.stats.reroute_count += 1
                    self.next_node = None
                    return False
            warehouse_system.enter_aisle(aisle_num, direction)
            lock_acquired = True
            if waited_on_aisle:
                env.stats.aisle_lock_entered_after_wait += 1

        try:
            dest_x, dest_y = get_node_coordinates(destination_node)
            if 1 <= destination_node <= 60:
                dest_y -= AnimationConfig.AGV_TRAVEL_OFFSET

            start_x, start_y = self.cur_x, self.cur_y
            distance = calculate_distance_between_nodes(
                self.current_node, destination_node, adjacency_matrix
            )

            if distance <= 0:
                self.cur_x, self.cur_y = dest_x, dest_y
                self.animation_object.x = dest_x
                self.animation_object.y = dest_y
                self.current_node = destination_node
                self.hold(0.1)
                return True

            step_dt = 0.5
            traveled = 0.0
            blocked_time = 0.0
            deadlock_timeout = 2.0

            while traveled < distance:
                step_dist = min(AGV_SPEED * step_dt, distance - traveled)
                step_time = step_dist / AGV_SPEED
                progress = (traveled + step_dist) / distance

                next_x = start_x + (dest_x - start_x) * progress
                next_y = start_y + (dest_y - start_y) * progress

                blocker = self.is_path_blocked(next_x, next_y)
                if blocker is not None:
                    self.agv_status = "queued"
                    self.total_waiting_time += step_dt
                    blocked_time += step_dt
                    self.hold(step_dt)

                    # Deadlock check: stuck for >= deadlock_timeout behind a queued AGV
                    if blocked_time >= deadlock_timeout and blocker.agv_status == "queued":
                        my_exit_dist = distance_to_nearest_aisle_exit(self)
                        other_exit_dist = distance_to_nearest_aisle_exit(blocker)

                        # Yield if closer to the aisle exit; break chain tie after 2x timeout
                        should_yield = (
                            (my_exit_dist < other_exit_dist)
                            or (my_exit_dist == other_exit_dist and self.agv_id > blocker.agv_id)
                            or (blocked_time >= deadlock_timeout * 2.0 and self.agv_id > blocker.agv_id)
                        )

                        if should_yield:
                            env.stats.reroute_count += 1
                            SimLogger.log(
                                f"deadlock with AGV {blocker.agv_id} near node {self.current_node} -> yielding and rerouting",
                                component_type="AGV",
                                component_id=self.agv_id,
                            )
                            # Reverse smoothly back to start_x, start_y (same direction as blocker)
                            while traveled > 0:
                                back_dist = min(AGV_SPEED * step_dt, traveled)
                                traveled -= back_dist
                                back_progress = traveled / distance
                                self.cur_x = start_x + (dest_x - start_x) * back_progress
                                self.cur_y = start_y + (dest_y - start_y) * back_progress
                                self.animation_object.x = self.cur_x
                                self.animation_object.y = self.cur_y
                                self.agv_status = "moving"
                                self.total_distance += back_dist
                                self.battery = max(0, self.battery - back_dist * ENERGY_PER_METER)
                                self.hold(back_dist / AGV_SPEED)

                            return False
                    continue

                blocked_time = 0.0
                self.agv_status = "moving"
                self.cur_x, self.cur_y = next_x, next_y
                self.animation_object.x = next_x
                self.animation_object.y = next_y

                energy_consumed = step_dist * ENERGY_PER_METER
                self.battery = max(0, self.battery - energy_consumed)
                self.total_distance += step_dist
                traveled += step_dist

                self.hold(step_time)

            self.current_node = destination_node
            return True
        finally:
            self.next_node = None
            if lock_acquired:
                warehouse_system.leave_aisle(aisle_num)

# ===============================================================================
# AGV ANIMATION MANAGER - Controls how AGVs look and move on screen
# ===============================================================================

class AGVAnimationManager:
    def __init__(self, agv):
        self.agv = agv
        self.setup_animations()

    def setup_animations(self):
        depot_x, depot_y = get_node_coordinates(DEPOT_NODE)

        self.agv.animation_object = sim.AnimateRectangle(
            spec=(-AnimationConfig.AGV_SIZE // 2, -AnimationConfig.AGV_SIZE // 2,
                  AnimationConfig.AGV_SIZE // 2, AnimationConfig.AGV_SIZE // 2),
            fillcolor=lambda t: self.get_agv_color(),
            linecolor="black",
            linewidth=2,
            x=depot_x, y=depot_y
        )

        self.agv.animation_text = sim.AnimateText(
            text=lambda t: f"{self.agv.agv_id}",
            x=lambda t: self.agv.animation_object.x(t) if callable(
                self.agv.animation_object.x) else self.agv.animation_object.x,
            y=lambda t: self.agv.animation_object.y(t) if callable(
                self.agv.animation_object.y) else self.agv.animation_object.y,
            fontsize=AnimationConfig.FONT_SIZE,
            textcolor="black",
            text_anchor="c"
        )

        self.agv.item_counter_text = sim.AnimateText(
            text=lambda t: self.get_item_counter_text(),
            x=lambda t: self.agv.animation_object.x(t) if callable(
                self.agv.animation_object.x) else self.agv.animation_object.x,
            y=lambda t: (self.agv.animation_object.y(t) if callable(
                self.agv.animation_object.y) else self.agv.animation_object.y) - 20,
            fontsize=8,
            textcolor="black",
            text_anchor="c"
        )

        self.setup_battery_animation()

    def setup_battery_animation(self):
        battery_width, battery_height = AnimationConfig.AGV_SIZE, 5

        self.agv.battery_bg = sim.AnimateRectangle(
            spec=(-battery_width // 2, -AnimationConfig.AGV_SIZE // 2 - battery_height - 2,
                  battery_width // 2, -AnimationConfig.AGV_SIZE // 2 - 2),
            fillcolor="red",
            linecolor="black", linewidth=1,
            x=lambda t: self.agv.animation_object.x(t) if callable(
                self.agv.animation_object.x) else self.agv.animation_object.x,
            y=lambda t: self.agv.animation_object.y(t) if callable(
                self.agv.animation_object.y) else self.agv.animation_object.y
        )

        self.agv.battery_fg = sim.AnimateRectangle(
            spec=lambda t: self.get_battery_spec(battery_width, battery_height),
            fillcolor="green",
            linecolor="black", linewidth=1,
            x=lambda t: self.agv.animation_object.x(t) if callable(
                self.agv.animation_object.x) else self.agv.animation_object.x,
            y=lambda t: self.agv.animation_object.y(t) if callable(
                self.agv.animation_object.y) else self.agv.animation_object.y
        )

    def get_agv_color(self):
        status_colors = {
            "idle": AnimationConfig.AGV_IDLE,
            "moving": AnimationConfig.AGV_MOVING,
            "picking_up": AnimationConfig.AGV_PICKING,
            "queued": AnimationConfig.AGV_QUEUED,
            "charging": AnimationConfig.AGV_CHARGING
        }
        return status_colors.get(self.agv.agv_status, "gray")

    def get_item_counter_text(self):
        if (self.agv.current_order is not None and
                self.agv.agv_status not in ["idle", "charging"]):
            return f"{self.agv.items_picked_up}/{self.agv.total_items_in_order}"
        else:
            return ""

    def get_battery_spec(self, battery_width, battery_height):
        battery_percentage = max(0, min(100, self.agv.battery)) / 100.0
        green_width = battery_width * battery_percentage
        return (-battery_width // 2, -AnimationConfig.AGV_SIZE // 2 - battery_height - 2,
                -battery_width // 2 + green_width, -AnimationConfig.AGV_SIZE // 2 - 2)

# ===============================================================================
# ASRS ANIMATION MANAGER - Controls how ASRS machines look on screen
# ===============================================================================

class ASRSAnimationManager:
    def __init__(self, asrs):
        self.asrs = asrs
        self.setup_animations()

    def setup_animations(self):
        asrs_x, asrs_y = get_node_coordinates(self.asrs.node_number)

        self.asrs.status_text = sim.AnimateText(
            text=lambda t: self.get_picking_status_text(),
            x=asrs_x - 50,
            y=asrs_y,
            fontsize=AnimationConfig.FONT_SIZE,
            textcolor="darkorchid",
            text_anchor="e"
        )

        if INNOVATION:
            container_width, container_height = AnimationConfig.NODE_RADIUS * 2, 4
            self.asrs.container_indicator = sim.AnimateRectangle(
                spec=(-container_width // 2, -AnimationConfig.NODE_RADIUS - container_height - 3,
                      container_width // 2, -AnimationConfig.NODE_RADIUS - 3),
                fillcolor=lambda t: self.get_container_color(),
                linecolor="black", linewidth=1,
                x=asrs_x, y=asrs_y
            )
        else:
            self.asrs.container_indicator = None

    def get_picking_status_text(self):
        if self.asrs.current_picking_order and self.asrs.current_picking_items > 0:
            return f"ASRS picking {self.asrs.current_picking_items} for O-{self.asrs.current_picking_order}"
        else:
            return ""

    def get_container_color(self):
        if INNOVATION and hasattr(self.asrs, 'container') and self.asrs.container.has_items():
            return AnimationConfig.CONTAINER_READY
        else:
            return AnimationConfig.CONTAINER_EMPTY

# ===============================================================================
# LOGGING SYSTEM - Prints messages about what's happening
# ===============================================================================

class SimLogger:
    @staticmethod
    def log(message, order_id=None, component_type=None, component_id=None):
        time_str = f"[{env.now():.1f}T]"
        order_str = f"O{order_id} - " if order_id else ""
        comp_str = f"{component_type} {component_id}: " if (component_type and component_id) else ""
        print(f"{time_str}: {order_str}{comp_str}{message}")

# ===============================================================================
# STATISTICS TRACKING - Keeps track of simulation performance
# ===============================================================================

class WarehouseStats:
    def __init__(self):
        self.orders_created = 0
        self.orders_completed = 0
        self.total_order_time = 0.0
        self.order_times = []
        self.total_recharges = 0
        self.container_ready_transfers = 0
        self.container_wait_transfers = 0
        self.sequential_transfers = 0

        # Traffic, aisle-lock, rerouting, and deadlock metrics
        self.aisle_lock_waits = 0            # Times an AGV had to wait for an aisle direction lock
        self.aisle_lock_wait_time = 0.0      # Total seconds spent waiting for aisle direction locks
        self.aisle_lock_entered_after_wait = 0  # Times an AGV waited on the aisle side and then entered
        self.reroute_count = 0               # Total reroutes triggered (deadlock yield, lock abort, FIFO)
        self.fifo_reroute_count = 0          # Reroutes specifically via middle node for FIFO queuing
        self.deadlocks_cleared = 0           # Deadlocks successfully cleared by yielding/stepping aside

    def update_agv_stats(self, agvs):
        self.total_agv_distance = sum(agv.total_distance for agv in agvs)
        self.total_agv_waiting_time = sum(agv.total_waiting_time for agv in agvs)

    def print_stats(self):
        print("\n===== Enhanced Warehouse Simulation Statistics =====")
        print(f"Innovation mode: {'ON' if INNOVATION else 'OFF'}")
        print(f"Simulation time: {env.now() / 60:.2f} minutes ({env.now() / 3600:.2f} hours)")
        print(f"Orders created: {self.orders_created}")
        print(f"Orders completed: {self.orders_completed}")

        if self.orders_completed > 0:
            avg_order_time = self.total_order_time / self.orders_completed / 60
            print(f"Average order completion time: {avg_order_time:.2f} minutes")

            throughput = self.orders_completed / (env.now() / 3600)
            print(f"Throughput: {throughput:.2f} orders/hour")

            if self.order_times:
                min_time = min(self.order_times) / 60
                max_time = max(self.order_times) / 60
                print(f"Minimum order time: {min_time:.2f} minutes")
                print(f"Maximum order time: {max_time:.2f} minutes")

        self.update_agv_stats(agv_list)
        print(f"Total AGV distance traveled: {self.total_agv_distance:.2f} meters")
        print(f"Total AGV waiting time: {self.total_agv_waiting_time / 60:.2f} minutes")
        print(f"Total battery recharges: {self.total_recharges}")
        if agv_list:
            print(f"Average AGV battery level: {sum(agv.battery for agv in agv_list) / len(agv_list):.1f}%")

        print(f"\n===== Innovation Performance Metrics =====")
        total_transfers = self.container_ready_transfers + self.container_wait_transfers + self.sequential_transfers
        if total_transfers > 0:
            if INNOVATION:
                ready_percentage = (self.container_ready_transfers / total_transfers) * 100
                wait_percentage = (self.container_wait_transfers / total_transfers) * 100
                print(f"Container ready on arrival: {self.container_ready_transfers} ({ready_percentage:.1f}%)")
                print(f"AGV waited for container: {self.container_wait_transfers} ({wait_percentage:.1f}%)")
                print(f"Innovation effectiveness: {ready_percentage:.1f}% of transfers benefited from pre-preparation")
            else:
                print(f"Sequential transfers: {self.sequential_transfers} (100.0%)")
                print("Innovation mode OFF - all transfers use traditional sequential processing")

        print(f"\n===== Individual AGV Statistics =====")
        for agv in agv_list:
            print(f"AGV {agv.agv_id}:")
            print(f"  - Total recharges: {agv.recharge_count}")
            print(f"  - Final battery level: {agv.battery:.1f}%")
            print(f"  - Total distance traveled: {agv.total_distance:.2f} meters")
            print(f"  - Total waiting time: {agv.total_waiting_time / 60:.2f} minutes")
            print(f"  - Current status: {agv.agv_status}")
            print(f"  - Current node: {agv.current_node}")

        print(f"\n===== Traffic, Aisle-Lock & Deadlock Summary =====")
        print(f"Aisle direction lock wait events: {self.aisle_lock_waits}")
        print(f"Total time waiting on aisle direction locks: {self.aisle_lock_wait_time / 60:.2f} minutes")
        print(f"Waited on aisle side & then entered once free: {self.aisle_lock_entered_after_wait}")
        print(f"Total reroutings: {self.reroute_count} (FIFO middle-node detours: {self.fifo_reroute_count})")
        print(f"Deadlocks successfully cleared: {self.deadlocks_cleared}")


class DeadlockMonitor(sim.Component):
    """Logs a snapshot if an AGV freezes >= 10s, and confirms when it recovers."""
    def setup(self, check_interval=5.0, stuck_threshold=10.0):
        self.check_interval = check_interval
        self.stuck_threshold = stuck_threshold
        self.last_pos = {}
        self.stuck_time = {}
        self.reported_stuck = set()  # Track AGVs that were flagged

    def process(self):
        while True:
            self.hold(self.check_interval)
            stuck_agvs = []

            for agv in warehouse_system.agv_list:
                pos = (round(agv.cur_x, 1), round(agv.cur_y, 1))

                if agv.agv_status in ("idle", "charging", "picking_up"):
                    if agv.agv_id in self.reported_stuck:
                        print(f"[t={env.now():.1f}s] [STUCK RESOLVED] AGV {agv.agv_id} is now {agv.agv_status} at node {agv.current_node}")
                        self.reported_stuck.remove(agv.agv_id)
                    self.stuck_time[agv.agv_id] = 0.0
                    self.last_pos[agv.agv_id] = pos
                    continue

                if self.last_pos.get(agv.agv_id) == pos:
                    self.stuck_time[agv.agv_id] = self.stuck_time.get(agv.agv_id, 0.0) + self.check_interval
                else:
                    if agv.agv_id in self.reported_stuck:
                        print(f"[t={env.now():.1f}s] [STUCK RESOLVED] AGV {agv.agv_id} resumed moving (now at {pos}, edge={agv.current_node}->{agv.next_node})")
                        self.reported_stuck.remove(agv.agv_id)
                    self.stuck_time[agv.agv_id] = 0.0
                    self.last_pos[agv.agv_id] = pos

                if self.stuck_time[agv.agv_id] >= self.stuck_threshold:
                    stuck_agvs.append(agv)
                    self.reported_stuck.add(agv.agv_id)

            if stuck_agvs:
                print(f"\n========== [STUCK MONITOR t={env.now():.1f}s] ==========")
                for agv in stuck_agvs:
                    order_id = agv.current_order.order_id if agv.current_order else None
                    in_asrs_q = [
                        n for n, asrs in warehouse_system.asrs_dict.items()
                        if agv in asrs.agv_queue
                    ]
                    aisle_num, direction = (
                        get_aisle_and_direction(agv.current_node, agv.next_node)
                        if agv.next_node is not None else (None, None)
                    )
                    lock_info = warehouse_system.aisle_locks.get(aisle_num) if aisle_num else None

                    nearby = []
                    for other in warehouse_system.agv_list:
                        if other is agv:
                            continue
                        if abs(agv.cur_x - other.cur_x) < 30 and abs(agv.cur_y - other.cur_y) < 30:
                            nearby.append(f"AGV {other.agv_id}({other.agv_status}@{other.cur_x:.0f},{other.cur_y:.0f})")

                    print(
                        f"  AGV {agv.agv_id:2d} | stuck={self.stuck_time[agv.agv_id]:.0f}s | status={agv.agv_status:8s} "
                        f"| edge={agv.current_node}->{agv.next_node} | pos=({agv.cur_x:.0f},{agv.cur_y:.0f}) "
                        f"| O{order_id} | in_asrs_q={in_asrs_q} | aisle_lock={aisle_num}:{lock_info} "
                        f"| nearby={nearby}"
                    )
                print("=================================================\n")



# ===============================================================================
# INITIALIZATION & EXECUTION
# ===============================================================================

env = sim.Environment(trace=False)
env.animation_parameters(
    animate=True,
    width=1200,
    height=750,
    x0=10,
    y0=0,
    x1=1040,
    speed=30,
)
env.stats = WarehouseStats()

warehouse_items = load_warehouse_data()
adjacency_matrix = load_adjacency_matrix()

asrs_list = []
agv_list = []
all_orders = []
available_agvs = []
order_queue = sim.Queue("Order_Queue")

setup_animation()

unique_nodes = set(item['AisleLocation'] for item in warehouse_items)
for node in sorted(unique_nodes):
    asrs = ASRS(name=f"ASRS_Node_{node}", node_number=node)
    asrs_list.append(asrs)
    warehouse_system.register_asrs(node, asrs)

SimLogger.log(f"Created {len(asrs_list)} ASRS systems for nodes: {sorted(unique_nodes)}")

num_agv = AGV_NUMBR
for i in range(num_agv):
    agv = AGV(name=f"AGV_{i + 1}", agv_id=i + 1)
    agv_list.append(agv)
    available_agvs.append(agv)
    warehouse_system.register_agv(agv)

dispatcher = Dispatcher(name="Dispatcher")
warehouse_system.register_dispatcher(dispatcher)

order_definitions = generate_orders_ahead(SEED, SIM_DURATION, warehouse_items)
order_feeder = OrderFeeder(name="OrderFeeder", order_definitions=order_definitions)
deadlock_monitor = DeadlockMonitor(name="DeadlockMonitor")

SimLogger.log(f"Starting enhanced simulation with innovation mode {'ON' if INNOVATION else 'OFF'}")
SimLogger.log("AGVs will now show live movement with color coding:")
SimLogger.log("- Green: Idle AGVs")
SimLogger.log("- Orange: Moving/Queued AGVs")
SimLogger.log("- Red: AGVs actively picking up at ASRS")
SimLogger.log("- Blue: AGVs charging")

VIDEO_DURATION = 3600 * 2  # 2 hours of simulation time
env.video("warehouse_simulation.mp4")

env.run(till=VIDEO_DURATION)

env.video_close()
print("Video saved to warehouse_simulation.mp4")

env.stats.print_stats()

print(f"\nNode-based Navigation Summary:")
print(f"Total unique pickup nodes: {len(unique_nodes)}")
if agv_list:
    avg_distance_per_agv = sum(agv.total_distance for agv in agv_list) / len(agv_list)
    print(f"Average distance per AGV: {avg_distance_per_agv:.2f} meters")

total_orders = len(all_orders)
total_items = sum(len(order.items) for order in all_orders)

print(f"\nSummary:")
print(f"Total orders created: {total_orders}")
print(f"Total items across all orders: {total_items}")
print(f"Average items per order: {total_items / total_orders:.2f}" if total_orders > 0 else "No orders created.")
