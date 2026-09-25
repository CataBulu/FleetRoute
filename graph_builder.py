import networkx as nx
import json

# Load road data from JSON
def load_road_data(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def build_graph(city_coords: dict, road_file: str = "roads.json") -> nx.Graph:
    """Build weighted graph using distance and duration from roads.json."""
    G = nx.Graph()
    roads = load_road_data(road_file)
    for road in roads:
        a = road.get("from")
        b = road.get("to")
        dist = float(road.get("distance_km", 0) or 0.0)
        dur = float(road.get("duration_hours", 0) or 0.0)
        if a not in city_coords or b not in city_coords:
            # Skip edges referencing unknown cities
            continue
        G.add_edge(a, b, distance=dist, duration=dur)
    return G

def get_distance(G: nx.Graph, source: str, target: str) -> float:
    """Shortest-path distance in km."""
    return nx.dijkstra_path_length(G, source, target, weight="distance")

def get_duration(G: nx.Graph, source: str, target: str) -> float:
    """Shortest-path duration in hours."""
    return nx.dijkstra_path_length(G, source, target, weight="duration")

def get_path(G: nx.Graph, source: str, target: str) -> list:
    """Shortest path by distance (list of city names)."""
    return nx.dijkstra_path(G, source, target, weight="distance")