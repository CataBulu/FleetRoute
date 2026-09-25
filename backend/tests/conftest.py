"""Shared fixtures: a tiny in-memory road network, no file I/O."""
import networkx as nx
import pytest

from fleetroute.solver import Network


def make_network() -> Network:
    """4 nodes, fully connected: depot, city_a, city_b, home."""
    G = nx.Graph()
    G.add_edge("depot", "city_a", distance=100.0, duration=1.5)
    G.add_edge("depot", "city_b", distance=130.0, duration=1.8)
    G.add_edge("depot", "home", distance=80.0, duration=1.0)
    G.add_edge("city_a", "city_b", distance=50.0, duration=0.7)
    G.add_edge("city_a", "home", distance=120.0, duration=1.6)
    G.add_edge("city_b", "home", distance=90.0, duration=1.2)
    cities = {
        "depot": {"coords": [45.0, 25.0], "visible": True},
        "city_a": {"coords": [46.0, 26.0], "visible": True},
        "city_b": {"coords": [47.0, 27.0], "visible": True},
        "home": {"coords": [44.0, 24.0], "visible": True},
    }
    return Network(cities, G)


def make_vehicle(name="T1", capacity=5000, home_city=None, crew=False):
    return {"name": name, "driver": "", "capacity_kg": capacity, "fuel_l100km": 30.0,
            "crew": crew, "count": 1, "home_city": home_city}


def make_order(pickup="city_a", delivery="city_b", demand=100, deadline=48,
               earliest=0, priority=False, oid=1, part=None):
    return {"id": oid, "part": part, "pickup": pickup, "delivery": delivery,
            "demand_kg": demand, "deadline_h": deadline, "earliest_pickup_h": earliest,
            "priority": priority}


@pytest.fixture()
def net():
    return make_network()
