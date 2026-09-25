"""Road network: city coordinates and the weighted graph built from roads.json."""
import json
from functools import lru_cache
from pathlib import Path

import networkx as nx

DATA_DIR = Path(__file__).parent / "data"


@lru_cache(maxsize=1)
def load_cities() -> dict:
    """All network nodes: {name: {"coords": [lat, lon], "visible": bool}}.

    Hidden nodes are motorway junctions and small towns used for routing only.
    """
    with open(DATA_DIR / "coords.json", encoding="utf-8") as f:
        return json.load(f)


def load_roads() -> list:
    with open(DATA_DIR / "roads.json", encoding="utf-8") as f:
        return json.load(f)


def build_graph(cities: dict) -> nx.Graph:
    """Weighted undirected graph with `distance` (km) and `duration` (h) on each edge."""
    G = nx.Graph()
    for road in load_roads():
        a, b = road.get("from"), road.get("to")
        if a not in cities or b not in cities:
            continue
        G.add_edge(
            a, b,
            distance=float(road.get("distance_km", 0) or 0.0),
            duration=float(road.get("duration_hours", 0) or 0.0),
        )
    return G


def get_distance(G: nx.Graph, source: str, target: str) -> float:
    """Shortest-path distance in km."""
    return nx.dijkstra_path_length(G, source, target, weight="distance")


def get_duration(G: nx.Graph, source: str, target: str) -> float:
    """Shortest-path duration in hours."""
    return nx.dijkstra_path_length(G, source, target, weight="duration")


def get_path(G: nx.Graph, source: str, target: str) -> list:
    """Shortest path by distance, as a list of city names."""
    return nx.dijkstra_path(G, source, target, weight="distance")
