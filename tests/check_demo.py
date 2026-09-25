import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from vrp_solver import solve_vrp

with open("coords.json", encoding="utf-8") as f:
    coords = json.load(f)
with open("demo_fleet.json", encoding="utf-8") as f:
    fleet = json.load(f)
with open("demo_orders.json", encoding="utf-8") as f:
    orders = json.load(f)

for i, o in enumerate(orders, 1):
    o["id"] = i

routes, _, _, dropped = solve_vrp(
    start_city="Cluj-Napoca",
    pd_requests=orders,
    coords=coords,
    vehicle_profiles=fleet,
    routing_mode="Economic",
    allow_split=False,
)

print(f"Routes: {len(routes)}   Dropped: {len(dropped)}")
for r in routes:
    veh   = r["vehicul"]["nume"]
    drv   = r["vehicul"]["driver_name"]
    stops = [s["oras"] for s in r["traseu"] if s["tip"] in ("pickup", "delivery")]
    km    = sum(float(s.get("distanta", 0) or 0) for s in r["traseu"])
    home  = r["vehicul"].get("home_city") or "depot"
    print(f"  [{veh} / {drv}] home={home}  stops={stops}  {round(km)} km")

if dropped:
    print("\nDROPPED:")
    for d in dropped:
        print(f"  {d['pickup']} -> {d['delivery']}  deadline={d['time_limit_hrs']}h")
    sys.exit(1)
else:
    print("\nAll 6 orders delivered successfully - demo scenario is good!")
