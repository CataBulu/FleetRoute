"""Starlette API. Run with:  uvicorn fleetroute.app:app --app-dir backend"""
import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import analytics, compliance, exports, solver
from .graph import DATA_DIR, load_cities
from .planning import (PlanningError, expand_fleet, normalize_order, normalize_vehicle,
                       prepare_orders)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
MAX_ORDERS = 200
MAX_TRUCKS = 100


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Request body must be valid JSON.")
    if not isinstance(body, dict):
        raise HTTPException(400, "Request body must be a JSON object.")
    return body


def _planning_input(body: dict) -> dict:
    """Validate a plan/compare request and turn it into solver arguments."""
    cities = load_cities()
    depot = body.get("depot")
    if depot not in cities:
        raise PlanningError("Choose a depot from the city list.")
    raw_vehicles, raw_orders = body.get("vehicles") or [], body.get("orders") or []
    if not isinstance(raw_vehicles, list) or not isinstance(raw_orders, list):
        raise PlanningError("Vehicles and orders must be lists.")
    if not raw_vehicles or not raw_orders:
        raise PlanningError("Add at least one vehicle and one order.")
    if len(raw_orders) > MAX_ORDERS:
        raise PlanningError(f"At most {MAX_ORDERS} orders per plan.")

    vehicles = [normalize_vehicle(v, cities) for v in raw_vehicles]
    if sum(v["count"] for v in vehicles) > MAX_TRUCKS:
        raise PlanningError(f"At most {MAX_TRUCKS} trucks per plan.")
    orders = [normalize_order(o) for o in raw_orders]
    for n, o in enumerate(orders, start=1):
        if o["pickup"] not in cities or o["delivery"] not in cities:
            raise PlanningError(f"Order {n} uses a city that is not on the map.")
        if o["pickup"] == o["delivery"]:
            raise PlanningError(f"Order {n}: pickup and delivery must be different cities.")
        if o["demand_kg"] <= 0:
            raise PlanningError(f"Order {n}: quantity must be positive.")
        if o["earliest_pickup_h"] >= o["deadline_h"]:
            raise PlanningError(f"Order {n}: earliest pickup must be before the deadline.")

    mode = body.get("mode", "economic")
    if mode not in solver.MODES:
        raise PlanningError(f"Routing mode must be one of {', '.join(solver.MODES)}.")
    return {
        "depot": depot,
        "orders": prepare_orders(orders, vehicles, bool(body.get("allow_split", False))),
        "vehicles": expand_fleet(vehicles),
        "mode": mode,
        "return_to_depot": bool(body.get("return_to_depot", True)),
        "total_orders": len(orders),
    }


async def cities(request):
    data = load_cities()
    visible = [{"name": n, "lat": c["coords"][0], "lon": c["coords"][1]}
               for n, c in data.items() if c.get("visible")]
    return JSONResponse({"cities": sorted(visible, key=lambda c: c["name"])})


async def demo(request):
    data = load_cities()
    with open(DATA_DIR / "demo_fleet.json", encoding="utf-8") as f:
        vehicles = [normalize_vehicle(v, data) for v in json.load(f)]
    with open(DATA_DIR / "demo_orders.json", encoding="utf-8") as f:
        orders = [normalize_order(o) for o in json.load(f)]
    return JSONResponse({"depot": "Brasov", "vehicles": vehicles, "orders": orders})


async def plan(request):
    args = _planning_input(await _json_body(request))
    total = args.pop("total_orders")
    result = await run_in_threadpool(solver.solve, **args)
    routes, dropped = result["routes"], result["dropped"]
    return JSONResponse({
        "routes": routes,
        "polylines": result["polylines"],
        "dropped": dropped,
        "kpis": analytics.kpis(routes, dropped, total),
        "vehicle_stats": analytics.vehicle_stats(routes),
        "alerts": analytics.alerts(routes, dropped),
        "timeline": analytics.timeline(routes),
        "schedule": compliance.build_schedule(routes),
    })


async def compare(request):
    args = _planning_input(await _json_body(request))
    args.pop("total_orders")
    return JSONResponse({"results": await run_in_threadpool(solver.compare_algorithms, **args)})


async def export(request):
    fmt = request.path_params["fmt"]
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(404, "Export format must be xlsx or pdf.")
    body = await _json_body(request)
    routes = body.get("routes")
    if not isinstance(routes, list) or not routes:
        raise PlanningError("Nothing to export yet. Generate routes first.")
    try:
        fuel_price = float(body.get("fuel_price", 7.5))
        schedule = compliance.build_schedule(routes)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PlanningError("The routes in this request are not in the expected format.")
    if fmt == "xlsx":
        data = exports.build_excel(schedule, fuel_price)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = exports.build_pdf(schedule, fuel_price, len(routes))
        media = "application/pdf"
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="fleetroute-report.{fmt}"'})


async def planning_error(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=400)


async def http_error(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


routes = [
    Route("/api/health", lambda r: JSONResponse({"status": "ok"})),
    Route("/api/cities", cities),
    Route("/api/demo", demo),
    Route("/api/plan", plan, methods=["POST"]),
    Route("/api/compare", compare, methods=["POST"]),
    Route("/api/export/{fmt:str}", export, methods=["POST"]),
]
if FRONTEND_DIST.is_dir():
    routes.append(Mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend"))

app = Starlette(
    routes=routes,
    exception_handlers={PlanningError: planning_error, HTTPException: http_error},
)
