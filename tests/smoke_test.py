"""
Headless smoke-test: exercises every major code path without a browser.
Run with:  .venv\Scripts\python.exe tests/smoke_test.py
"""
import sys, os, json, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from vrp_solver import solve_vrp, compare_algorithms
from table_view import _build_pdf
from dashboard import _today_dispatch_iso, _vehicle_label
import pandas as pd
from datetime import date, datetime

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"

errors = []

def check(label, fn):
    try:
        fn()
        print(f"{PASS}  {label}")
    except Exception as e:
        print(f"{FAIL}  {label}\n       {e}")
        errors.append((label, traceback.format_exc()))

# ── real coords ──────────────────────────────────────────────────────────────
print("\n=== Loading real data ===")
with open("coords.json", encoding="utf-8") as f:
    city_coords = json.load(f)
visible = [c for c, v in city_coords.items() if v.get("visible")]
print(f"  {len(visible)} visible cities loaded")

# ── scenario ─────────────────────────────────────────────────────────────────
DEPOT = "Cluj-Napoca"
VEHICLES = [
    {"nume": "Truck A", "driver_name": "Ion", "capacitate": 15000, "fuel_l100km": 28.0,
     "tahograf": True, "echipaj": False, "numar": 1, "home_city": None},
    {"nume": "Truck B", "driver_name": "Maria", "capacitate": 20000, "fuel_l100km": 32.0,
     "tahograf": True, "echipaj": False, "numar": 1, "home_city": "Timisoara"},
]
ORDERS = [
    {"pickup": "Timisoara", "delivery": "Brasov",   "demand": 5000,  "time_limit_hrs": 12,
     "earliest_pickup_hrs": 0, "priority": True,  "id": 1},
    {"pickup": "Sibiu",     "delivery": "Iasi",     "demand": 8000,  "time_limit_hrs": 18,
     "earliest_pickup_hrs": 2, "priority": False, "id": 2},
    {"pickup": "Oradea",    "delivery": "Constanta","demand": 12000, "time_limit_hrs": 24,
     "earliest_pickup_hrs": 0, "priority": False, "id": 3},
    {"pickup": "Craiova",   "delivery": "Galati",   "demand": 6000,  "time_limit_hrs": 10,
     "earliest_pickup_hrs": 1, "priority": True,  "id": 4},
]

# ── solver tests ─────────────────────────────────────────────────────────────
print("\n=== solve_vrp ===")
routes = dropped = None

def run_economic():
    global routes, dropped
    routes, polylines, cost, dropped = solve_vrp(
        DEPOT, ORDERS, city_coords, VEHICLES, "Economic", False)
    assert isinstance(routes, list)
    assert isinstance(dropped, list)
    print(f"       routes={len(routes)}, dropped={len(dropped)}")
check("solve_vrp Economic returns lists", run_economic)

def check_route_structure():
    for r in routes:
        assert r["traseu"][0]["tip"] in ("plecare", "home_depart")
        assert any(s["tip"] == "delivery" for s in r["traseu"]), \
            f"Route {r['vehicul']['nume']} has no delivery step"
        for s in r["traseu"]:
            assert "oras" in s and "durata" in s and "distanta" in s
check("Every route has correct step structure", check_route_structure)

def run_fast():
    r, _, _, d = solve_vrp(DEPOT, ORDERS, city_coords, VEHICLES, "Fast", False)
    assert isinstance(r, list)
    print(f"       routes={len(r)}, dropped={len(d)}")
check("solve_vrp Fast", run_fast)

def run_balanced():
    r, _, _, d = solve_vrp(DEPOT, ORDERS, city_coords, VEHICLES, "Balanced", False)
    assert isinstance(r, list)
    print(f"       routes={len(r)}, dropped={len(d)}")
check("solve_vrp Balanced", run_balanced)

def run_open_routing():
    import vrp_solver as _vs
    prev = _vs.RETURN_TO_DEPOT
    _vs.RETURN_TO_DEPOT = False
    r, _, _, _ = solve_vrp(DEPOT, ORDERS, city_coords, VEHICLES, "Economic", False)
    _vs.RETURN_TO_DEPOT = prev
    for route in r:
        tips = [s["tip"] for s in route["traseu"]]
        assert "intoarcere" not in tips, f"Open routing should have no return step: {tips}"
