"""HTTP API, against the real road network."""
import pytest
from starlette.testclient import TestClient

from fleetroute.app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def payload(**overrides):
    body = {
        "depot": "Cluj-Napoca",
        "vehicles": [{"name": "Truck", "driver": "Dan", "capacity_kg": 20000, "fuel_l100km": 30,
                      "crew": False, "count": 1, "home_city": "Timisoara"}],
        "orders": [{"pickup": "Iasi", "delivery": "Bucuresti", "demand_kg": 5000, "deadline_h": 48,
                    "earliest_pickup_h": 0, "priority": False}],
        "mode": "economic",
        "return_to_depot": True,
        "allow_split": False,
    }
    return body | overrides


def test_cities_lists_visible_cities_only(client):
    names = [c["name"] for c in client.get("/api/cities").json()["cities"]]
    assert "Cluj-Napoca" in names and "A1xA6" not in names
    assert names == sorted(names)


def test_demo_data_loads(client):
    demo = client.get("/api/demo").json()
    assert demo["vehicles"] and demo["orders"] and demo["depot"]


def test_plan_returns_everything_the_ui_needs(client):
    res = client.post("/api/plan", json=payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) >= {"routes", "polylines", "dropped", "kpis", "vehicle_stats",
                         "alerts", "timeline", "schedule"}
    assert body["kpis"]["orders_delivered"] == 1
    assert body["routes"][0]["steps"][0]["type"] == "home_depart"


@pytest.mark.parametrize("override, message", [
    ({"depot": "Atlantis"}, "depot"),
    ({"orders": []}, "at least one"),
    ({"orders": [{"pickup": "Iasi", "delivery": "Iasi", "demand_kg": 1, "deadline_h": 5}]}, "different"),
    ({"orders": [{"pickup": "Iasi", "delivery": "Arad", "demand_kg": 1, "deadline_h": 5,
                  "earliest_pickup_h": 6}]}, "earliest pickup"),
    ({"orders": [{"pickup": "Iasi", "delivery": "Arad", "demand_kg": 90000, "deadline_h": 50}]}, "splitting"),
    ({"mode": "teleport"}, "mode"),
])
def test_invalid_input_gets_a_readable_400(client, override, message):
    res = client.post("/api/plan", json=payload(**override))
    assert res.status_code == 400
    assert message in res.json()["error"].lower()


def test_malformed_json_is_rejected(client):
    res = client.post("/api/plan", content=b"{nope", headers={"content-type": "application/json"})
    assert res.status_code == 400


def test_exports_round_trip(client):
    routes = client.post("/api/plan", json=payload()).json()["routes"]
    pdf = client.post("/api/export/pdf", json={"routes": routes, "fuel_price": 7.5})
    xlsx = client.post("/api/export/xlsx", json={"routes": routes, "fuel_price": 7.5})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK")
    assert client.post("/api/export/doc", json={"routes": routes}).status_code == 404
    assert client.post("/api/export/pdf", json={"routes": [{"bad": 1}]}).status_code == 400
