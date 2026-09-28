"""Road shapes: decoding, orientation, how legs use them, and the bundled data file."""
import json
from math import atan2, cos, radians, sin, sqrt

import pytest

from fleetroute.graph import DATA_DIR, decode_polyline, load_cities, load_geometry, load_roads
from fleetroute.solver import Network, expand_leg
from tests.conftest import make_network, make_order


def km_along(points):
    total = 0.0
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        p1, p2 = radians(lat1), radians(lat2)
        x = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
        total += 2 * 6371 * atan2(sqrt(x), sqrt(1 - x))
    return total


def test_decodes_the_reference_polyline():
    # the worked example from Google's encoded polyline documentation
    assert decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [[38.5, -120.2], [40.7, -120.95], [43.252, -126.453]]


class TestSegment:
    @pytest.fixture()
    def shaped(self):
        base = make_network()
        bend = [[45.0, 25.0], [45.5, 25.2], [46.0, 26.0]]  # depot -> city_a
        return Network(base.cities, base.G, geometry={("depot", "city_a"): bend})

    def test_uses_the_stored_shape(self, shaped):
        assert shaped.segment("depot", "city_a")[1] == [45.5, 25.2]

    def test_reverses_the_shape_when_driven_the_other_way(self, shaped):
        assert shaped.segment("city_a", "depot") == [[46.0, 26.0], [45.5, 25.2], [45.0, 25.0]]

    def test_straight_line_when_a_link_has_no_shape(self, shaped):
        assert shaped.segment("city_a", "city_b") == [shaped.coords("city_a"), shaped.coords("city_b")]

    def test_every_step_carries_its_road_and_the_line_has_no_repeated_joints(self, shaped):
        steps, line = expand_leg(shaped, "city_b", "city_a", "pickup", make_order())
        steps2, line2 = expand_leg(shaped, "depot", "city_b", "delivery", make_order())
        for leg_steps, leg_line in ((steps, line), (steps2, line2)):
            joined = [leg_steps[0]["geometry"][0]]
            for s in leg_steps:
                assert s["geometry"][-1] == s["coords"]
                joined += s["geometry"][1:]
            assert leg_line == joined
        assert shaped.segment("depot", "city_a")[1] in expand_leg(shaped, "depot", "city_a", "pickup", make_order())[1]


class TestBundledShapes:
    """The shipped road_geometry.json must cover the shipped road network."""

    cities = load_cities()
    shapes = load_geometry()

    @pytest.mark.parametrize("road", load_roads(), ids=lambda r: f"{r['from']}-{r['to']}")
    def test_every_link_has_a_shape_from_city_to_city(self, road):
        shape = self.shapes.get((road["from"], road["to"]))
        assert shape, "missing: run scripts/fetch_road_geometry.py"
        assert shape[0] == pytest.approx(self.cities[road["from"]]["coords"], abs=1e-5)
        assert shape[-1] == pytest.approx(self.cities[road["to"]]["coords"], abs=1e-5)
        # the drawn road should be about as long as the distance the planner uses
        assert 0.7 <= km_along(shape) / road["distance_km"] <= 1.5

    def test_the_file_credits_openstreetmap(self):
        meta = json.loads((DATA_DIR / "road_geometry.json").read_text(encoding="utf-8"))
        assert "OpenStreetMap" in meta["license"] and "ODbL" in meta["license"]