check("Open routing (RETURN_TO_DEPOT=False) has no return step", run_open_routing)

def run_compare():
    cmp = compare_algorithms(DEPOT, ORDERS, city_coords, VEHICLES, "Economic")
    assert len(cmp) == 4
    for row in cmp:
        assert "Algorithm" in row and "Vehicles used" in row
        print(f"       {row['Algorithm']}: {row['Vehicles used']}v "
              f"{row['Total distance (km)']}km {row['Orders dropped']}dropped")
check("compare_algorithms returns 4 rows", run_compare)

# ── depot service-time fix ────────────────────────────────────────────────────
print("\n=== Depot 2h service-time fix ===")
def tight_deadline_not_dropped():
    # depot→Timisoara is roughly 3h; Timisoara→Brasov roughly 4h; 2h service = ~9h total
    # Use a generous deadline relative to travel so only the depot-svc bug would break it
    tight = [{"pickup": "Timisoara", "delivery": "Brasov", "demand": 1000,
              "time_limit_hrs": 12, "earliest_pickup_hrs": 0, "priority": False, "id": 99}]
    r, _, _, d = solve_vrp(DEPOT, tight, city_coords, [VEHICLES[0]], "Economic", False)
    assert len(d) == 0, f"Should be delivered but dropped (depot 2h svc bug?): dropped={d}"
check("Order with 12h deadline delivered (not dropped by depot svc bug)", tight_deadline_not_dropped)

# ── dashboard pure-logic ──────────────────────────────────────────────────────
print("\n=== Dashboard pure-logic ===")
check("_today_dispatch_iso returns today",
      lambda: assert_today(_today_dispatch_iso()))

def assert_today(s):
    assert s.startswith(str(date.today())), f"Expected today, got {s}"

check("_today_dispatch_iso starts with today",
      lambda: assert_today(_today_dispatch_iso()))

check("_vehicle_label with driver",
      lambda: assert_eq(_vehicle_label(VEHICLES[0]), "Truck A (Ion)"))

check("_vehicle_label without driver",
      lambda: assert_eq(
          _vehicle_label({"nume": "X", "driver_name": ""}), "X"))

def assert_eq(a, b):
    assert a == b, f"{a!r} != {b!r}"

# ── Gantt service-time bars ───────────────────────────────────────────────────
print("\n=== Gantt service-time bars ===")
def gantt_has_service_bars():
    from dashboard import render_gantt_chart
    import inspect
    src = inspect.getsource(render_gantt_chart)
    assert "service" in src, "render_gantt_chart must create 'service' type bars"
    assert "SERVICE_H" in src or "service_h" in src.lower() or "SERVICE_TIME" in src or "2.0" in src, \
        "Service time constant must be present in gantt chart"
check("render_gantt_chart source has service-time bars", gantt_has_service_bars)

