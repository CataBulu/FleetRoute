"""Pickup-and-delivery vehicle routing with Google OR-Tools.

Data shapes (all plain dicts, JSON-ready):
  vehicle: {name, driver, capacity_kg, fuel_l100km, crew, count, home_city}
  order:   {id, part, pickup, delivery, demand_kg, deadline_h, earliest_pickup_h, priority}
  step:    {type, city, coords, distance_km, duration_h, [order_id, part, deadline_h]}
  route:   {vehicle, depot, steps}

Step types: depart, transit, pickup, delivery, return, home_depart, arrive_depot.
"""
import time
from math import atan2, cos, radians, sin, sqrt

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .graph import build_graph, get_distance, get_duration, get_path, load_cities

__all__ = ["solve", "compare_algorithms", "MODES"]

MODES = ("economic", "fast", "balanced")

SECONDS_PER_HOUR = 3600
METERS_PER_KM = 1000
SERVICE_TIME_H = 2                 # loading / unloading at every pickup and delivery
HORIZON_H = 999                    # planning horizon (relaxed windows)
SPAN_COST_COEFFICIENT = 100
SOLVER_TIME_LIMIT_S = 10
METAHEURISTIC_TIME_LIMIT_S = 20
FALLBACK_SPEED_KMPH = 70           # HGV national-road limit in Romania (OUG 195/2002)
KM_PER_HOUR_EQUIVALENT = 60        # balanced mode: one hour of driving weighs like 60 km

# Fixed cost for opening a vehicle, so the solver chains orders on one truck
VEHICLE_STARTUP_COST_KM = 200
VEHICLE_STARTUP_COST_HOURS = 2

STRATEGIES = {
    "PATH_CHEAPEST_ARC": routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
    "SAVINGS": routing_enums_pb2.FirstSolutionStrategy.SAVINGS,
    "GLOBAL_CHEAPEST_ARC": routing_enums_pb2.FirstSolutionStrategy.GLOBAL_CHEAPEST_ARC,
    "PARALLEL_CHEAPEST_INSERTION": routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION,
}


class Network:
    """Road graph plus memoised shortest-path lookups, with a haversine fallback
    for city pairs the graph cannot connect."""

    def __init__(self, cities: dict, G=None):
        self.cities = cities
        self.G = G if G is not None else build_graph(cities)
        self._dist, self._dur, self._path = {}, {}, {}

    def coords(self, city):
        return self.cities[city]["coords"]

    def distance(self, a, b):
        if (a, b) not in self._dist:
            try:
                self._dist[a, b] = get_distance(self.G, a, b)
            except Exception:
                self._dist[a, b] = haversine_km(self.coords(a), self.coords(b))
        return self._dist[a, b]

    def duration(self, a, b):
        if (a, b) not in self._dur:
            try:
                self._dur[a, b] = get_duration(self.G, a, b)
            except Exception:
                self._dur[a, b] = haversine_km(self.coords(a), self.coords(b)) / FALLBACK_SPEED_KMPH
        return self._dur[a, b]

    def path(self, a, b):
        if (a, b) not in self._path:
            try:
                self._path[a, b] = get_path(self.G, a, b)
            except Exception:
                self._path[a, b] = [a, b]
        return self._path[a, b]


_network = None


def get_network() -> Network:
    global _network
    if _network is None:
        _network = Network(load_cities())
    return _network


def haversine_km(a, b):
    R = 6371.0
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    x = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * R * atan2(sqrt(x), sqrt(1 - x))


# ---------- route building helpers ----------

def expand_leg(net, a, b, arrival_type, order=None):
    """Steps along the shortest path a -> b, one per road segment. Only the final
    step carries `arrival_type` and the order metadata. Returns (steps, polyline)."""
    seg_path = net.path(a, b) if a != b else [a, b]
    steps = []
    for i in range(1, len(seg_path)):
        prev, city = seg_path[i - 1], seg_path[i]
        same = prev == city
        steps.append({
            "type": "transit",
            "city": city,
            "coords": net.coords(city),
            "distance_km": 0.0 if same else net.distance(prev, city),
            "duration_h": 0.0 if same else net.duration(prev, city),
        })
    last = steps[-1]
    last["type"] = arrival_type
    if order:
        last["order_id"] = order.get("id")
        last["part"] = order.get("part")
        last["deadline_h"] = order.get("deadline_h")
    polyline = [net.coords(c) for c in seg_path]
    return steps, polyline


