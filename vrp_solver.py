from math import radians, sin, cos, sqrt, atan2
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from graph_builder import build_graph, get_distance, get_duration, get_path

__all__ = ["solve_vrp", "compare_algorithms"]

# Toggle: should vehicles return to depot after the last delivery? (False = open routing / wait)
RETURN_TO_DEPOT = True

# constants
SECONDS_PER_HOUR = 3600
METERS_PER_KM = 1000
DEFAULT_SERVICE_TIME = 2           # hours (service at pickup/delivery)
MAX_TIME_LIMIT = 999               # hours (relaxed windows)
TIME_WINDOW_COEFFICIENT = 100
SOLVER_TIME_LIMIT_SECONDS = 10
TIME_OPTIMIZATION_LIMIT_SECONDS = 20
FALLBACK_SPEED_KMPH = 70           # HGV national road speed limit (Romania OUG 195/2002)

# module-level caches â€” persist for the lifetime of the Streamlit process
_cached_graph = None          # NetworkX graph, rebuilt only when coords changes
_cached_coords_id = None      # id() of the coords dict used to build _cached_graph
_dist_cache: dict = {}        # (city_a, city_b) â†’ km
_dur_cache: dict = {}         # (city_a, city_b) â†’ hours
_path_cache: dict = {}        # (city_a, city_b) â†’ [city, ...]


def _get_graph(coords):
    global _cached_graph, _cached_coords_id
    if _cached_graph is None or id(coords) != _cached_coords_id:
        _cached_graph = build_graph(coords)
        _cached_coords_id = id(coords)
        _dist_cache.clear()
        _dur_cache.clear()
        _path_cache.clear()
    return _cached_graph

# encourage chaining multiple orders on same truck
VEHICLE_STARTUP_COST_KM = 200      # penalty to open a vehicle when cost=distance
VEHICLE_STARTUP_COST_HOURS = 2     # penalty to open a vehicle when cost=time

# helpers
def _haversine_km(a, b):
    R = 6371.0
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2 * R * atan2(sqrt(x), sqrt(1-x))

def _safe_graph_distance(G, coords, ci, cj):
    key = (ci, cj)
    if key not in _dist_cache:
        try:
            _dist_cache[key] = get_distance(G, ci, cj)
        except Exception:
            pa, pb = coords[ci]['coords'], coords[cj]['coords']
            _dist_cache[key] = _haversine_km(pa, pb)
    return _dist_cache[key]

def _safe_graph_duration(G, coords, ci, cj):
    key = (ci, cj)
    if key not in _dur_cache:
        try:
            _dur_cache[key] = get_duration(G, ci, cj)
        except Exception:
            pa, pb = coords[ci]['coords'], coords[cj]['coords']
            dist = _haversine_km(pa, pb)
            _dur_cache[key] = dist / max(FALLBACK_SPEED_KMPH, 1e-6)
    return _dur_cache[key]

def _expand_leg_to_steps(G, coords, a, b, step_type_on_arrival, order_meta=None):
    # per-segment steps along shortest path a->b; mark pickup/delivery only on final node b
    key = (a, b)
    if key not in _path_cache:
        try:
            _path_cache[key] = get_path(G, a, b)
        except Exception:
            _path_cache[key] = [a, b]
    seg_path = _path_cache[key]

    # â”€â”€ Build STEPS (logical city-to-city, unchanged) â”€â”€
    steps = []
    for i in range(1, len(seg_path)):
        prev_city = seg_path[i - 1]
        city = seg_path[i]
        dkm = _safe_graph_distance(G, coords, prev_city, city)
        th = _safe_graph_duration(G, coords, prev_city, city)

        row = {'tip': "intermediar", 'oras': city, 'distanta': dkm, 'durata': th}

        if i == len(seg_path) - 1:
            row['tip'] = step_type_on_arrival
            if order_meta:
                oid = order_meta.get('id')
                row['order_id'] = oid
                row['comanda'] = oid
                row['order_pickup'] = order_meta.get('pickup')
                row['order_delivery'] = order_meta.get('delivery')
                row['time_limit'] = order_meta.get('time_limit_hrs')
                row['part'] = order_meta.get('part')
        steps.append(row)

    # â”€â”€ Build POLYLINE: straight lines between cities along shortest path â”€â”€
    poly_coords = [coords[seg_path[0]]['coords']]
    for i in range(1, len(seg_path)):
        poly_coords.append(coords[seg_path[i]]['coords'])

    return steps, poly_coords

