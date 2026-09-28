"""The offline helpers of scripts/build_road_network.py (the parts that need no internet)."""
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from fleetroute.graph import decode_polyline

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_road_network.py"
spec = importlib.util.spec_from_file_location("build_road_network", SCRIPT)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


@pytest.mark.parametrize("name, key", [
    ("Târgu Mureș", "Targu Mures"), ("Ştefăneşti", "Stefanesti"), ("București", "Bucuresti"),
    ("Sighetu Marmației", "Sighetu Marmatiei"), ("Râmnicu Vâlcea", "Ramnicu Valcea"),
])
def test_town_names_become_the_ascii_keys_the_network_uses(name, key):
    assert build.ascii_name(name) == key


def test_encoded_shapes_decode_back_to_the_same_points():
    points = [[45.65723, 25.60122], [45.66001, 25.59013], [46.77121, 23.62364]]
    assert decode_polyline(build.encode(points)) == points
    assert build.decode(build.encode(points)) == points


def test_simplify_keeps_the_ends_and_the_bends():
    straight = [[45.0, 25.0 + i * 0.001] for i in range(50)]
    assert build.simplify(straight, 20) == [straight[0], straight[-1]]
    bent = straight + [[45.0 + i * 0.001, 25.049] for i in range(1, 50)]
    assert [45.0, 25.049] in build.simplify(bent, 20)


def test_truck_time_is_slower_than_a_car_and_capped_at_80_kmh():
    assert build.truck_hours(100, 2.0) == pytest.approx(2.2)
    assert build.truck_hours(200, 1.5) == pytest.approx(2.5)  # 133 km/h by car -> 80 km/h


def test_nearest_links_connect_every_town():
    towns = {f"T{i}": [45 + (i % 5) * 0.3, 22 + (i // 5) * 0.4] for i in range(25)}
    links, tree = build.nearest_links(towns)
    assert tree <= links and len(tree) == len(towns) - 1
    parent = {t: t for t in towns}

    def root(t):
        while parent[t] != t:
            t = parent[t]
        return t

    for a, b in tree:
        parent[root(a)] = root(b)
    assert len({root(t) for t in towns}) == 1


def test_shortcuts_fix_a_detour_and_respect_the_time_limit():
    # A-B-C in a line, but the links make A-C go the long way round (via B at 100 + 100 km)
    names = ["A", "B", "C"]
    road_km = np.array([[0, 100, 120], [100, 0, 100], [120, 100, 0]], dtype=float)
    road_h = road_km / 60
    truck = np.maximum(road_h * build.TRUCK_SLOWDOWN, road_km / build.TRUCK_MAX_KMPH)
    graph_km = np.array([[0, 100, 200], [100, 0, 100], [200, 100, 0]], dtype=float)
    graph_h = graph_km / 60 * build.TRUCK_SLOWDOWN
    assert build.shortcuts(names, graph_km, graph_h, road_km, truck, {(0, 1), (1, 2)}) == [("A", "C")]
    # the same detour, but the direct road is too long for one link: no shortcut
    far = road_km * 3
    far_truck = np.maximum(far / 60 * build.TRUCK_SLOWDOWN, far / build.TRUCK_MAX_KMPH)
    assert math.isclose(far_truck[0, 2], 360 / 60 * build.TRUCK_SLOWDOWN)
    assert build.shortcuts(names, graph_km * 3, graph_h * 3, far, far_truck, {(0, 1), (1, 2)}) == []