def prepend_home_leg(net, vehicle, depot, steps):
    """If the vehicle starts away from the depot, replace the depot departure with
    home -> depot steps. Returns (pre_polyline, steps)."""
    home = vehicle.get("home_city")
    if not home or home == depot or home not in net.cities:
        return [], steps
    home_steps, home_poly = expand_leg(net, home, depot, "arrive_depot")
    start = {"type": "home_depart", "city": home, "coords": net.coords(home),
             "distance_km": 0.0, "duration_h": 0.0}
    return home_poly, [start] + home_steps + steps[1:]


def _route_from_stops(net, depot, vehicle, stops, return_to_depot):
    """stops: [(city, type, order)] visited after leaving the depot."""
    steps = [{"type": "depart", "city": depot, "coords": net.coords(depot),
              "distance_km": 0.0, "duration_h": 0.0}]
    outbound, return_leg = [], []
    cur = depot
    for city, kind, order in stops:
        leg_steps, leg_poly = expand_leg(net, cur, city, kind, order)
        steps += leg_steps
        outbound += leg_poly if not outbound else leg_poly[1:]
        cur = city
    if outbound:
        return_leg = [outbound[-1]]
    if return_to_depot:
        leg_steps, leg_poly = expand_leg(net, cur, depot, "return")
        steps += leg_steps
        return_leg += leg_poly[1:]
    pre, steps = prepend_home_leg(net, vehicle, depot, steps)
    route = {"vehicle": vehicle, "depot": depot, "steps": steps}
    return route, {"pre": pre, "outbound": outbound, "return_leg": return_leg}


def _greedy_assign(net, depot, orders, vehicles):
    """Fallback when OR-Tools finds nothing: tightest deadline first, each order to the
    vehicle with the least added drive time. Returns per-vehicle stop lists."""
    plan = [[] for _ in vehicles]
    last_city = [depot] * len(vehicles)
    for k in sorted(range(len(orders)), key=lambda k: float(orders[k].get("deadline_h", HORIZON_H))):
        o = orders[k]
        cost = lambda v: net.duration(last_city[v], o["pickup"]) + net.duration(o["pickup"], o["delivery"])
        fitting = [v for v in range(len(vehicles)) if o["demand_kg"] <= vehicles[v]["capacity_kg"]]
        best = min(fitting or range(len(vehicles)), key=cost)
        plan[best] += [(o["pickup"], "pickup", o), (o["delivery"], "delivery", o)]
        last_city[best] = o["delivery"]
    return plan


# ---------- OR-Tools model ----------