def _estimate_leg_hours(G, coords, a, b):
    try:
        return _safe_graph_duration(G, coords, a, b)
    except Exception:
        pa, pb = coords[a]['coords'], coords[b]['coords']
        d = _haversine_km(pa, pb)
        return d / max(FALLBACK_SPEED_KMPH, 1e-6)

def _prepend_home_leg(G, coords, veh, depot, steps):
    """If vehicle has a home_city different from depot, prepend homeâ†’depot steps.
    Returns (pre_poly, updated_steps)."""
    home_city = veh.get('home_city') if isinstance(veh, dict) else None
    if not home_city or home_city == depot or home_city not in coords:
        return [], steps
    home_steps, home_poly = _expand_leg_to_steps(G, coords, home_city, depot, "arrive_depot")
    home_start = {'tip': 'home_depart', 'oras': home_city, 'distanta': 0, 'durata': 0, 'comanda': None}
    # skip the original 'plecare' depot step (steps[0]) â€” replaced by home sequence
    new_steps = [home_start] + home_steps + steps[1:]
    # home_poly already starts with home_city coords (built by _expand_leg_to_steps)
    return home_poly, new_steps


# solver
def solve_vrp(start_city, pd_requests, coords, vehicle_profiles, routing_mode, allow_split=True):
    # Defensive guards: validate inputs before building the model
    if not vehicle_profiles:
        return [], [], 0.0, list(pd_requests)
    if not pd_requests:
        return [], [], 0.0, []
    # Filter out requests whose pickup/delivery cities are missing from coords
    valid_requests, missing_requests = [], []
    for r in pd_requests:
        if r.get('pickup') in coords and r.get('delivery') in coords:
            valid_requests.append(r)
        else:
            missing_requests.append(r)
    if start_city not in coords:
        return [], [], 0.0, list(pd_requests)
    if not valid_requests:
        return [], [], 0.0, missing_requests
    pd_requests = valid_requests

    pickups = [r['pickup'] for r in pd_requests]
    deliveries = [r['delivery'] for r in pd_requests]
    cities = [start_city] + list(dict.fromkeys(pickups + deliveries))

    G = _get_graph(coords)
    n = len(cities)
    city_index = {c: i for i, c in enumerate(cities)}
    dist_m = [[0]*n for _ in range(n)]
    time_m = [[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                d = t = 0
            else:
                a, b = cities[i], cities[j]
                d = _safe_graph_distance(G, coords, a, b)
                t = _safe_graph_duration(G, coords, a, b)
            dist_m[i][j] = int(round(d))
            time_m[i][j] = int(round(t))

    vehicle_count = max(1, len(vehicle_profiles))
    capacities = [vp['capacitate'] for vp in vehicle_profiles] if vehicle_profiles else [10**9]

    # node list: depot + (pickup, delivery)
    node_list = [start_city]
    node_types = ['depot']
    order_idx = [-1]
    for i, order in enumerate(pd_requests):
        node_list += [order['pickup'], order['delivery']]
        node_types += ['pickup', 'delivery']
        order_idx += [i, i]

    N = len(node_list)
    manager = pywrapcp.RoutingIndexManager(N, vehicle_count, 0)
    routing = pywrapcp.RoutingModel(manager)

    # arc cost
    time_mode = routing_mode in ("Timp minim", "Fast")
    balanced_mode = routing_mode == "Balanced"
    if time_mode:
        def time_cb(from_index, to_index):
            fi = manager.IndexToNode(from_index); ti = manager.IndexToNode(to_index)
            a = node_list[fi]; b = node_list[ti]
            return int(time_m[city_index[a]][city_index[b]] * SECONDS_PER_HOUR)
        cb = routing.RegisterTransitCallback(time_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(cb)
        routing.SetFixedCostOfAllVehicles(int(VEHICLE_STARTUP_COST_HOURS * SECONDS_PER_HOUR))
    elif balanced_mode:
        def balanced_cb(from_index, to_index):
            fi = manager.IndexToNode(from_index); ti = manager.IndexToNode(to_index)
            a = node_list[fi]; b = node_list[ti]
            dist_m_val = dist_m[city_index[a]][city_index[b]] * METERS_PER_KM
            time_eq_m  = time_m[city_index[a]][city_index[b]] * 60 * METERS_PER_KM  # hoursâ†’equiv km
            return int(dist_m_val * 0.5 + time_eq_m * 0.5)
        cb = routing.RegisterTransitCallback(balanced_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(cb)
        routing.SetFixedCostOfAllVehicles(int((VEHICLE_STARTUP_COST_KM + VEHICLE_STARTUP_COST_HOURS * 60) / 2 * METERS_PER_KM))
    else:
        def dist_cb(from_index, to_index):
            fi = manager.IndexToNode(from_index); ti = manager.IndexToNode(to_index)
            a = node_list[fi]; b = node_list[ti]
            return int(dist_m[city_index[a]][city_index[b]] * METERS_PER_KM)
        cb = routing.RegisterTransitCallback(dist_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(cb)
        routing.SetFixedCostOfAllVehicles(int(VEHICLE_STARTUP_COST_KM * METERS_PER_KM))

    # capacity (kg)
    demands = [0]*N
    for i, t in enumerate(node_types):
        if t == 'pickup':
            demands[i] = pd_requests[order_idx[i]]['demand']
        elif t == 'delivery':
            demands[i] = -pd_requests[order_idx[i]]['demand']

    def demand_cb(index):
        node = manager.IndexToNode(index)
        return demands[node]

    dcb = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(dcb, 0, capacities, True, 'Capacity')
    cap_dim = routing.GetDimensionOrDie('Capacity')

    # pickup-delivery constraints
    for i, _ in enumerate(pd_requests):
        p = 1 + 2*i
        d = 1 + 2*i + 1
        routing.AddPickupAndDelivery(manager.NodeToIndex(p), manager.NodeToIndex(d))
        routing.solver().Add(
            routing.VehicleVar(manager.NodeToIndex(p)) == routing.VehicleVar(manager.NodeToIndex(d))
        )
        routing.solver().Add(
            cap_dim.CumulVar(manager.NodeToIndex(p)) <= cap_dim.CumulVar(manager.NodeToIndex(d))
        )

    svc = [int(DEFAULT_SERVICE_TIME * SECONDS_PER_HOUR)] * N
    svc[0] = 0  # depot has no loading/unloading service time
    def full_time_cb(from_index, to_index):
        fi = manager.IndexToNode(from_index); ti = manager.IndexToNode(to_index)
        a = node_list[fi]; b = node_list[ti]
        return int(time_m[city_index[a]][city_index[b]] * SECONDS_PER_HOUR + svc[fi])

    ft_idx = routing.RegisterTransitCallback(full_time_cb)
    routing.AddDimension(ft_idx, 0, int(MAX_TIME_LIMIT * SECONDS_PER_HOUR), True, 'Time')
    time_dim = routing.GetDimensionOrDie('Time')

    # Time windows: delivery deadline + optional earliest pickup
    max_window_s = int(MAX_TIME_LIMIT * SECONDS_PER_HOUR)
    for i in range(N):
        idx = manager.NodeToIndex(i)
        if node_types[i] == 'delivery':
            try:
                deadline_s = int(float(pd_requests[order_idx[i]].get('time_limit_hrs', MAX_TIME_LIMIT)) * SECONDS_PER_HOUR)
            except (TypeError, ValueError):
                deadline_s = max_window_s
            time_dim.CumulVar(idx).SetRange(0, max(1, min(deadline_s, max_window_s)))
        elif node_types[i] == 'pickup':
            try:
                earliest_s = int(float(pd_requests[order_idx[i]].get('earliest_pickup_hrs', 0)) * SECONDS_PER_HOUR)
            except (TypeError, ValueError):
                earliest_s = 0
            time_dim.CumulVar(idx).SetRange(max(0, earliest_s), max_window_s)
        else:
            time_dim.CumulVar(idx).SetRange(0, max_window_s)
    time_dim.SetGlobalSpanCostCoefficient(TIME_WINDOW_COEFFICIENT)

    # Priority orders get a 5Ã— higher drop penalty so the solver avoids dropping them
    drop_penalty_base = max_window_s * 10
    for i in range(len(pd_requests)):
        multiplier = 5 if pd_requests[i].get('priority', False) else 1
        p_idx = manager.NodeToIndex(1 + 2*i)
        d_idx = manager.NodeToIndex(1 + 2*i + 1)
        routing.AddDisjunction([p_idx, d_idx], drop_penalty_base * multiplier, 2)

    # search params
    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    if time_mode or balanced_mode:
        p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        p.time_limit.seconds = TIME_OPTIMIZATION_LIMIT_SECONDS
    else:
        p.time_limit.seconds = SOLVER_TIME_LIMIT_SECONDS

    solution = routing.SolveWithParameters(p)

    # fallback (chained, per-vehicle)
    if not solution:
        routes, polylines = [], []
        vcount = vehicle_count

        # assign orders (tightest deadline first), by minimal added drive-time
        order_ids = list(range(len(pd_requests)))
        order_ids.sort(key=lambda k: float(pd_requests[k].get("time_limit_hrs", MAX_TIME_LIMIT)))

        assignments = [[] for _ in range(vcount)]
        last_city = [start_city for _ in range(vcount)]
        for oid in order_ids:
            o = pd_requests[oid]
            best_v = None
            best_cost = float('inf')
            for vid in range(vcount):
                cap = vehicle_profiles[vid].get("capacitate", 10**9)
                if o.get("demand", 0) > cap:
                    continue
                c = _estimate_leg_hours(G, coords, last_city[vid], o['pickup']) + \
                    _estimate_leg_hours(G, coords, o['pickup'], o['delivery'])
                if c < best_cost:
                    best_cost = c; best_v = vid
            if best_v is None:
                best_v = min(range(vcount), key=lambda vid:
                             _estimate_leg_hours(G, coords, last_city[vid], o['pickup']) +
                             _estimate_leg_hours(G, coords, o['pickup'], o['delivery']))
            assignments[best_v].append(oid)
            last_city[best_v] = o['delivery']

        # build chained routes: depot -> (p/d)* -> depot
        for vid in range(vcount):
            if not assignments[vid]:
                continue
            veh = vehicle_profiles[vid]
            steps = [{'tip': 'plecare', 'oras': start_city, 'distanta': 0, 'durata': 0, 'comanda': None}]
            outbound_poly = []
            return_poly = []
            cur = start_city

            for oid in assignments[vid]:
                o = pd_requests[oid]
                s_steps, s_poly = _expand_leg_to_steps(G, coords, cur, o['pickup'], "pickup", order_meta=o)
                steps += s_steps
                outbound_poly += (s_poly if not outbound_poly else s_poly[1:])
                if s_poly:
                    return_poly = [s_poly[-1]]
                cur = o['pickup']
                s_steps, s_poly = _expand_leg_to_steps(G, coords, cur, o['delivery'], "delivery", order_meta=o)
                steps += s_steps
                outbound_poly += (s_poly if not outbound_poly else s_poly[1:])
                if s_poly:
                    return_poly = [s_poly[-1]]
                cur = o['delivery']

            if RETURN_TO_DEPOT and cur != start_city:
                s_steps, s_poly = _expand_leg_to_steps(G, coords, cur, start_city, "intoarcere", order_meta=None)
                steps += s_steps
                return_poly += (s_poly if not return_poly else s_poly[1:])

            pre_poly, steps = _prepend_home_leg(G, coords, veh, start_city, steps)
            polylines.append({"pre": pre_poly, "outbound": outbound_poly, "return_leg": return_poly})
            routes.append({'vehicul': veh, 'traseu': steps, 'depot': start_city})

        return routes, polylines, 0.0, missing_requests

    # extract OR-Tools solution
    routes, polylines, total_cost = [], [], 0.0
    visited_orders = set()
    for vid in range(vehicle_count):
        index = routing.Start(vid)
        if routing.IsEnd(solution.Value(routing.NextVar(index))):
            continue

        seq_nodes = []
        while not routing.IsEnd(index):
            node_id = manager.IndexToNode(index)
            if node_types[node_id] == 'pickup':
                visited_orders.add(order_idx[node_id])
            seq_nodes.append(node_list[node_id])
            index = solution.Value(routing.NextVar(index))
        # Only append the return-to-depot node if RETURN_TO_DEPOT is True
        if RETURN_TO_DEPOT:
            seq_nodes.append(start_city)

        steps = [{'tip': 'plecare', 'oras': start_city, 'distanta': 0, 'durata': 0, 'comanda': None}]
        outbound_poly = []
        return_poly = []
        picked = set(); onboard = set()

        for a, b in zip(seq_nodes[:-1], seq_nodes[1:]):
            arr_type = "intermediar"
            arr_order_meta = None

            for j, order in enumerate(pd_requests):
                if b == order['pickup'] and j not in picked:
                    arr_type = "pickup"; arr_order_meta = order
                    picked.add(j); onboard.add(j); break

            if arr_type == "intermediar":
                for j, order in enumerate(pd_requests):
                    if b == order['delivery'] and j in onboard:
                        arr_type = "delivery"; arr_order_meta = order
                        onboard.remove(j); break

            if b == start_city and arr_type == "intermediar":
                arr_type = "intoarcere"

            leg_steps, leg_poly = _expand_leg_to_steps(G, coords, a, b, arr_type, order_meta=arr_order_meta)
            steps += leg_steps
            if arr_type == "intoarcere":
                return_poly += (leg_poly if not return_poly else leg_poly[1:])
            else:
                outbound_poly += (leg_poly if not outbound_poly else leg_poly[1:])
                if not return_poly and leg_poly:
                    return_poly = [leg_poly[-1]]

        veh = vehicle_profiles[vid]
        pre_poly, steps = _prepend_home_leg(G, coords, veh, start_city, steps)
        polylines.append({"pre": pre_poly, "outbound": outbound_poly, "return_leg": return_poly})
        routes.append({'vehicul': veh, 'traseu': steps, 'depot': start_city})

    dropped = [pd_requests[i] for i in range(len(pd_requests)) if i not in visited_orders]
    dropped += missing_requests   # also include requests with cities not in coords
    return routes, polylines, 0.0, dropped


# â”€â”€ Algorithm comparison (feature 10) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
import time as _time

_STRATEGIES = [
    ("PATH_CHEAPEST_ARC",          routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC),
    ("SAVINGS",                    routing_enums_pb2.FirstSolutionStrategy.SAVINGS),
    ("GLOBAL_CHEAPEST_ARC",        routing_enums_pb2.FirstSolutionStrategy.GLOBAL_CHEAPEST_ARC),
    ("PARALLEL_CHEAPEST_INSERTION",routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION),
]


def _total_route_km(routes, coords):
    total = 0.0
    for route in routes:
        for step in route.get("traseu", []):
            d = step.get("distanta", 0) or 0
            total += float(d)
    return round(total, 2)


def compare_algorithms(start_city, pd_requests, coords, vehicle_profiles, routing_mode, allow_split=True):
    """Run the VRP with 4 different first-solution strategies and return a comparison table."""
    results = []
    for name, strategy_enum in _STRATEGIES:
        t0 = _time.time()
        # Temporarily patch the search param inside solve_vrp by using a thin wrapper
        routes, _, _, dropped = _solve_with_strategy(
            start_city, pd_requests, coords, vehicle_profiles,
            routing_mode, strategy_enum
        )
        elapsed = round(_time.time() - t0, 2)
        total_km = _total_route_km(routes, coords)
        results.append({
            "Algorithm":        name,
            "Vehicles used":    len(routes),
            "Total distance (km)": total_km,
            "Orders dropped":   len(dropped),
            "Solve time (s)":   elapsed,
        })
    return results


def _solve_with_strategy(start_city, pd_requests, coords, vehicle_profiles,
                         routing_mode, strategy_enum):
    """Internal: same as solve_vrp but with a forced first-solution strategy."""
    pickups    = [r['pickup']   for r in pd_requests]
    deliveries = [r['delivery'] for r in pd_requests]
    cities     = [start_city] + list(dict.fromkeys(pickups + deliveries))
    G          = _get_graph(coords)
    n          = len(cities)
    city_index = {c: i for i, c in enumerate(cities)}

    dist_m = [[0]*n for _ in range(n)]
    time_m = [[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                a, b = cities[i], cities[j]
                dist_m[i][j] = int(round(_safe_graph_distance(G, coords, a, b)))
                time_m[i][j] = int(round(_safe_graph_duration(G, coords, a, b)))

    vehicle_count = max(1, len(vehicle_profiles))
    capacities    = [vp['capacitate'] for vp in vehicle_profiles] if vehicle_profiles else [10**9]

    node_list  = [start_city]
    node_types = ['depot']
    order_idx  = [-1]
    for i, order in enumerate(pd_requests):
        node_list  += [order['pickup'], order['delivery']]
        node_types += ['pickup', 'delivery']
        order_idx  += [i, i]

    N       = len(node_list)
    manager = pywrapcp.RoutingIndexManager(N, vehicle_count, 0)
    routing = pywrapcp.RoutingModel(manager)

    time_mode     = routing_mode in ("Timp minim", "Fast")
    balanced_mode = routing_mode == "Balanced"

    def _dist_cb(fi_, ti_):
        a = node_list[manager.IndexToNode(fi_)]
        b = node_list[manager.IndexToNode(ti_)]
        return int(dist_m[city_index[a]][city_index[b]] * METERS_PER_KM)

    def _time_cb(fi_, ti_):
        a = node_list[manager.IndexToNode(fi_)]
        b = node_list[manager.IndexToNode(ti_)]
        return int(time_m[city_index[a]][city_index[b]] * SECONDS_PER_HOUR)

    def _balanced_cb(fi_, ti_):
        a = node_list[manager.IndexToNode(fi_)]
        b = node_list[manager.IndexToNode(ti_)]
        dist_val = dist_m[city_index[a]][city_index[b]] * METERS_PER_KM
        time_val = time_m[city_index[a]][city_index[b]] * 60 * METERS_PER_KM
        return int(dist_val * 0.5 + time_val * 0.5)

    if time_mode:
        cb = routing.RegisterTransitCallback(_time_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(cb)
        routing.SetFixedCostOfAllVehicles(int(VEHICLE_STARTUP_COST_HOURS * SECONDS_PER_HOUR))
    elif balanced_mode:
        cb = routing.RegisterTransitCallback(_balanced_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(cb)
        routing.SetFixedCostOfAllVehicles(int((VEHICLE_STARTUP_COST_KM + VEHICLE_STARTUP_COST_HOURS * 60) / 2 * METERS_PER_KM))
    else:
        cb = routing.RegisterTransitCallback(_dist_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(cb)
        routing.SetFixedCostOfAllVehicles(int(VEHICLE_STARTUP_COST_KM * METERS_PER_KM))

    demands = [0] * N
    for i, t in enumerate(node_types):
        if t == 'pickup':
            demands[i] = pd_requests[order_idx[i]]['demand']
        elif t == 'delivery':
            demands[i] = -pd_requests[order_idx[i]]['demand']

    dcb = routing.RegisterUnaryTransitCallback(lambda idx: demands[manager.IndexToNode(idx)])
    routing.AddDimensionWithVehicleCapacity(dcb, 0, capacities, True, 'Capacity')
    cap_dim = routing.GetDimensionOrDie('Capacity')

    for i in range(len(pd_requests)):
        p = manager.NodeToIndex(1 + 2*i)
        d = manager.NodeToIndex(1 + 2*i + 1)
        routing.AddPickupAndDelivery(p, d)
        routing.solver().Add(routing.VehicleVar(p) == routing.VehicleVar(d))
        routing.solver().Add(cap_dim.CumulVar(p) <= cap_dim.CumulVar(d))

    svc = [int(DEFAULT_SERVICE_TIME * SECONDS_PER_HOUR)] * N
    svc[0] = 0  # depot has no loading/unloading service time
    def _ft_cb(fi_, ti_):
        a = node_list[manager.IndexToNode(fi_)]
        b = node_list[manager.IndexToNode(ti_)]
        return int(time_m[city_index[a]][city_index[b]] * SECONDS_PER_HOUR + svc[manager.IndexToNode(fi_)])
    ft = routing.RegisterTransitCallback(_ft_cb)
    routing.AddDimension(ft, 0, int(MAX_TIME_LIMIT * SECONDS_PER_HOUR), True, 'Time')
    time_dim = routing.GetDimensionOrDie('Time')
    max_w = int(MAX_TIME_LIMIT * SECONDS_PER_HOUR)
    for i in range(N):
        idx = manager.NodeToIndex(i)
        if node_types[i] == 'delivery':
            dl = int(float(pd_requests[order_idx[i]].get('time_limit_hrs', MAX_TIME_LIMIT)) * SECONDS_PER_HOUR)
            time_dim.CumulVar(idx).SetRange(0, max(1, min(dl, max_w)))
        elif node_types[i] == 'pickup':
            try:
                earliest_s = int(float(pd_requests[order_idx[i]].get('earliest_pickup_hrs', 0)) * SECONDS_PER_HOUR)
            except (TypeError, ValueError):
                earliest_s = 0
            time_dim.CumulVar(idx).SetRange(max(0, earliest_s), max_w)
        else:
            time_dim.CumulVar(idx).SetRange(0, max_w)
    time_dim.SetGlobalSpanCostCoefficient(TIME_WINDOW_COEFFICIENT)

    dp = max_w * 10
    for i in range(len(pd_requests)):
        multiplier = 5 if pd_requests[i].get('priority', False) else 1
        routing.AddDisjunction([manager.NodeToIndex(1+2*i), manager.NodeToIndex(1+2*i+1)], dp * multiplier, 2)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = strategy_enum
    params.time_limit.seconds = SOLVER_TIME_LIMIT_SECONDS

    solution = routing.SolveWithParameters(params)
    if not solution:
        return [], [], 0.0, list(pd_requests)

    routes, polylines = [], []
    visited = set()
    for vid in range(vehicle_count):
        index = routing.Start(vid)
        if routing.IsEnd(solution.Value(routing.NextVar(index))):
            continue
        seq = []
        while not routing.IsEnd(index):
            nid = manager.IndexToNode(index)
            if node_types[nid] == 'pickup':
                visited.add(order_idx[nid])
            seq.append(node_list[nid])
            index = solution.Value(routing.NextVar(index))
        if RETURN_TO_DEPOT:
            seq.append(start_city)

        steps = [{'tip': 'plecare', 'oras': start_city, 'distanta': 0, 'durata': 0, 'comanda': None}]
        outbound_poly, return_poly = [], []
        picked, onboard = set(), set()
        for a, b in zip(seq[:-1], seq[1:]):
            arr_type, arr_meta = "intermediar", None
            for j, order in enumerate(pd_requests):
                if b == order['pickup'] and j not in picked:
                    arr_type = "pickup"; arr_meta = order; picked.add(j); onboard.add(j); break
            if arr_type == "intermediar":
                for j, order in enumerate(pd_requests):
                    if b == order['delivery'] and j in onboard:
                        arr_type = "delivery"; arr_meta = order; onboard.remove(j); break
            if b == start_city and arr_type == "intermediar":
                arr_type = "intoarcere"
            leg_steps, leg_poly = _expand_leg_to_steps(G, coords, a, b, arr_type, order_meta=arr_meta)
            steps += leg_steps
            if arr_type == "intoarcere":
                return_poly += (leg_poly if not return_poly else leg_poly[1:])
            else:
                outbound_poly += (leg_poly if not outbound_poly else leg_poly[1:])
                if not return_poly and leg_poly:
                    return_poly = [leg_poly[-1]]

        veh = vehicle_profiles[vid]
        pre_poly, steps = _prepend_home_leg(G, coords, veh, start_city, steps)
        polylines.append({"pre": pre_poly, "outbound": outbound_poly, "return_leg": return_poly})
        routes.append({'vehicul': veh, 'traseu': steps, 'depot': start_city})

    dropped = [pd_requests[i] for i in range(len(pd_requests)) if i not in visited]
    return routes, polylines, 0.0, dropped


