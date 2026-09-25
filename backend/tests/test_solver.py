"""Solver behaviour on a tiny network, plus a few real-data scenarios."""
import json

import pytest

from fleetroute import solver
from fleetroute.compliance import build_schedule
from fleetroute.graph import DATA_DIR
from fleetroute.planning import expand_fleet, prepare_orders
from fleetroute.solver import compare_algorithms, expand_leg, prepend_home_leg, solve
from tests.conftest import make_order, make_vehicle


def step_types(route):
    return [s["type"] for s in route["steps"]]


class TestExpandLeg:
    def test_order_fields_copied_to_arrival_step(self, net):
        steps, _ = expand_leg(net, "city_a", "city_b", "delivery", make_order(oid=3, deadline=12, part=1))
        assert {"type": "delivery", "order_id": 3, "deadline_h": 12, "part": 1}.items() <= steps[-1].items()

    def test_part_is_none_for_unsplit_order(self, net):
        steps, _ = expand_leg(net, "depot", "city_a", "pickup", make_order())
        assert steps[-1]["part"] is None

    def test_same_city_leg_still_emits_arrival(self, net):
        steps, poly = expand_leg(net, "city_a", "city_a", "pickup", make_order())
        assert [s["type"] for s in steps] == ["pickup"]
        assert steps[0]["distance_km"] == 0 and len(poly) == 2


class TestHomeLeg:
    depart = [{"type": "depart", "city": "depot", "distance_km": 0, "duration_h": 0}]

    def test_polyline_runs_home_to_depot_without_duplicates(self, net):
        pre, steps = prepend_home_leg(net, make_vehicle(home_city="home"), "depot", self.depart)
        assert pre[0] == net.coords("home") and pre[-1] == net.coords("depot")
        assert pre[0] != pre[1]
        assert steps[0]["type"] == "home_depart" and steps[-1]["type"] == "arrive_depot"

    @pytest.mark.parametrize("home", [None, "depot"])
    def test_no_home_leg_when_starting_at_depot(self, net, home):
        pre, steps = prepend_home_leg(net, make_vehicle(home_city=home), "depot", self.depart)
        assert pre == [] and steps is self.depart


class TestSolve:
    def test_closed_routing_returns_to_depot(self, net):
        out = solve("depot", [make_order()], [make_vehicle()], net=net)
        assert step_types(out["routes"][0])[-1] == "return"

    def test_open_routing_has_no_return(self, net):
        out = solve("depot", [make_order()], [make_vehicle()], return_to_depot=False, net=net)
        assert "return" not in step_types(out["routes"][0])

    def test_unused_vehicles_produce_no_routes(self, net):
        out = solve("depot", [make_order()], [make_vehicle("T1"), make_vehicle("T2"), make_vehicle("T3")], net=net)
        assert len(out["routes"]) == 1 == len(out["polylines"])
        assert "delivery" in step_types(out["routes"][0])

    def test_depot_has_no_service_time(self, net):
        # depot->a 1.5h + 2h loading + a->b 0.7h = 4.2h, fits a 5h deadline
        assert solve("depot", [make_order(deadline=5)], [make_vehicle()], net=net)["dropped"] == []

    def test_impossible_deadline_is_dropped(self, net):
        assert len(solve("depot", [make_order(deadline=3)], [make_vehicle()], net=net)["dropped"]) == 1

    def test_fractional_hours_are_not_rounded_away(self, net):
        # 4.2h needed; rounding legs to whole hours (2h + 2h + 1h = 5h) would drop this
        assert solve("depot", [make_order(deadline=4.5)], [make_vehicle()], net=net)["dropped"] == []

    def test_truck_waits_for_earliest_pickup(self, net):
        out = solve("depot", [make_order(earliest=50, deadline=60)], [make_vehicle()], net=net)
        assert out["dropped"] == [] and out["routes"]

    def test_overweight_order_is_dropped(self, net):
        out = solve("depot", [make_order(demand=9000)], [make_vehicle(capacity=5000)], net=net)
        assert len(out["dropped"]) == 1

    def test_priority_order_wins_when_only_one_fits(self, net):
        # each needs 4.2h and together they exceed the truck, so only one meets a 5h deadline
        normal = make_order(oid=1, demand=4000, deadline=5)
        urgent = make_order(oid=2, demand=4000, deadline=5, priority=True)
        out = solve("depot", [normal, urgent], [make_vehicle(capacity=5000)], net=net)
        assert [d["id"] for d in out["dropped"]] == [1]

    @pytest.mark.parametrize("mode", solver.MODES)
    def test_all_modes_serve_the_order(self, net, mode):
        out = solve("depot", [make_order()], [make_vehicle()], mode=mode, time_limit_s=1, net=net)
        assert out["dropped"] == []

    def test_greedy_fallback_builds_routes(self, net, monkeypatch):
        monkeypatch.setattr(solver, "_solve_model", lambda *a, **k: None)
        out = solve("depot", [make_order()], [make_vehicle(), make_vehicle("T2")], return_to_depot=False, net=net)
        assert len(out["routes"]) == 1
        assert step_types(out["routes"][0]) == ["depart", "pickup", "delivery"]

    def test_edge_cases(self, net):
        assert solve("depot", [], [make_vehicle()], net=net)["routes"] == []
        assert len(solve("depot", [make_order()], [], net=net)["dropped"]) == 1
        assert len(solve("depot", [make_order(pickup="nowhere")], [make_vehicle()], net=net)["dropped"]) == 1