def _solve_model(net, depot, orders, vehicles, mode, return_to_depot, strategy, time_limit_s):
    """Build and solve the model. Returns per-vehicle stop lists, or None."""
    nodes = [(depot, "depot", None)]
    for o in orders:
        nodes += [(o["pickup"], "pickup", o), (o["delivery"], "delivery", o)]
    N = len(nodes)

    manager = pywrapcp.RoutingIndexManager(N, len(vehicles), 0)
    routing = pywrapcp.RoutingModel(manager)

    def leg(fi, ti):
        a, b = manager.IndexToNode(fi), manager.IndexToNode(ti)
        if a == b or (b == 0 and not return_to_depot):   # open routing: the way home is free
            return 0.0, 0.0
        ca, cb = nodes[a][0], nodes[b][0]
        return net.distance(ca, cb), net.duration(ca, cb)

    if mode == "fast":
        cost_cb = lambda fi, ti: int(leg(fi, ti)[1] * SECONDS_PER_HOUR)
        fixed = VEHICLE_STARTUP_COST_HOURS * SECONDS_PER_HOUR
    elif mode == "balanced":
        def cost_cb(fi, ti):
            km, h = leg(fi, ti)
            return int((km * 0.5 + h * KM_PER_HOUR_EQUIVALENT * 0.5) * METERS_PER_KM)
        fixed = (VEHICLE_STARTUP_COST_KM + VEHICLE_STARTUP_COST_HOURS * KM_PER_HOUR_EQUIVALENT) / 2 * METERS_PER_KM
    else:
        cost_cb = lambda fi, ti: int(leg(fi, ti)[0] * METERS_PER_KM)
        fixed = VEHICLE_STARTUP_COST_KM * METERS_PER_KM
    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(cost_cb))
    routing.SetFixedCostOfAllVehicles(int(fixed))

    # capacity (kg): +demand at pickup, -demand at delivery
    demands = [0] + [sign * o["demand_kg"] for o in orders for sign in (1, -1)]
    demand_idx = routing.RegisterUnaryTransitCallback(lambda i: int(demands[manager.IndexToNode(i)]))
    routing.AddDimensionWithVehicleCapacity(
        demand_idx, 0, [int(v["capacity_kg"]) for v in vehicles], True, "Capacity")

    # time: travel + service at the node being left; waiting allowed (slack)
    horizon = HORIZON_H * SECONDS_PER_HOUR

    def time_cb(fi, ti):
        service = SERVICE_TIME_H if manager.IndexToNode(fi) != 0 else 0
        return int((leg(fi, ti)[1] + service) * SECONDS_PER_HOUR)

    routing.AddDimension(routing.RegisterTransitCallback(time_cb), horizon, horizon, True, "Time")
    time_dim = routing.GetDimensionOrDie("Time")
    time_dim.SetGlobalSpanCostCoefficient(SPAN_COST_COEFFICIENT)

    drop_penalty = horizon * 10
    solver = routing.solver()
    for i, o in enumerate(orders):
        p, d = manager.NodeToIndex(1 + 2 * i), manager.NodeToIndex(2 + 2 * i)
        routing.AddPickupAndDelivery(p, d)
        solver.Add(routing.VehicleVar(p) == routing.VehicleVar(d))
        solver.Add(time_dim.CumulVar(p) <= time_dim.CumulVar(d))
        earliest = float(o.get("earliest_pickup_h") or 0) * SECONDS_PER_HOUR
        deadline = float(o.get("deadline_h") or HORIZON_H) * SECONDS_PER_HOUR
        time_dim.CumulVar(p).SetRange(max(0, int(earliest)), horizon)
        time_dim.CumulVar(d).SetRange(0, max(1, min(int(deadline), horizon)))
        # priority orders are 5x more expensive to drop
        routing.AddDisjunction([p, d], drop_penalty * (5 if o.get("priority") else 1), 2)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = strategy
    if time_limit_s is None:
        if mode in ("fast", "balanced"):
            params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            time_limit_s = METAHEURISTIC_TIME_LIMIT_S
        else:
            time_limit_s = SOLVER_TIME_LIMIT_S
    params.time_limit.seconds = time_limit_s

    solution = routing.SolveWithParameters(params)
    if not solution:
        return None

    plan = []
    for v in range(len(vehicles)):
        stops = []
        index = solution.Value(routing.NextVar(routing.Start(v)))
        while not routing.IsEnd(index):
            stops.append(nodes[manager.IndexToNode(index)])
            index = solution.Value(routing.NextVar(index))
        plan.append(stops)
    return plan


def solve(depot, orders, vehicles, mode="economic", return_to_depot=True,
          strategy="PATH_CHEAPEST_ARC", time_limit_s=None, net=None):
    """Plan routes. `vehicles` is the expanded fleet (one entry per physical truck).

    Returns {"routes", "polylines", "dropped"}; routes and polylines are index-aligned,
    only vehicles that were used appear.
    """
    net = net or get_network()
    empty = {"routes": [], "polylines": [], "dropped": []}
    if not orders:
        return empty
    if not vehicles or depot not in net.cities:
        return {**empty, "dropped": list(orders)}

    valid = [o for o in orders if o.get("pickup") in net.cities and o.get("delivery") in net.cities]
    unknown = [o for o in orders if o not in valid]
    if not valid:
        return {**empty, "dropped": unknown}

    plan = _solve_model(net, depot, valid, vehicles, mode, return_to_depot,
                        STRATEGIES[strategy], time_limit_s)
    if plan is None:
        plan = _greedy_assign(net, depot, valid, vehicles)

    routes, polylines, served = [], [], set()
    for vehicle, stops in zip(vehicles, plan):
        if not stops:
            continue
        served.update(id(order) for _, kind, order in stops if kind == "pickup")
        route, poly = _route_from_stops(net, depot, vehicle, stops, return_to_depot)
        routes.append(route)
        polylines.append(poly)

    dropped = [o for o in valid if id(o) not in served] + unknown
    return {"routes": routes, "polylines": polylines, "dropped": dropped}


def total_route_km(routes):
    return round(sum(float(s.get("distance_km") or 0) for r in routes for s in r["steps"]), 2)


def compare_algorithms(depot, orders, vehicles, mode="economic", return_to_depot=True):
    """Solve with each first-solution strategy and report the results side by side."""
    results = []
    for name in STRATEGIES:
        t0 = time.perf_counter()
        out = solve(depot, orders, vehicles, mode, return_to_depot,
                    strategy=name, time_limit_s=SOLVER_TIME_LIMIT_S)
        results.append({
            "algorithm": name,
            "vehicles_used": len(out["routes"]),
            "total_km": total_route_km(out["routes"]),
            "orders_dropped": len(out["dropped"]),
            "solve_time_s": round(time.perf_counter() - t0, 2),
        })
    return results