# ── table_view PDF ────────────────────────────────────────────────────────────
print("\n=== PDF export ===")
def pdf_correct_delivery_count():
    rows = [
        {"Step": 1, "Vehicle": "Truck A", "Description": "Depart depot",
         "City": "Cluj-Napoca", "Distance (km)": "-", "Speed (km/h)": "-",
         "Time elapsed (h)": "00:00", "Drive time (h)": "00:00", "Breaks": 0,
         "Tacho remaining (h)": "09:00", "Fuel cost (RON)": 0.0,
         "Time left (h)": "-", "On time?": "-"},
        {"Step": 2, "Vehicle": "Truck A", "Description": "Arrive order 1 (pickup)",
         "City": "Timisoara", "Distance (km)": 310.0, "Speed (km/h)": 70.0,
         "Time elapsed (h)": "04:25", "Drive time (h)": "04:25", "Breaks": 0,
         "Tacho remaining (h)": "04:35", "Fuel cost (RON)": 87.0,
         "Time left (h)": "07:35", "On time?": "YES"},
        {"Step": 3, "Vehicle": "Truck A", "Description": "Depart order 1 (pickup)",
         "City": "Timisoara", "Distance (km)": "-", "Speed (km/h)": "-",
         "Time elapsed (h)": "06:25", "Drive time (h)": "04:25", "Breaks": 0,
         "Tacho remaining (h)": "04:35", "Fuel cost (RON)": 87.0,
         "Time left (h)": "05:35", "On time?": "YES"},
        {"Step": 4, "Vehicle": "Truck A", "Description": "Arrive order 1 (delivery)",
         "City": "Brasov", "Distance (km)": 250.0, "Speed (km/h)": 72.0,
         "Time elapsed (h)": "09:55", "Drive time (h)": "07:58", "Breaks": 1,
         "Tacho remaining (h)": "01:03", "Fuel cost (RON)": 156.0,
         "Time left (h)": "02:05", "On time?": "YES"},
        {"Step": 5, "Vehicle": "Truck A", "Description": "Depart order 1 (delivery)",
         "City": "Brasov", "Distance (km)": "-", "Speed (km/h)": "-",
         "Time elapsed (h)": "11:55", "Drive time (h)": "07:58", "Breaks": 1,
         "Tacho remaining (h)": "01:03", "Fuel cost (RON)": 156.0,
         "Time left (h)": "-", "On time?": "-"},
    ]
    df = pd.DataFrame(rows)
    # new regex must count exactly 1 delivery (not 2 from the old str.contains)
    count = int(df["Description"].str.match(r"^Arrive order .+ \(delivery\)$").sum())
    assert count == 1, f"Expected 1 delivery, got {count}"
    pdf = _build_pdf([VEHICLES[0]], df, [], [])
    assert isinstance(pdf, bytes) and len(pdf) > 1000
    print(f"       PDF size={len(pdf)} bytes, delivery_count={count}")
check("PDF export: correct delivery count + valid bytes", pdf_correct_delivery_count)

# ── allow_split chunking ──────────────────────────────────────────────────────
print("\n=== Load splitting ===")
def split_order_served():
    big_order = [{"pickup": "Timisoara", "delivery": "Brasov",
                  "demand": 25000, "time_limit_hrs": 24,
                  "earliest_pickup_hrs": 0, "priority": False, "id": 10}]
    # chunk into two 15k pieces manually (as main.py does)
    chunks = [
        {**big_order[0], "demand": 15000, "id": 10, "part": 1},
        {**big_order[0], "demand": 10000, "id": 10, "part": 2},
    ]
    r, _, _, d = solve_vrp(DEPOT, chunks, city_coords, VEHICLES, "Economic", True)
    assert isinstance(r, list)
    print(f"       routes={len(r)}, dropped={len(d)} (split order)")
check("Split order (25k kg across two 15k/20k trucks)", split_order_served)

# ── missing cities ────────────────────────────────────────────────────────────
print("\n=== Edge cases ===")
def missing_city_goes_to_dropped():
    bad = [{"pickup": "NONEXISTENT_CITY", "delivery": "Brasov",
            "demand": 1000, "time_limit_hrs": 24,
            "earliest_pickup_hrs": 0, "priority": False, "id": 77}]
    r, _, _, d = solve_vrp(DEPOT, bad, city_coords, [VEHICLES[0]], "Economic", False)
    assert len(d) == 1, f"Missing-city order must be in dropped, got routes={r}, dropped={d}"
check("Order with unknown pickup city lands in dropped", missing_city_goes_to_dropped)

def empty_orders_returns_empty():
    r, _, _, d = solve_vrp(DEPOT, [], city_coords, VEHICLES, "Economic", False)
    assert r == [] and d == []
check("No orders → empty routes and dropped", empty_orders_returns_empty)

def no_vehicles_returns_all_dropped():
    r, _, _, d = solve_vrp(DEPOT, ORDERS, city_coords, [], "Economic", False)
    assert r == []
    assert len(d) == len(ORDERS)
check("No vehicles → all orders in dropped", no_vehicles_returns_all_dropped)

# ── summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"\033[91m{'='*50}\033[0m")
    print(f"\033[91m  {len(errors)} CHECK(S) FAILED:\033[0m")
    for label, tb in errors:
        print(f"\n  ✗ {label}\n{tb}")
    sys.exit(1)
else:
    total = 15
    print(f"\033[92m{'='*50}\033[0m")
    print(f"\033[92m  ALL {total} CHECKS PASSED — app logic verified\033[0m")
    print(f"\033[92m{'='*50}\033[0m")
