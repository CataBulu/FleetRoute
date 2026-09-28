"""Build the road network for every city and town in Romania, once, from Wikidata and OSRM.

Writes the three files the planner reads (the planner itself never goes online):
  backend/fleetroute/data/coords.json         every city and town reachable by road
  backend/fleetroute/data/roads.json          links between towns: km and truck hours
  backend/fleetroute/data/road_geometry.json  the real road shape of each link

    python scripts/build_road_network.py [--refresh] [--dry-run]

--dry-run chooses the links and reports how close they come to the real roads, without
fetching any road shapes.

1. Towns: Romania's 103 municipalities and 216 towns, from Wikidata, at their centres. Cities
   the project already had keep their name and position, so saved fleets and orders still
   load. Sulina is left out: it is in the Danube Delta and has no road to the rest of Romania.
2. Links: every town is linked to its 5 nearest towns, plus a minimum spanning tree so the
   whole country is connected.
3. Shortcuts: a trip through the links visits every town centre on the way, which is longer
   than the real road (motorways bypass the towns). OSRM's table service gives the real
   door-to-door distance and time between every pair of towns; wherever the links are over
   5% (and 3 km) longer, or over 10% (and 15 minutes) slower, a direct link is added, worst
   first, until none is. Every link stays under 3 hours of truck driving, because the EU rules
   engine places breaks between links.
4. Roads: OSRM (the public demo server, routing on OpenStreetMap data) gives each link's road
   distance, driving time and shape. Car times become truck times: 10% slower, and never
   faster than an 80 km/h average (Romanian HGV limits are 90 on motorways, 70 on national
   roads).

Links already fetched are kept unless you pass --refresh. The demo server allows light use
only, so the script sends at most one request per second (a full run takes about an hour).
The road data is derived from OpenStreetMap: © OpenStreetMap contributors, ODbL 1.0.
Town names and positions come from Wikidata (CC0).
"""
import json
import math
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np  # installed with OR-Tools

DATA = Path(__file__).resolve().parent.parent / "backend" / "fleetroute" / "data"
GEOMETRY = DATA / "road_geometry.json"
TABLE_CACHE = Path(tempfile.gettempdir()) / "fleetroute-osrm-table.json"
OSRM = "https://router.project-osrm.org"
WIKIDATA = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "FleetRoute road-network builder (github.com/CataBulu/FleetRoute)"}

NEIGHBOURS = 5          # links per town to its nearest towns
MAX_DETOUR = 2.5        # a nearest-town link whose road is this x the straight line is dropped
SHORTCUT_EPS = 0.05     # add a direct link when the links are over 5% longer than the road ...
SHORTCUT_SLACK_KM = 3   # ... and over 3 km longer
SHORTCUT_EPS_H = 0.10  # ... and for truck time, when they are over 10% slower ...
SHORTCUT_SLACK_H = 0.25 # ... and 15 minutes slower
MAX_LINK_H = 3.0        # truck hours; the rules engine places EU breaks between links
TOLERANCE_M = 20        # simplified road shape stays within this distance of the real road
PAUSE_S = 1.1           # demo-server policy: at most one request per second
TABLE_BLOCK = 50        # towns per side of one table request (the demo server allows 100)
TRUCK_SLOWDOWN = 1.10   # trucks take 10% longer than OSRM's car estimate ...
TRUCK_MAX_KMPH = 80     # ... and average at most 80 km/h on any link

RENAMES = {"Piatra-Neamt": "Piatra Neamt"}   # Wikidata's spelling -> this project's name
NO_ROAD = {"Sulina"}                          # towns with no road to the rest of the country

TOWNS_QUERY = """
SELECT ?item ?name ?coord ?county WHERE {
  VALUES ?type { wd:Q640364 wd:Q16858213 }   # municipality of Romania, town in Romania
  ?item wdt:P31 ?type ; wdt:P625 ?coord ; rdfs:label ?name . FILTER(LANG(?name) = "ro")
  OPTIONAL { ?item wdt:P131 ?c . ?c wdt:P31 wd:Q1776764 ; rdfs:label ?county . FILTER(LANG(?county) = "ro") }
}"""


