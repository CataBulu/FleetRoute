"""The shipped road network: every city and town in Romania, connected by real roads."""
import networkx as nx
import pytest

from fleetroute.graph import build_graph, load_cities, load_roads

# The cities the project shipped before the country-wide network. Saved fleets, orders and
# scenarios refer to them by these names, so they must never disappear or be renamed.
ORIGINAL_CITIES = [
    "Alba Iulia", "Alexandria", "Arad", "Bacau", "Baia Mare", "Barlad", "Bistrita", "Botosani",
    "Braila", "Brasov", "Bucuresti", "Buzau", "Calarasi", "Campulung", "Cluj-Napoca",
    "Constanta", "Craiova", "Deva", "Drobeta-Turnu Severin", "Focsani", "Galati", "Giurgiu",
    "Hunedoara", "Iasi", "Lugoj", "Mangalia", "Medgidia", "Medias", "Miercurea Ciuc", "Mioveni",
    "Navodari", "Odorheiu Secuiesc", "Onesti", "Oradea", "Pascani", "Piatra Neamt", "Pitesti",
    "Ploiesti", "Ramnicu Sarat", "Ramnicu Valcea", "Resita", "Roman", "Satu Mare",
    "Sfantu Gheorghe", "Sibiu", "Sighetu Marmatiei", "Slatina", "Slobozia", "Suceava",
    "Targoviste", "Targu Jiu", "Targu Mures", "Targu Neamt", "Tecuci", "Timisoara", "Tulcea",
    "Turda", "Vaslui", "Zalau",
]

cities = load_cities()
graph = build_graph(cities)


def test_every_city_and_town_reachable_by_road_is_a_node():
    # Romania's 103 municipalities and 216 towns, except Sulina: it is in the Danube Delta
    # and has no road to the rest of the country
    assert len(cities) == 318 and "Sulina" not in cities
    assert all(c["visible"] for c in cities.values())


def test_the_whole_country_is_connected():
    assert set(graph.nodes) == set(cities)
    assert nx.is_connected(graph)


def test_original_city_names_still_exist():
    assert [n for n in ORIGINAL_CITIES if n not in cities] == []


@pytest.mark.parametrize("road", load_roads(), ids=lambda r: f"{r['from']}-{r['to']}")
def test_every_link_has_a_plausible_truck_time(road):
    speed = road["distance_km"] / road["duration_hours"]
    assert 15 <= speed <= 80.5, f"{speed:.0f} km/h"
    # the EU rules engine places breaks between links, so no link may reach the 4.5 h window
    assert road["duration_hours"] <= 4.0