def test_compare_algorithms_reports_every_strategy(net, monkeypatch):
    monkeypatch.setattr(solver, "get_network", lambda: net)
    results = compare_algorithms("depot", [make_order()], [make_vehicle()])
    assert [r["algorithm"] for r in results] == list(solver.STRATEGIES)
    assert all(r["orders_dropped"] == 0 and r["vehicles_used"] == 1 for r in results)


class TestRealNetwork:
    """Scenarios on the shipped Romanian road network."""

    VEHICLES = [make_vehicle("Truck A", 15000), make_vehicle("Truck B", 20000, home_city="Timisoara")]

    @pytest.mark.parametrize("deadline, dropped", [(14, 1), (22, 1), (24, 0)])
    def test_deadline_boundary_includes_eu_rests(self, deadline, dropped):
        # Cluj -> Timisoara 4.75h, 2h loading, Timisoara -> Brasov 6.5h = 13.25h of work,
        # plus a 45 min break and a 9h daily rest for a single driver = 23h
        order = make_order("Timisoara", "Brasov", 1000, deadline=deadline)
        out = solve("Cluj-Napoca", [order], [self.VEHICLES[0]])
        assert len(out["dropped"]) == dropped
        assert build_schedule(out["routes"])["late"] == []

    def test_crew_reaches_deadline_a_single_driver_cannot(self):
        order = make_order("Timisoara", "Brasov", 1000, deadline=16)
        assert len(solve("Cluj-Napoca", [order], [make_vehicle("Solo", 15000)])["dropped"]) == 1
        assert solve("Cluj-Napoca", [order], [make_vehicle("Duo", 15000, crew=True)])["dropped"] == []

    @pytest.mark.parametrize("mode", solver.MODES)
    def test_demo_plan_is_fully_legal(self, mode):
        vehicles = json.loads((DATA_DIR / "demo_fleet.json").read_text(encoding="utf-8"))
        orders = json.loads((DATA_DIR / "demo_orders.json").read_text(encoding="utf-8"))
        out = solve("Brasov", prepare_orders(orders, vehicles, False), expand_fleet(vehicles),
                    mode=mode, time_limit_s=2)
        assert out["dropped"] == []
        assert build_schedule(out["routes"])["late"] == []

    def test_mixed_orders_produce_valid_routes(self):
        orders = [
            make_order("Timisoara", "Brasov", 5000, 12, priority=True, oid=1),
            make_order("Sibiu", "Iasi", 8000, 18, earliest=2, oid=2),
            make_order("Oradea", "Constanta", 12000, 24, oid=3),
        ]
        out = solve("Cluj-Napoca", orders, self.VEHICLES)
        for route in out["routes"]:
            assert route["steps"][0]["type"] in ("depart", "home_depart")
            assert "delivery" in step_types(route)
