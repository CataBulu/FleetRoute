"""Shared test fixtures: minimal in-memory graph and coords, no file I/O."""
import sys
import os
import pytest
import networkx as nx

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def make_graph() -> nx.Graph:
    """4-node graph: depot, city_a, city_b, home — fully connected."""
    G = nx.Graph()
    G.add_edge("depot",  "city_a", distance=100.0, duration=1.5)
    G.add_edge("depot",  "city_b", distance=130.0, duration=1.8)
    G.add_edge("depot",  "home",   distance=80.0,  duration=1.0)
    G.add_edge("city_a", "city_b", distance=50.0,  duration=0.7)
    G.add_edge("city_a", "home",   distance=120.0, duration=1.6)
    G.add_edge("city_b", "home",   distance=90.0,  duration=1.2)
    return G


def make_coords() -> dict:
    return {
        "depot":  {"coords": [45.0, 25.0], "visible": True},
        "city_a": {"coords": [46.0, 26.0], "visible": True},
        "city_b": {"coords": [47.0, 27.0], "visible": True},
        "home":   {"coords": [44.0, 24.0], "visible": True},
    }


def make_vehicle(name="T1", capacity=5000, home_city=None):
    return {
        "nume": name,
        "capacitate": capacity,
        "numar": 1,
        "echipaj": False,
        "fuel_l100km": 30.0,
        "home_city": home_city,
        "driver_name": "",
        "tahograf": True,
    }


def make_order(pickup="city_a", delivery="city_b", demand=100,
               time_limit_hrs=48, priority=False, oid=1, part=None):
    o = {
        "pickup": pickup,
        "delivery": delivery,
        "demand": demand,
        "time_limit_hrs": time_limit_hrs,
        "earliest_pickup_hrs": 0,
        "priority": priority,
        "id": oid,
    }
    if part is not None:
        o["part"] = part
    return o


@pytest.fixture()
def G():
    return make_graph()


@pytest.fixture()
def coords():
    return make_coords()
