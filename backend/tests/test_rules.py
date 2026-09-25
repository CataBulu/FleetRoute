"""Planning helpers, EU 561/2006 schedule, analytics and exports."""
import pytest

from fleetroute import analytics, compliance, exports
from fleetroute.planning import (PlanningError, expand_fleet, normalize_order, normalize_vehicle,
                                 prepare_orders)
from fleetroute.solver import solve
from tests.conftest import make_order, make_vehicle

CITIES = {"Brasov": {}, "Arad": {}}


def test_legacy_config_keys_are_accepted():
    v = normalize_vehicle({"nume": "Volvo", "driver_name": "Ana", "capacitate": 20000,
                           "echipaj": True, "numar": 2, "home_city": "Arad"}, CITIES)
    assert v == {"name": "Volvo", "driver": "Ana", "capacity_kg": 20000, "fuel_l100km": 30.0,
                 "crew": True, "count": 2, "home_city": "Arad"}
    o = normalize_order({"pickup": "Arad", "delivery": "Brasov", "demand": 500, "time_limit_hrs": 10})
    assert (o["demand_kg"], o["deadline_h"], o["earliest_pickup_h"]) == (500, 10, 0)


def test_unknown_home_city_is_cleared_and_capacity_capped():
    assert normalize_vehicle({"capacity_kg": 1000, "home_city": "Atlantis"}, CITIES)["home_city"] is None
    with pytest.raises(PlanningError):
        normalize_vehicle({"capacity_kg": 50_000}, CITIES)


def test_fleet_expands_by_count_smallest_first():
    fleet = expand_fleet([make_vehicle("Big", 20000) | {"count": 2}, make_vehicle("Small", 5000)])
    assert [v["name"] for v in fleet] == ["Small", "Big", "Big"]


def test_oversized_order_splits_into_parts():
    orders = [normalize_order({"pickup": "Arad", "delivery": "Brasov", "demand_kg": 25000})]
    chunks = prepare_orders(orders, [make_vehicle(capacity=15000)], allow_split=True)
    assert [(c["id"], c["part"], c["demand_kg"]) for c in chunks] == [(1, 1, 15000), (1, 2, 10000)]
    with pytest.raises(PlanningError):
        prepare_orders(orders, [make_vehicle(capacity=15000)], allow_split=False)


def test_priority_orders_are_sorted_first():
    orders = [normalize_order({"pickup": "Arad", "delivery": "Brasov", "demand_kg": 1, "deadline_h": 5}),
              normalize_order({"pickup": "Arad", "delivery": "Brasov", "demand_kg": 1, "deadline_h": 50,
                               "priority": True})]
    assert [c["id"] for c in prepare_orders(orders, [make_vehicle()], False)] == [2, 1]


def test_aptitude_windows_follow_regulation():
    assert compliance.APTITUDE_AFTER_NORMAL_REST == 13
    assert compliance.APTITUDE_AFTER_REDUCED_REST == 15


def _long_route(hours, crew=False):
    """One delivery `hours` of driving away, split into 1h road segments."""
    steps = [{"type": "depart", "city": "D", "distance_km": 0, "duration_h": 0}]
    steps += [{"type": "transit", "city": f"X{i}", "distance_km": 80, "duration_h": 1} for i in range(hours - 1)]
    steps.append({"type": "delivery", "city": "Z", "distance_km": 80, "duration_h": 1,
                  "order_id": 1, "part": None, "deadline_h": 999})
    return [{"vehicle": make_vehicle(crew=crew), "depot": "D", "steps": steps}]


def test_break_after_four_and_a_half_hours():
    rows = compliance.build_schedule(_long_route(6))["rows"]
    kinds = [r["kind"] for r in rows]
    assert kinds.count("break") == 1
    assert kinds.index("break") == 5  # depart + 4 transits, then the break before the 5th hour


def test_daily_rest_for_single_driver_but_not_crew():
    single = [r["kind"] for r in compliance.build_schedule(_long_route(12))["rows"]]
    crew = [r["kind"] for r in compliance.build_schedule(_long_route(12, crew=True))["rows"]]
    assert "daily_rest" in single and "daily_rest" not in crew


def test_late_delivery_is_reported():
    route = _long_route(3)
    route[0]["steps"][-1]["deadline_h"] = 1
    schedule = compliance.build_schedule(route)
    late = schedule["late"]
    assert late and late[0]["order"] == "1" and late[0]["delay_h"] == pytest.approx(2)
    assert [a["type"] for a in analytics.alerts([], schedule)] == ["Late delivery"]


def test_long_but_compliant_trip_raises_no_alert():
    schedule = compliance.build_schedule(_long_route(20))
    assert schedule["late"] == [] and analytics.alerts([], schedule) == []
    assert schedule["arrivals"]["1"] > 20  # rests were inserted


def test_full_pipeline_on_tiny_network(net):
    out = solve("depot", [make_order()], [make_vehicle()], net=net)
    schedule = compliance.build_schedule(out["routes"])
    assert sum(1 for r in schedule["rows"] if r["description"].startswith("Arrive order 1 (delivery)")) == 1
    k = analytics.kpis(out["routes"], out["dropped"], 1)
    assert (k["vehicles_used"], k["orders_delivered"], k["orders_total"]) == (1, 1, 1)
    stats = analytics.vehicle_stats(out["routes"])[0]
    assert stats["co2_kg"] == pytest.approx(stats["fuel_l"] * 2.68, abs=0.2)
    tl = analytics.timeline(out["routes"])[0]
    assert [s["type"] for s in tl["segments"]].count("service") == 2
    assert exports.build_pdf(schedule, 7.5, 1).startswith(b"%PDF")
    assert exports.build_excel(schedule, 7.5).startswith(b"PK")


def test_workload_uses_multi_day_limit():
    route = _long_route(20)
    stats = analytics.vehicle_stats(route)[0]
    assert (stats["work_days"], stats["trip_limit_h"]) == (3, 27)


def test_hhmm_formatting():
    assert exports.fmt_hhmm(1.5) == "01:30"
    assert exports.fmt_hhmm(-0.25) == "-00:15"
    assert exports.fmt_hhmm(1.9999) == "02:00"
    assert exports.fmt_hhmm(None) == "-"
