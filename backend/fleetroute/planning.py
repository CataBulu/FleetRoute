"""Input normalisation and pre-processing before the solver runs."""

MAX_VEHICLE_CAPACITY_KG = 40_000   # 5-axle semi-trailer, legal max without an ARR permit
DEFAULT_FUEL_L100KM = 30.0

# Keys used by configs saved from the original Streamlit version
_LEGACY_VEHICLE_KEYS = {
    "nume": "name", "driver_name": "driver", "capacitate": "capacity_kg",
    "echipaj": "crew", "numar": "count",
}
_LEGACY_ORDER_KEYS = {
    "demand": "demand_kg", "time_limit_hrs": "deadline_h", "earliest_pickup_hrs": "earliest_pickup_h",
}


class PlanningError(ValueError):
    """Input that cannot be planned; the message is safe to show to the user."""


def _rename(d: dict, mapping: dict) -> dict:
    return {mapping.get(k, k): v for k, v in d.items()}


def normalize_vehicle(raw: dict, cities: dict) -> dict:
    v = _rename(raw, _LEGACY_VEHICLE_KEYS)
    home = v.get("home_city") or None
    capacity = int(v.get("capacity_kg") or 0)
    if not 0 < capacity <= MAX_VEHICLE_CAPACITY_KG:
        raise PlanningError(f"Vehicle capacity must be between 1 and {MAX_VEHICLE_CAPACITY_KG} kg.")
    return {
        "name": str(v.get("name") or "Truck").strip(),
        "driver": str(v.get("driver") or "").strip(),
        "capacity_kg": capacity,
        "fuel_l100km": float(v.get("fuel_l100km") or DEFAULT_FUEL_L100KM),
        "crew": bool(v.get("crew", False)),
        "count": max(1, int(v.get("count") or 1)),
        "home_city": home if home in cities else None,
    }


def normalize_order(raw: dict) -> dict:
    o = _rename(raw, _LEGACY_ORDER_KEYS)
    return {
        "pickup": o.get("pickup"),
        "delivery": o.get("delivery"),
        "demand_kg": int(o.get("demand_kg") or 0),
        "deadline_h": float(o.get("deadline_h") or 24),
        "earliest_pickup_h": float(o.get("earliest_pickup_h") or 0),
        "priority": bool(o.get("priority", False)),
    }


def vehicle_label(vehicle: dict) -> str:
    name = vehicle.get("name", "Vehicle")
    return f"{name} ({vehicle['driver']})" if vehicle.get("driver") else name


def expand_fleet(vehicles: list) -> list:
    """One entry per physical truck, smallest first (matches the original ordering)."""
    return [v for v in sorted(vehicles, key=lambda v: v["capacity_kg"]) for _ in range(v["count"])]


def prepare_orders(orders: list, vehicles: list, allow_split: bool) -> list:
    """Give each order a 1-based id; split loads above the largest truck when allowed.
    Priority orders come first, then tightest deadline."""
    max_cap = max((v["capacity_kg"] for v in vehicles), default=0)
    chunks = []
    for oid, order in enumerate(orders, start=1):
        if order["demand_kg"] > max_cap and not allow_split:
            raise PlanningError(
                f"Order {order['pickup']} -> {order['delivery']} ({order['demand_kg']} kg) is larger "
                f"than the biggest truck ({max_cap} kg). Enable load splitting or add a bigger vehicle.")
        if order["demand_kg"] <= max_cap:
            chunks.append({**order, "id": oid, "part": None})
            continue
        remaining, part = order["demand_kg"], 1
        while remaining > 0:
            size = min(remaining, max_cap)
            chunks.append({**order, "id": oid, "part": part, "demand_kg": size})
            remaining -= size
            part += 1
    return sorted(chunks, key=lambda c: (not c["priority"], c["deadline_h"]))
