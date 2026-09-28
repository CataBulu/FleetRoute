"""Road network: city coordinates, the weighted graph built from roads.json, and road shapes.

Shortest paths are computed in solver.Network (one Dijkstra search per origin)."""
import json
from functools import lru_cache
from pathlib import Path

import networkx as nx

DATA_DIR = Path(__file__).parent / "data"


@lru_cache(maxsize=1)
def load_cities() -> dict:
    """All network nodes: {name: {"coords": [lat, lon], "visible": bool}}.

    The shipped network is every city and town in Romania (scripts/build_road_network.py),
    all visible. A node with visible = false would be a routing-only point the UI hides.
    """
    with open(DATA_DIR / "coords.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_geometry() -> dict:
    """Road shape of each link, {(from, to): [[lat, lon], ...]}, from road_geometry.json.

    The shapes come from OpenStreetMap via OSRM (scripts/fetch_road_geometry.py) and are only
    drawn on the map: distances and durations still come from roads.json. A link without a
    shape, or a missing file, is drawn as a straight line.
    """
    path = DATA_DIR / "road_geometry.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        edges = json.load(f)["edges"]
    return {tuple(k.split("|", 1)): decode_polyline(v["polyline"]) for k, v in edges.items()}


def decode_polyline(encoded: str) -> list:
    """Google encoded polyline (5 decimal places) to [[lat, lon], ...]."""
    points, i, lat, lon = [], 0, 0, 0
    while i < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat, lon = lat + deltas[0], lon + deltas[1]
        points.append([lat / 1e5, lon / 1e5])
    return points


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
