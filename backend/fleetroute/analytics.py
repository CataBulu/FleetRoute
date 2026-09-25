"""Summaries derived from solved routes: KPIs, per-vehicle stats, alerts and timeline."""
import math

from .compliance import CREW_DRIVER_DAILY_LIMIT, SERVICE_TIME, SINGLE_DRIVER_DAILY_LIMIT, order_label
from .planning import vehicle_label

CO2_KG_PER_LITER_DIESEL = 2.68
CO2_KG_PER_TREE_YEAR = 21
FATIGUE_WARNING_SHARE = 0.85


def _km(route):
    return sum(float(s.get("distance_km") or 0) for s in route["steps"])


def _hours(route):
    return sum(float(s.get("duration_h") or 0) for s in route["steps"])


def kpis(routes, dropped, total_orders):
    delivered = {s.get("order_id") for r in routes for s in r["steps"] if s.get("type") == "delivery"}
    delivered -= {d.get("id") for d in dropped}
    total_km = sum(_km(r) for r in routes)
    return {
        "vehicles_used": len(routes),
        "orders_delivered": len(delivered),
        "orders_total": total_orders,
        "total_km": round(total_km, 1),
        "avg_km_per_vehicle": round(total_km / max(len(routes), 1), 1),
    }


def vehicle_stats(routes):
    """Distance, driving time, fuel, CO2 and workload against the trip's EU limit."""
    out = []
    for i, route in enumerate(routes):
        veh = route["vehicle"]
        km, drive_h = _km(route), _hours(route)
        liters = km * float(veh.get("fuel_l100km", 30)) / 100.0
        co2 = liters * CO2_KG_PER_LITER_DIESEL
        daily_limit = CREW_DRIVER_DAILY_LIMIT if veh.get("crew") else SINGLE_DRIVER_DAILY_LIMIT
        # A multi-day trip is compared against days x daily limit, not a single day
        days = max(1, math.ceil(drive_h / daily_limit))
        out.append({
            "index": i, "vehicle": vehicle_label(veh), "crew": bool(veh.get("crew")),
            "distance_km": round(km, 1), "drive_h": round(drive_h, 2),
            "fuel_l": round(liters, 2), "co2_kg": round(co2, 1),
            "trees": round(co2 / CO2_KG_PER_TREE_YEAR, 1),
            "work_days": days, "trip_limit_h": days * daily_limit,
            "workload_share": round(min(drive_h / (days * daily_limit), 1.0), 3),
        })
    return out


def alerts(routes, dropped):
    items = []
    for route in routes:
        veh = route["vehicle"]
        limit = CREW_DRIVER_DAILY_LIMIT if veh.get("crew") else SINGLE_DRIVER_DAILY_LIMIT
        drive_h = _hours(route)
        if drive_h > limit * FATIGUE_WARNING_SHARE:
            items.append({
                "severity": "high" if drive_h > limit else "medium",
                "vehicle": vehicle_label(veh), "type": "Driver fatigue",
                "detail": f"Drive time {drive_h:.1f}h vs daily limit {limit}h",
            })
    for d in dropped:
        items.append({
            "severity": "high", "vehicle": None, "type": "Order dropped",
            "detail": f"{d.get('pickup')} → {d.get('delivery')} "
                      f"({d.get('demand_kg')} kg, deadline {d.get('deadline_h')}h)",
        })
    return sorted(items, key=lambda a: a["severity"] != "high")


def timeline(routes):
    """Per vehicle: gantt segments and key stops, as hour offsets from dispatch.
    Loading/unloading takes SERVICE_TIME at every pickup and delivery."""
    out = []
    for i, route in enumerate(routes):
        steps = route["steps"]
        t = 0.0
        segments, stops = [], []
        first = steps[0]
        stops.append({"type": first["type"], "city": first["city"], "t": 0.0, "order": None})
        for s in steps[1:]:
            kind = s.get("type", "transit")
            dur = float(s.get("duration_h") or 0)
            if dur > 0:
                segments.append({"type": kind, "city": s["city"], "start": t, "end": t + dur})
                t += dur
            label = order_label(s) if kind in ("pickup", "delivery") else None
            if kind != "transit":
                stops.append({"type": kind, "city": s["city"], "t": round(t, 4), "order": label})
            if kind in ("pickup", "delivery"):
                segments.append({"type": "service", "city": s["city"], "start": t, "end": t + SERVICE_TIME,
                                 "detail": "Loading" if kind == "pickup" else "Unloading"})
                t += SERVICE_TIME
        out.append({"index": i, "vehicle": vehicle_label(route["vehicle"]),
                    "segments": segments, "stops": stops, "end": round(t, 4)})
    return out