def ascii_name(name: str) -> str:
    """'Târgu Mureș' -> 'Targu Mures' (the network keys stay ASCII, as they always were)."""
    for a, b in (("ș", "s"), ("ş", "s"), ("ț", "t"), ("ţ", "t"), ("Ș", "S"), ("Ş", "S"), ("Ț", "T"), ("Ţ", "T")):
        name = name.replace(a, b)
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()


def fetch_json(url: str, pause: bool = True) -> dict:
    for attempt in range(4):
        try:
            if pause:
                time.sleep(PAUSE_S)
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as res:
                return json.load(res)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def haversine_km(a: list, b: list) -> float:
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def truck_hours(km: float, car_h: float) -> float:
    return max(car_h * TRUCK_SLOWDOWN, km / TRUCK_MAX_KMPH)


# ---------- towns ----------

def load_towns(existing: dict) -> dict:
    """{name: [lat, lon]} for every municipality and town reachable by road."""
    rows = fetch_json(WIKIDATA + "?" + urllib.parse.urlencode({"query": TOWNS_QUERY, "format": "json"}), pause=False)
    towns = {}
    for b in rows["results"]["bindings"]:
        qid = b["item"]["value"].rsplit("/", 1)[1]
        lon, lat = map(float, b["coord"]["value"][len("Point("):-1].split())
        towns.setdefault(qid, (ascii_name(b["name"]["value"]), round(lat, 4), round(lon, 4),
                               ascii_name(b.get("county", {}).get("value", ""))))
    count = {}
    for name, *_ in towns.values():
        count[name] = count.get(name, 0) + 1
    nodes = {}
    for name, lat, lon, county in towns.values():
        name = RENAMES.get(name, name)
        if name in NO_ROAD:
            continue
        if count.get(name, 0) > 1:
            name = f"{name} ({county})"  # e.g. two towns called Stefanesti
        # keep the positions of the cities the project always had (not of its old junction points)
        known = existing.get(name, {})
        nodes[name] = known["coords"] if known.get("visible") else [lat, lon]
    lost = [n for n, v in existing.items() if v.get("visible") and n not in nodes]
    if lost:
        raise SystemExit(f"these cities would disappear, add them to RENAMES: {lost}")
    return dict(sorted(nodes.items()))


# ---------- links ----------

def nearest_links(nodes: dict) -> tuple[set, set]:
    """(links, tree): each town's nearest towns, plus a spanning tree that connects them all."""
    names = list(nodes)
    straight = {(a, b): haversine_km(nodes[a], nodes[b]) for i, a in enumerate(names) for b in names[i + 1:]}
    d = lambda a, b: straight[(a, b) if (a, b) in straight else (b, a)]  # noqa: E731
    links = set()
    for a in names:
        for b in sorted((x for x in names if x != a), key=lambda x: d(a, x))[:NEIGHBOURS]:
            links.add(tuple(sorted((a, b))))
    tree, best = set(), {n: (d(names[0], n), names[0]) for n in names[1:]}  # Prim's algorithm
    while best:
        n = min(best, key=lambda x: best[x][0])
        tree.add(tuple(sorted((n, best.pop(n)[1]))))
        for m in best:
            if d(n, m) < best[m][0]:
                best[m] = (d(n, m), n)
    return links | tree, tree


def road_table(nodes: dict) -> tuple[np.ndarray, np.ndarray]:
    """Door-to-door road km and car hours between every pair of towns (OSRM table service)."""
    names = list(nodes)
    if TABLE_CACHE.exists() and "--refresh" not in sys.argv:
        cached = json.loads(TABLE_CACHE.read_text(encoding="utf-8"))
        if cached["names"] == names and cached["coords"] == [nodes[n] for n in names]:
            return np.array(cached["km"]), np.array(cached["h"])
    n = len(names)
    km, h = np.full((n, n), np.inf), np.full((n, n), np.inf)
    blocks = [list(range(i, min(i + TABLE_BLOCK, n))) for i in range(0, n, TABLE_BLOCK)]
    for si, src in enumerate(blocks):
        for dst in blocks:
            idx = src + [j for j in dst if j not in src]
            coords = ";".join(f"{nodes[names[i]][1]},{nodes[names[i]][0]}" for i in idx)
            sources = ";".join(str(k) for k in range(len(src)))
            dests = ";".join(str(idx.index(j)) for j in dst)
            res = fetch_json(f"{OSRM}/table/v1/driving/{coords}?sources={sources}&destinations={dests}"
                             f"&annotations=distance,duration")
            for a, row_km, row_s in zip(src, res["distances"], res["durations"]):
                for b, m, s in zip(dst, row_km, row_s):
                    if m is not None:
                        km[a, b], h[a, b] = m / 1000, s / 3600
        print(f"  road table: {si + 1}/{len(blocks)} rows of blocks", flush=True)
    TABLE_CACHE.write_text(json.dumps({"names": names, "coords": [nodes[x] for x in names],
                                       "km": km.tolist(), "h": h.tolist()}), encoding="utf-8")
    return km, h


def all_pairs(n: int, index: dict, edges: dict, field: str) -> np.ndarray:
    """Shortest path lengths between all towns over the links (Floyd-Warshall)."""
    d = np.full((n, n), np.inf)
    np.fill_diagonal(d, 0)
    for key, e in edges.items():
        a, b = (index[x] for x in key.split("|"))
        d[a, b] = d[b, a] = min(d[a, b], e[field])
    for k in range(n):
        d = np.minimum(d, d[:, k, None] + d[None, k, :])
    return d


def shortcuts(names: list, km: np.ndarray, h: np.ndarray, road_km: np.ndarray, truck_h: np.ndarray,
              taken: set) -> list:
    """Direct links to add, greedily, until the links are never much longer or slower than the
    real road: first by distance, then by truck time (a motorway can be longer but faster)."""
    n = len(names)
    ok = (truck_h < MAX_LINK_H) & np.isfinite(road_km) & ~np.eye(n, dtype=bool)
    for a, b in taken:
        ok[a, b] = ok[b, a] = False
    added, km, h = [], km.copy(), h.copy()
    for graph, road, eps, slack in ((km, road_km, SHORTCUT_EPS, SHORTCUT_SLACK_KM),
                                    (h, truck_h, SHORTCUT_EPS_H, SHORTCUT_SLACK_H)):
        while True:
            excess = np.where(ok, graph - road * (1 + eps) - slack, -np.inf)
            a, b = np.unravel_index(np.argmax(excess), excess.shape)
            if excess[a, b] <= 0:
                break
            added.append((names[a], names[b]) if names[a] < names[b] else (names[b], names[a]))
            ok[a, b] = ok[b, a] = False
            for g, w in ((km, road_km[a, b]), (h, truck_h[a, b])):  # both views get the new link
                g[:] = np.minimum(g, np.minimum(g[:, a, None] + w + g[None, b, :], g[:, b, None] + w + g[None, a, :]))
    return added


# ---------- roads ----------

def route(a: list, b: list) -> tuple[list, float, float]:
    """OSRM's fastest road a -> b: ([[lat, lon], ...], km, car hours)."""
    r = fetch_json(f"{OSRM}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}?overview=full&geometries=geojson")["routes"][0]
    return [[lat, lon] for lon, lat in r["geometry"]["coordinates"]], r["distance"] / 1000, r["duration"] / 3600


_snaps: dict = {}


def snap_points(p: list) -> list:
    """Nearby road points to p, e.g. both carriageways of a road it sits on."""
    if tuple(p) not in _snaps:
        found = []
        for w in fetch_json(f"{OSRM}/nearest/v1/driving/{p[1]},{p[0]}?number=6")["waypoints"]:
            point = [w["location"][1], w["location"][0]]
            if point not in found:
                found.append(point)
        _snaps[tuple(p)] = found[:3]
    return _snaps[tuple(p)]


def best_route(a: list, b: list) -> tuple[list, float, float]:
    """The fastest road, unless a point snapped onto the wrong carriageway (a U-turn at the
    next exit makes the road much longer than the straight line): then the shortest road
    between nearby snap points."""
    points, km, h = route(a, b)
    if km > 1.6 * haversine_km(a, b) + 10:
        for sa in snap_points(a):
            for sb in snap_points(b):
                p2, km2, h2 = route(sa, sb)
                if km2 < km:
                    points, km, h = p2, km2, h2
    return points, km, h


def simplify(points: list, tolerance_m: float) -> list:
    """Douglas-Peucker on a local flat projection (fine at this scale)."""
    if len(points) < 3:
        return points
    lat0 = math.radians(points[0][0])
    xy = [(p[1] * 111_320 * math.cos(lat0), p[0] * 110_540) for p in points]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        (x1, y1), (x2, y2) = xy[i], xy[j]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-9
        far, best = -1, -1.0
        for k in range(i + 1, j):
            dist = abs(dy * (xy[k][0] - x1) - dx * (xy[k][1] - y1)) / norm
            if dist > best:
                far, best = k, dist
        if best > tolerance_m:
            keep[far] = True
            stack += [(i, far), (far, j)]
    return [p for p, k in zip(points, keep) if k]


def encode(points: list) -> str:
    """Google encoded polyline, 5 decimal places (about 1 m)."""
    out, prev = [], (0, 0)
    for lat, lon in points:
        cur = (round(lat * 1e5), round(lon * 1e5))
        for delta in (cur[0] - prev[0], cur[1] - prev[1]):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev = cur
    return "".join(out)


def decode(polyline: str) -> list:
    """Encoded polyline back to [[lat, lon], ...] (to check a cached link still fits its towns)."""
    points, i, lat, lon = [], 0, 0, 0
    while i < len(polyline):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(polyline[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat, lon = lat + deltas[0], lon + deltas[1]
        points.append([lat / 1e5, lon / 1e5])
    return points


def fetch_links(pairs: list, nodes: dict, edges: dict) -> None:
    """Fetch the road of every pair not in `edges` yet."""
    todo = [p for p in pairs if "|".join(p) not in edges]
    for n, (a, b) in enumerate(todo, 1):
        points, km, car_h = best_route(nodes[a], nodes[b])
        h = truck_hours(km, car_h)
        # start and end exactly on the town points, which OSRM snaps to the nearest road
        edges[f"{a}|{b}"] = {"km": round(km, 1), "h": round(h, 2),
                             "polyline": encode(simplify([nodes[a], *points, nodes[b]], TOLERANCE_M))}
        print(f"  {n:4}/{len(todo)}  {a} - {b}: {km:.1f} km, {h:.2f} h", flush=True)
        if n % 25 == 0:
            write_geometry(edges)


# ---------- files ----------

def write_geometry(edges: dict) -> None:
    head = {
        "about": "Road shape, distance (km) and truck time (h) of each link in roads.json, from scripts/build_road_network.py",
        "source": "OSRM demo server (router.project-osrm.org), routing on OpenStreetMap data",
        "license": "Open Database License (ODbL) 1.0, © OpenStreetMap contributors",
        "generated": date.today().isoformat(),
        "tolerance_m": TOLERANCE_M,
    }
    meta = json.dumps(head, ensure_ascii=False, indent=1)[:-2]  # without the closing "\n}"
    body = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v, separators=(',', ':'))}" for k, v in sorted(edges.items()))
    GEOMETRY.write_text(meta + ',\n "edges": {\n' + body + "\n }\n}\n", encoding="utf-8")


def write_network(nodes: dict, edges: dict) -> None:
    coords = {n: {"coords": c, "visible": True} for n, c in nodes.items()}
    (DATA / "coords.json").write_text(json.dumps(coords, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    roads = [{"from": k.split("|")[0], "to": k.split("|")[1], "duration_hours": e["h"], "distance_km": e["km"]}
             for k, e in sorted(edges.items())]
    (DATA / "roads.json").write_text("[\n" + ",\n".join("  " + json.dumps(r) for r in roads) + "\n]\n", encoding="utf-8")


def report(label: str, graph: np.ndarray, road: np.ndarray, names: list | None = None) -> None:
    mask = np.isfinite(road) & (road > 0) & ~np.eye(len(road), dtype=bool)
    ratio = np.where(mask, graph / np.where(mask, road, 1), 0)
    r = ratio[mask]
    print(f"  {label}: median {np.median(r):.3f}, 95% of pairs under {np.percentile(r, 95):.3f}, "
          f"worst {r.max():.3f} x the real road", flush=True)
    if names:
        worst = np.dstack(np.unravel_index(np.argsort(-ratio, axis=None)[:10:2], ratio.shape))[0]
        print("    worst pairs: " + "; ".join(f"{names[i]} - {names[j]} {ratio[i, j]:.2f}x ({road[i, j]:.0f} real)"
                                         for i, j in worst), flush=True)


def main() -> None:
    existing = json.loads((DATA / "coords.json").read_text(encoding="utf-8"))
    nodes = load_towns(existing)
    names = list(nodes)
    index = {n: i for i, n in enumerate(names)}
    base, tree = nearest_links(nodes)
    print(f"{len(nodes)} towns, {len(base)} nearest-town links", flush=True)

    road_km, road_h = road_table(nodes)
    road_km, road_h = np.minimum(road_km, road_km.T), np.minimum(road_h, road_h.T)
    truck_h = np.maximum(road_h * TRUCK_SLOWDOWN, road_km / TRUCK_MAX_KMPH)

    # choose the links from the table: nearest towns (minus detours), then shortcuts
    def table_edge(a, b):
        i, j = index[a], index[b]
        return {"km": road_km[i, j], "h": truck_h[i, j]}

    chosen = set()
    for a, b in sorted(base):
        e = table_edge(a, b)
        detour = e["km"] > MAX_DETOUR * haversine_km(nodes[a], nodes[b]) + 10 or e["h"] > MAX_LINK_H
        if detour and (a, b) not in tree:
            print(f"  dropped {a} - {b}: {e['km']:.0f} km, {e['h']:.2f} h", flush=True)
        else:
            chosen.add((a, b))
    as_edges = lambda pairs: {f"{a}|{b}": table_edge(a, b) for a, b in pairs}  # noqa: E731
    graph = all_pairs(len(names), index, as_edges(chosen), "km")
    report("nearest-town links, road km", graph, road_km)
    extra = shortcuts(names, graph, all_pairs(len(names), index, as_edges(chosen), "h"), road_km, truck_h,
                      {(index[a], index[b]) for a, b in chosen})
    chosen |= set(extra)
    print(f"{len(extra)} shortcuts, {len(chosen)} links in all", flush=True)
    report("with shortcuts, road km", all_pairs(len(names), index, as_edges(chosen), "km"), road_km, names)
    report("with shortcuts, truck hours", all_pairs(len(names), index, as_edges(chosen), "h"), truck_h, names)
    if "--dry-run" in sys.argv:
        return

    edges = {}
    if GEOMETRY.exists() and "--refresh" not in sys.argv:
        for k, v in json.loads(GEOMETRY.read_text(encoding="utf-8"))["edges"].items():
            a, b = k.split("|")
            if "h" in v and (a, b) in chosen:
                shape = decode(v["polyline"])
                if all(abs(p - q) < 1e-4 for p, q in zip(shape[0] + shape[-1], nodes[a] + nodes[b])):
                    edges[k] = v  # still the same towns at the same places
    fetch_links(sorted(chosen), nodes, edges)
    final = {k: v for k, v in edges.items() if tuple(k.split("|")) in chosen
             and (v["h"] <= MAX_LINK_H or tuple(k.split("|")) in tree)}

    write_geometry(final)
    write_network(nodes, final)
    report("fetched roads, road km", all_pairs(len(names), index, final, "km"), road_km)
    report("fetched roads, truck hours", all_pairs(len(names), index, final, "h"), truck_h)
    longest = max(final.values(), key=lambda e: e["h"])
    print(f"done: {len(nodes)} towns, {len(final)} links (longest {longest['h']} h), "
          f"road_geometry.json {GEOMETRY.stat().st_size // 1024} KB", flush=True)


if __name__ == "__main__":
    main()
