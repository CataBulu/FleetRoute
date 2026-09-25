import base64
import streamlit as st
import folium
import pydeck as pdk
from streamlit_folium import st_folium
from folium.plugins import AntPath, Fullscreen, MiniMap, TimestampedGeoJson, HeatMap
from math import radians, sin, cos, sqrt, atan2
from datetime import date, datetime, timedelta


def _today_dispatch_iso() -> str:
    return datetime.combine(date.today(), datetime.min.time().replace(hour=8)).isoformat()

__all__ = ["draw_initial_map", "draw_route_map", "draw_simulation_map", "draw_route_map_3d"]

MAP_CENTER = [45.9432, 24.9668]
DEFAULT_ZOOM = 7
PATH_WEIGHT = 5
ANTPATH_DELAY_MS = 600

# Vibrant red/amber route colours for the RED/BLACK theme
COLORS = [
    "#FF003C",  # vivid red
    "#FF6B00",  # neon orange
    "#FFB700",  # warm amber
    "#FF4458",  # hot coral
    "#FFD93D",  # gold
    "#FF1744",  # crimson
    "#FF8C42",  # tangerine
    "#FFA600",  # amber
    "#E63946",  # deep red
    "#FF5E5B",  # salmon
    "#FFAA00",  # bright amber
]

# Dark tile layer — CartoDB DarkMatter (almost black, perfect for neon overlay)
TILE_URL  = "https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png"
TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'


def _route_roles(routes, start_city):
    roles = {start_city: "depot"}
    for route in (routes or []):
        for step in route.get("traseu", []):
            tip = step.get("tip", "")
            city = step.get("oras", "")
            if not city:
                continue
            existing = roles.get(city)
            if existing == "depot":
                continue  # depot role is immutable
            if tip == "pickup":
                roles[city] = "pickup"   # pickup always wins
            elif tip == "delivery":
                if existing != "pickup":  # don't demote pickup → delivery
                    roles[city] = "delivery"
            elif tip == "home_depart":
                if existing is None:      # only mark if city has no role yet
                    roles[city] = "current_location"
    return roles


def _current_location_marker(coords, city):
    """Cyan pulsing pin — driver's current starting location (home city)."""
    html = """
    <div style="position:relative;">
      <div style="position:absolute;left:-16px;top:-16px;width:32px;height:32px;
        border-radius:50%;background:#00B8FF;opacity:0.22;
        animation:cl-pulse 2.2s ease-in-out infinite;"></div>
      <div style="position:absolute;left:-10px;top:-10px;width:20px;height:20px;
        border-radius:50%;
        background:radial-gradient(circle, #FFFFFF 0%, #00B8FF 60%);
        border:2px solid #00EEFF;
        box-shadow:0 0 14px #00B8FF, 0 0 28px #00B8FF88;
        z-index:10;
        display:flex;align-items:center;justify-content:center;
        font-size:10px;line-height:1;">📍</div>
    </div>
    <style>
      @keyframes cl-pulse {
        0%,100% { transform:scale(1);   opacity:0.25; }
        50%     { transform:scale(2.0); opacity:0.08; }
      }
    </style>
    """
    return folium.Marker(
        location=coords,
        tooltip=f"📍 CURRENT LOCATION: {city}",
        icon=folium.DivIcon(html=html, icon_size=(0, 0), icon_anchor=(0, 0)),
    )


def _pulsing_depot_marker(coords, city):
    """Triple-ring pulsing neon depot beacon."""
    html = f"""
    <div style="position:relative;">
      <div style="position:absolute;left:-22px;top:-22px;width:44px;height:44px;
        border-radius:50%;border:2px solid #FF003C;
        animation:depot-ring 2s ease-out infinite;"></div>
      <div style="position:absolute;left:-18px;top:-18px;width:36px;height:36px;
        border-radius:50%;border:2px solid #FF6B00;
        animation:depot-ring 2s ease-out infinite 0.6s;"></div>
      <div style="position:absolute;left:-14px;top:-14px;width:28px;height:28px;
        border-radius:50%;border:2px solid #FFB700;
        animation:depot-ring 2s ease-out infinite 1.2s;"></div>
      <div style="position:absolute;left:-9px;top:-9px;width:18px;height:18px;
        border-radius:50%;
        background:radial-gradient(circle, #FFFFFF 0%, #FF003C 50%, #00B8FF 100%);
        border:2px solid #FFFFFF;
        box-shadow:0 0 20px #FF003C, 0 0 40px #FF003C;
        animation:depot-core 1.5s ease-in-out infinite;
        z-index:10;"></div>
    </div>
    <style>
      @keyframes depot-ring {{
        0%   {{ transform:scale(0.4); opacity:1;   border-width:3px; }}
        100% {{ transform:scale(2.2); opacity:0;   border-width:1px; }}
      }}
      @keyframes depot-core {{
        0%,100% {{ box-shadow:0 0 20px #FF003C, 0 0 40px #FF003C;        transform:scale(1);   }}
        50%     {{ box-shadow:0 0 30px #FF6B00, 0 0 60px #FF6B00;        transform:scale(1.15);}}
      }}
    </style>
    """
    return folium.Marker(
        location=coords,
        tooltip=f"⚡ DEPOT: {city}",
        icon=folium.DivIcon(html=html, icon_size=(0, 0), icon_anchor=(0, 0)),
    )


def _pickup_marker(coords, city):
    html = f"""
    <div style="position:relative;">
      <div style="position:absolute;left:-12px;top:-12px;width:24px;height:24px;
        border-radius:50%;background:#FFA600;opacity:0.4;
        animation:px-pulse 2s ease-in-out infinite;"></div>
      <div style="position:absolute;left:-8px;top:-8px;width:16px;height:16px;
        border-radius:50%;
        background:radial-gradient(circle, #FFB700, #FFA600);
        border:2px solid #FFFFFF;
        box-shadow:0 0 12px #FFA600;
        z-index:10;
        display:flex;align-items:center;justify-content:center;
        font-size:8px;color:#000;font-weight:bold;">↑</div>
    </div>
    <style>
      @keyframes px-pulse {{
        0%,100% {{ transform:scale(1);   opacity:0.5; }}
        50%     {{ transform:scale(1.6); opacity:0.1; }}
      }}
    </style>
    """
    return folium.Marker(
        location=coords,
        tooltip=f"📦 PICKUP: {city}",
        icon=folium.DivIcon(html=html, icon_size=(0, 0), icon_anchor=(0, 0)),
    )


def _delivery_marker(coords, city):
    html = f"""
    <div style="position:relative;">
      <div style="position:absolute;left:-12px;top:-12px;width:24px;height:24px;
        border-radius:50%;background:#FF6B00;opacity:0.4;
        animation:dl-pulse 2s ease-in-out infinite;"></div>
      <div style="position:absolute;left:-8px;top:-8px;width:16px;height:16px;
        border-radius:50%;
        background:radial-gradient(circle, #FFFFFF, #FF6B00);
        border:2px solid #FFFFFF;
        box-shadow:0 0 12px #FF6B00;
        z-index:10;
        display:flex;align-items:center;justify-content:center;
        font-size:8px;color:#000;font-weight:bold;">↓</div>
    </div>
    <style>
      @keyframes dl-pulse {{
        0%,100% {{ transform:scale(1);   opacity:0.5; }}
        50%     {{ transform:scale(1.6); opacity:0.1; }}
      }}
    </style>
    """
    return folium.Marker(
        location=coords,
        tooltip=f"🎯 DELIVERY: {city}",
        icon=folium.DivIcon(html=html, icon_size=(0, 0), icon_anchor=(0, 0)),
    )


def _add_markers(m, city_coords, start_city, roles=None):
    roles = roles or {start_city: "depot"}
    for city, data in city_coords.items():
        if not data.get("visible", False):
            continue
        role = roles.get(city, None)
        if role is None and city == start_city:
            role = "depot"

        if role == "depot":
            _pulsing_depot_marker(data["coords"], city).add_to(m)
        elif role == "current_location":
            _current_location_marker(data["coords"], city).add_to(m)
        elif role == "pickup":
            _pickup_marker(data["coords"], city).add_to(m)
        elif role == "delivery":
            _delivery_marker(data["coords"], city).add_to(m)
        else:
            # Faint static dot for inactive cities
            html_static = (
                '<div style="width:6px;height:6px;border-radius:50%;'
                'background:rgba(100,150,200,0.35);'
                'box-shadow:0 0 4px rgba(100,150,200,0.4);"></div>'
            )
            folium.Marker(
                location=data["coords"],
                tooltip=city,
                icon=folium.DivIcon(html=html_static, icon_size=(6, 6), icon_anchor=(3, 3)),
            ).add_to(m)


def _add_legend(m, routes):
    if not routes:
        return
    items = ""
    for i, route in enumerate(routes):
        veh = route.get("vehicul", {})
        name = veh.get("nume", f"Vehicle {i+1}") if isinstance(veh, dict) else str(veh)
        driver = veh.get("driver_name", "") if isinstance(veh, dict) else ""
        label = name + (f" · {driver}" if driver else "")
        color = COLORS[i % len(COLORS)]
        items += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">'
            f'<span style="background:{color};width:24px;height:4px;'
            f'display:inline-block;border-radius:2px;box-shadow:0 0 8px {color}80;flex-shrink:0"></span>'
            f'<span style="font-size:12px;color:#E8EEFF">{label}</span></div>'
        )

    html = f"""
    <div style="position:fixed;bottom:30px;right:14px;z-index:9999;
         background:linear-gradient(135deg,rgba(3,5,10,0.92),rgba(8,13,26,0.92));
         padding:14px 18px;border:1px solid rgba(0,255,229,0.5);border-radius:10px;
         box-shadow:0 0 0 1px rgba(0,255,229,0.15),0 8px 40px rgba(0,0,0,0.7),
                    0 0 30px rgba(0,255,229,0.2),inset 0 0 20px rgba(0,255,229,0.05);
         backdrop-filter:blur(12px);min-width:200px;font-family:'Share Tech Mono',monospace;
         overflow:hidden;position:fixed;">
      <div style="position:absolute;top:0;left:0;right:0;height:1px;
           background:linear-gradient(90deg,transparent,#FF003C,transparent);
           animation:legend-scan 3s linear infinite;"></div>
      <div style="font-weight:700;font-size:12px;margin-bottom:10px;
           color:#FF003C;text-transform:uppercase;letter-spacing:2px;
           text-shadow:0 0 12px rgba(0,255,229,0.7);">
        ▸ FLEET STATUS
      </div>
      {items}
      <hr style="margin:10px 0;border:none;border-top:1px dashed rgba(0,255,229,0.25)">
      <div style="font-size:10px;color:#8FA3BD;line-height:2;letter-spacing:0.5px">
        <span style="color:#FF003C;text-shadow:0 0 6px #FF003C">●</span> DEPOT &nbsp;
        <span style="color:#FFA600;text-shadow:0 0 6px #FFA600">▲</span> PICKUP &nbsp;
        <span style="color:#FF6B00;text-shadow:0 0 6px #FF6B00">▼</span> DELIVER &nbsp;
        <span style="color:#00B8FF;text-shadow:0 0 6px #00B8FF">📍</span> CURR.LOC
      </div>
    </div>
    <style>
      @keyframes legend-scan {{
        0%   {{ transform:translateX(-100%); }}
        100% {{ transform:translateX(100%); }}
      }}
    </style>"""
    m.get_root().html.add_child(folium.Element(html))


def _base_map():
    m = folium.Map(
        location=MAP_CENTER,
        zoom_start=DEFAULT_ZOOM,
        tiles=None,
        prefer_canvas=True,
    )
    folium.TileLayer(
        tiles=TILE_URL,
        attr=TILE_ATTR,
        name="Voyager",
        control=False,
    ).add_to(m)
    Fullscreen(position="topright").add_to(m)
    MiniMap(toggle_display=True, position="bottomleft",
            tile_layer=folium.TileLayer(TILE_URL, attr=TILE_ATTR)).add_to(m)
    return m


def draw_initial_map(city_coords, start_city):
    m = _base_map()
    _add_markers(m, city_coords, start_city)
    st_folium(m, height=640, use_container_width=True)


def _add_heatmap(m, routes, city_coords):
    """Overlay an order-density heatmap from all pickup/delivery locations."""
    pts = []
    for route in (routes or []):
        for s in route.get("traseu", []):
            if s.get("tip") in ("pickup", "delivery"):
                c = city_coords.get(s.get("oras"), {}).get("coords")
                if c:
                    pts.append([c[0], c[1], 1.0])  # weight 1 per stop
    if pts:
        HeatMap(pts, radius=25, blur=18, min_opacity=0.3,
                gradient={"0.3":"#FFB700", "0.5":"#FF6B00", "0.7":"#FF003C", "1":"#8B0000"}
                ).add_to(folium.FeatureGroup(name="Order density", show=False).add_to(m))


def draw_route_map(city_coords, start_city, polylines, routes=None):
    m = _base_map()
    roles = _route_roles(routes, start_city)
    _add_markers(m, city_coords, start_city, roles=roles)
    _add_heatmap(m, routes, city_coords)
    _add_legend(m, routes)
    folium.LayerControl(position="topleft", collapsed=True).add_to(m)

    all_coords = []
    for i, poly_data in enumerate(polylines or []):
        if not poly_data:
            continue
        color = COLORS[i % len(COLORS)]

        if isinstance(poly_data, dict):
            pre      = poly_data.get("pre", [])
            outbound = poly_data.get("outbound", [])
            ret      = poly_data.get("return_leg", [])
        else:
            pre, outbound, ret = [], poly_data, []

        if len(pre) > 1:
            # Glow layer (wider, transparent) + dashed line
            folium.PolyLine(locations=pre, color=color, weight=8,
                            opacity=0.18).add_to(m)
            folium.PolyLine(
                locations=pre, color="#A0AEC0", weight=2,
                dash_array="6 8", opacity=0.85,
                tooltip="Current location → Depot",
            ).add_to(m)
            all_coords.extend(pre)

        # When several trucks share the same path (split orders), thick glow
        # halos stack and look like duplicated parallel lines. Keep halos but
        # make them slimmer + dimmer so overlap reads as one stronger line.
        if len(outbound) > 1:
            folium.PolyLine(locations=outbound, color=color,
                            weight=PATH_WEIGHT + 5, opacity=0.08).add_to(m)
            folium.PolyLine(locations=outbound, color=color,
                            weight=PATH_WEIGHT + 2, opacity=0.20).add_to(m)
            # Animated core path
            AntPath(
                locations=outbound, color=color,
                weight=PATH_WEIGHT, delay=ANTPATH_DELAY_MS,
                pulse_color="#FFFFFF",
                tooltip=f"▸ OUTBOUND — Truck {i+1}",
            ).add_to(m)
            all_coords.extend(outbound)

        if len(ret) > 1:
            folium.PolyLine(locations=ret, color=color,
                            weight=PATH_WEIGHT + 2, opacity=0.12).add_to(m)
            AntPath(
                locations=ret, color=color,
                weight=PATH_WEIGHT - 1, delay=ANTPATH_DELAY_MS * 3,
                dash_array=[10, 20], opacity=0.75,
                pulse_color="#FFB700",
                tooltip=f"◂ RETURN — Truck {i+1}",
            ).add_to(m)
            all_coords.extend(ret)

    if all_coords:
        lats = [c[0] for c in all_coords]
        lons = [c[1] for c in all_coords]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(40, 40))

    st_folium(m, height=640, use_container_width=True)


# ─────────────────── SIMULATION MODE ───────────────────
def _haversine_km(a, b):
    R = 6371.0
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    x = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(x), sqrt(1 - x))


def _densify_for_simulation(coords, speed_kmh, base_time, n_points=200):
    """
    Uniformly sample *n_points* along the route (by accumulated distance),
    returning (dense_coords, iso_timestamps).

    With straight-line routing between cities the raw polyline has only a
    handful of vertices — the truck would appear frozen between cities in
    TimestampedGeoJson.  Densifying to ~200 evenly-spaced positions ensures
    smooth animation: the truck advances on almost every slider step.
    """
    if len(coords) < 2:
        return coords, [base_time.isoformat()] * len(coords)

    # ── cumulative distance ──
    cum = [0.0]
    for i in range(1, len(coords)):
        cum.append(cum[-1] + _haversine_km(coords[i - 1], coords[i]))
    total_km = cum[-1]
    if total_km < 0.01:
        return coords, [base_time.isoformat()] * len(coords)

    dense_coords: list = []
    timestamps:   list = []
    seg_idx = 0

    for k in range(n_points):
        d_target = k * total_km / (n_points - 1)
        # advance to the correct segment
        while seg_idx < len(cum) - 2 and cum[seg_idx + 1] < d_target:
            seg_idx += 1
        seg_len = cum[seg_idx + 1] - cum[seg_idx]
        frac = (d_target - cum[seg_idx]) / seg_len if seg_len > 0 else 0.0
        lat = coords[seg_idx][0] + (coords[seg_idx + 1][0] - coords[seg_idx][0]) * frac
        lon = coords[seg_idx][1] + (coords[seg_idx + 1][1] - coords[seg_idx][1]) * frac
        dense_coords.append([lat, lon])
        t = base_time + timedelta(hours=d_target / max(speed_kmh, 1))
        timestamps.append(t.isoformat())

    return dense_coords, timestamps


def _truck_icon_url(color: str, vehicle_number: int = 1) -> str:
    """
    Build an SVG data-URL for a truck marker.
    Each vehicle gets the route colour as a glowing ring around the 🚛 emoji.
    Returns a base64-encoded data: URI safe for Leaflet L.icon({ iconUrl }).
    """
    label = str(vehicle_number)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="42" height="42">'
        # outer glow ring
        f'<circle cx="21" cy="21" r="20" fill="{color}" fill-opacity="0.18" '
        f'        stroke="{color}" stroke-width="2.5"/>'
        # inner filled disc
        f'<circle cx="21" cy="21" r="14" fill="{color}" fill-opacity="0.55"/>'
        # truck emoji
        f'<text x="21" y="27" text-anchor="middle" font-size="16" '
        f'      font-family="Segoe UI Emoji,Apple Color Emoji,Noto Color Emoji,sans-serif">'
        f'&#x1F69B;'   # 🚛 articulated lorry
        f'</text>'
        # small vehicle-number badge (top-right)
        f'<circle cx="34" cy="10" r="7" fill="#08020A" stroke="{color}" stroke-width="1.5"/>'
        f'<text x="34" y="14" text-anchor="middle" font-size="8" '
        f'      font-family="Share Tech Mono,monospace" fill="{color}" font-weight="bold">'
        f'{label}'
        f'</text>'
        f'</svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def draw_simulation_map(city_coords, start_city, polylines, routes=None,
                        sim_speed_kmh=60, sim_start_iso=None):
    """Animated truck simulation along each vehicle's route.
    Uses folium's TimestampedGeoJson which gives built-in play/pause/speed controls.
    """
    m = _base_map()
    roles = _route_roles(routes, start_city)
    _add_markers(m, city_coords, start_city, roles=roles)
    _add_legend(m, routes)

    # Show full static route lines underneath for context (lighter)
    all_coords = []
    for i, poly_data in enumerate(polylines or []):
        if not poly_data:
            continue
        color = COLORS[i % len(COLORS)]
        if isinstance(poly_data, dict):
            pre      = poly_data.get("pre", [])
            outbound = poly_data.get("outbound", [])
            ret      = poly_data.get("return_leg", [])
            # deduplicate junction points (pre ends at depot = outbound[0];
            # outbound ends at last delivery = ret[0])
            full = (pre[:-1] if pre else []) + outbound + (ret[1:] if ret else [])
        else:
            full = poly_data
        if len(full) > 1:
            # Glow halo so the static trail is readable under the moving marker
            folium.PolyLine(locations=full, color=color,
                            weight=8, opacity=0.12).add_to(m)
            folium.PolyLine(locations=full, color=color,
                            weight=4, opacity=0.55,
                            dash_array="8 6").add_to(m)
            all_coords.extend(full)

    # ──── Build TimestampedGeoJson features ────
    base_time = datetime.fromisoformat(sim_start_iso or _today_dispatch_iso())
    features      = []
    max_spacing_s = 120.0   # default 2 min; updated below from actual data
    truck_finals  = []      # (last_pt, last_ts_iso, color, icon_url, veh_name, driver)

    for i, poly_data in enumerate(polylines or []):
        if not poly_data:
            continue
        color = COLORS[i % len(COLORS)]
        veh = routes[i].get("vehicul", {}) if routes and i < len(routes) else {}
        veh_name = veh.get("nume", f"Vehicle {i+1}") if isinstance(veh, dict) else str(veh)
        driver = veh.get("driver_name", "") if isinstance(veh, dict) else ""

        if isinstance(poly_data, dict):
            pre      = poly_data.get("pre", [])
            outbound = poly_data.get("outbound", [])
            ret      = poly_data.get("return_leg", [])
            coords = (pre[:-1] if pre else []) + outbound + (ret[1:] if ret else [])
        else:
            coords = poly_data

        if len(coords) < 2:
            continue

        # Densify to 200 evenly-spaced positions for smooth animation.
        dense_coords, timestamps = _densify_for_simulation(
            coords, sim_speed_kmh, base_time, n_points=200
        )

        # Measure actual timestamp spacing for this truck so we can set
        # duration/period correctly (spacing depends on route length + speed).
        if len(timestamps) >= 2:
            t0 = datetime.fromisoformat(timestamps[0])
            t1 = datetime.fromisoformat(timestamps[1])
            max_spacing_s = max(max_spacing_s, (t1 - t0).total_seconds())

        icon_url = _truck_icon_url(color, vehicle_number=i + 1)

        # Save final position so we can keep the truck visible after it arrives.
        truck_finals.append((dense_coords[-1], timestamps[-1],
                             color, icon_url, veh_name, driver))

        for j, (pt, ts) in enumerate(zip(dense_coords, timestamps)):
            try:
                t_label = datetime.fromisoformat(ts).strftime("%H:%M")
            except Exception:
                t_label = ts
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [pt[1], pt[0]],   # [lon, lat]
                },
                "properties": {
                    "time": ts,
                    "popup": (
                        f"<div style='font-family:Share Tech Mono,monospace;"
                        f"background:#08020A;color:{color};padding:6px 10px;"
                        f"border:1px solid {color};border-radius:4px;font-size:12px;'>"
                        f"<b>🚛 {veh_name}</b>"
                        + (f"<br>👤 {driver}" if driver else "")
                        + f"<br>🕐 {t_label}"
                        f"</div>"
                    ),
                    "icon": "marker",
                    "iconstyle": {
                        "iconUrl":     icon_url,
                        "iconSize":    [42, 42],
                        "iconAnchor":  [21, 21],
                        "popupAnchor": [0, -24],
                    },
                },
            })

    # ── Fix J1: dynamic duration/period based on actual feature spacing ──────
    # duration must be >= spacing so each marker stays visible until the next
    # one appears.  period controls how fast the slider advances.
    duration_s = int(max_spacing_s * 1.2) + 60   # 20 % buffer + 1 min guard
    period_s   = max(30, int(max_spacing_s / 3))  # advance at 1/3 of spacing

    def _s_to_iso(s: int) -> str:
        h, r = divmod(int(s), 3600)
        m, sec = divmod(r, 60)
        result = "PT"
        if h:   result += f"{h}H"
        if m:   result += f"{m}M"
        if sec or result == "PT": result += f"{sec}S"
        return result

    duration_iso = _s_to_iso(duration_s)
    period_iso   = _s_to_iso(period_s)

    # ── Fix J2: keep each truck visible at its final position until the ──────
    # global animation end (prevents trucks from vanishing when their route
    # finishes before the longest route does).
    if truck_finals and features:
        global_end_dt = max(datetime.fromisoformat(tf[1]) for tf in truck_finals)
        step_td = timedelta(seconds=period_s)
        for last_pt, last_ts, t_color, t_icon, t_name, t_driver in truck_finals:
            cur_dt = datetime.fromisoformat(last_ts) + step_td
            while cur_dt <= global_end_dt:
                try:
                    t_label = cur_dt.strftime("%H:%M")
                except Exception:
                    t_label = cur_dt.isoformat()
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [last_pt[1], last_pt[0]],
                    },
                    "properties": {
                        "time": cur_dt.isoformat(),
                        "popup": (
                            f"<div style='font-family:Share Tech Mono,monospace;"
                            f"background:#08020A;color:{t_color};padding:6px 10px;"
                            f"border:1px solid {t_color};border-radius:4px;font-size:12px;'>"
                            f"<b>🚛 {t_name}</b>"
                            + (f"<br>👤 {t_driver}" if t_driver else "")
                            + f"<br>🕐 {t_label} &nbsp;&#10003; Arrived"
                            f"</div>"
                        ),
                        "icon": "marker",
                        "iconstyle": {
                            "iconUrl":     t_icon,
                            "iconSize":    [42, 42],
                            "iconAnchor":  [21, 21],
                            "popupAnchor": [0, -24],
                        },
                    },
                })
                cur_dt += step_td

    if features:
        TimestampedGeoJson(
            data={"type": "FeatureCollection", "features": features},
            period=period_iso,
            duration=duration_iso,
            transition_time=150,
            auto_play=True,
            loop=True,
            add_last_point=True,
            date_options="HH:mm DD-MM",
            time_slider_drag_update=True,
        ).add_to(m)

        # ── Style the timeline control bar & hide the confusing "0fps" display ──
        # The fps counter shows rendering FPS (0 when paused) which looks broken.
        sim_css = folium.Element("""
        <style>
        /* Timeline control bar — match dark cyberpunk theme */
        .leaflet-timeline-controls {
            background: rgba(3,5,10,0.92) !important;
            border: 1px solid rgba(255,0,60,0.45) !important;
            border-radius: 8px !important;
            box-shadow: 0 0 20px rgba(255,0,60,0.15) !important;
            padding: 6px 10px !important;
            font-family: 'Share Tech Mono', monospace !important;
            color: #FF003C !important;
        }
        /* Hide the fps counter — it shows "0fps" when paused, confusing users */
        .leaflet-timeline-controls .fps,
        .leaflet-timeline-controls output {
            display: none !important;
        }
        /* Style the play/pause/step buttons */
        .leaflet-timeline-controls button {
            background: rgba(255,0,60,0.15) !important;
            border: 1px solid rgba(255,0,60,0.4) !important;
            color: #FF003C !important;
            border-radius: 4px !important;
            margin: 0 2px !important;
        }
        .leaflet-timeline-controls button:hover {
            background: rgba(255,0,60,0.4) !important;
        }
        /* Style the time slider */
        .leaflet-timeline-controls input[type=range] {
            accent-color: #FF003C;
        }
        </style>
        """)
        m.get_root().html.add_child(sim_css)

    if all_coords:
        lats = [c[0] for c in all_coords]
        lons = [c[1] for c in all_coords]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(40, 40))

    st_folium(m, height=720, use_container_width=True)


# ─────────────────── 3D MODE (deck.gl via pydeck) ───────────────────
# Hex color → [R, G, B] for pydeck
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i+2], 16) for i in (0, 2, 4)]

COLORS_RGB = [_hex_to_rgb(c) for c in COLORS]


def draw_route_map_3d(city_coords, start_city, polylines, routes=None, pitch=55, bearing=0):
    """3D map using deck.gl PathLayer + ColumnLayer for cities. Dark CARTO base."""
    roles = _route_roles(routes, start_city)

    # ── PathLayer: 3D animated routes ──
    paths_data = []
    bounds_lats, bounds_lons = [], []
    for i, poly_data in enumerate(polylines or []):
        if not poly_data:
            continue
        color = COLORS_RGB[i % len(COLORS_RGB)]
        if isinstance(poly_data, dict):
            pre      = poly_data.get("pre", [])
            outbound = poly_data.get("outbound", [])
            ret      = poly_data.get("return_leg", [])
            full = (pre[:-1] if pre else []) + outbound + (ret[1:] if ret else [])
        else:
            full = poly_data
        if len(full) < 2:
            continue
        # deck.gl path expects [lon, lat] OR [lon, lat, elev]; elevate slightly per vehicle
        elev = 500 + i * 800
        path = [[c[1], c[0], elev] for c in full]
        veh = routes[i].get("vehicul", {}) if routes and i < len(routes) else {}
        veh_name = veh.get("nume", f"Vehicle {i+1}") if isinstance(veh, dict) else str(veh)
        driver = veh.get("driver_name", "") if isinstance(veh, dict) else ""
        paths_data.append({
            "path":  path,
            "color": color + [220],
            "name":  veh_name + (f" — {driver}" if driver else ""),
        })
        bounds_lats.extend([c[0] for c in full])
        bounds_lons.extend([c[1] for c in full])

    path_layer = pdk.Layer(
        "PathLayer",
        data=paths_data,
        get_path="path",
        get_color="color",
        width_min_pixels=4,
        get_width=6,
        rounded=True,
        billboard=True,
        pickable=True,
    )

    # ── ColumnLayer for cities (3D extrusion) ──
    columns_data = []
    for city, role in roles.items():
        if city not in city_coords:
            continue
        c = city_coords[city]["coords"]
        if role == "depot":
            color, height = [255, 0, 60, 230],   60000   # tall vivid red
        elif role == "pickup":
            color, height = [255, 107, 0, 220],  30000   # orange
        elif role == "delivery":
            color, height = [255, 23, 68, 220],  35000   # crimson
        else:
            continue
        columns_data.append({
            "position": [c[1], c[0]],
            "color":    color,
            "elevation": height,
            "name":     f"{role.upper()}: {city}",
        })

    column_layer = pdk.Layer(
        "ColumnLayer",
        data=columns_data,
        get_position="position",
        get_elevation="elevation",
        elevation_scale=1,
        radius=4500,
        get_fill_color="color",
        pickable=True,
        extruded=True,
        auto_highlight=True,
    )

    # ── Glow rings around active cities (ScatterplotLayer) ──
    rings_data = [{"position": d["position"], "color": d["color"][:3] + [80]} for d in columns_data]
    rings_layer = pdk.Layer(
        "ScatterplotLayer",
        data=rings_data,
        get_position="position",
        get_radius=8000,
        get_fill_color="color",
        radius_min_pixels=15,
        pickable=False,
        stroked=False,
        filled=True,
    )

    # ── HexagonLayer for order-density 3D heatmap ──
    hex_data = []
    for city, role in roles.items():
        if role in ("pickup", "delivery") and city in city_coords:
            c = city_coords[city]["coords"]
            hex_data.append({"position": [c[1], c[0]]})

    hex_layer = pdk.Layer(
        "HexagonLayer",
        data=hex_data,
        get_position="position",
        radius=20000,
        elevation_scale=600,
        elevation_range=[0, 50000],
        extruded=True,
        coverage=0.85,
        color_range=[
            [255, 183, 0, 100],
            [255, 107, 0, 150],
            [255, 0, 60, 200],
            [139, 0, 0, 240],
        ],
        pickable=False,
    ) if hex_data else None

    # ── View state: centred on routes, with pitch for 3D effect ──
    # Adapt zoom to actual route span so the map fits regardless of how
    # spread out the cities are.
    if bounds_lats:
        ctr_lat = (min(bounds_lats) + max(bounds_lats)) / 2
        ctr_lon = (min(bounds_lons) + max(bounds_lons)) / 2
        span = max(max(bounds_lats) - min(bounds_lats),
                   max(bounds_lons) - min(bounds_lons))
        # Rough heuristic: tighter span → higher zoom
        if   span < 1.0:  zoom = 8
        elif span < 2.5:  zoom = 7
        elif span < 5.0:  zoom = 6.2
        elif span < 10.0: zoom = 5.5
        else:             zoom = 5
    else:
        ctr_lat, ctr_lon, zoom = 45.9432, 24.9668, 6

    view_state = pdk.ViewState(
        latitude=ctr_lat,
        longitude=ctr_lon,
        zoom=zoom,
        pitch=pitch,
        bearing=bearing,
    )

    layers = [l for l in [hex_layer, rings_layer, column_layer, path_layer] if l is not None]

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="dark",  # CARTO dark — no Mapbox token needed
        tooltip={
            "html": "<b>{name}</b>",
            "style": {
                "backgroundColor": "rgba(8,2,10,0.95)",
                "color": "#FF003C",
                "border": "1px solid #FF003C",
                "borderRadius": "4px",
                "fontFamily": "Share Tech Mono, monospace",
                "padding": "8px",
            },
        },
    )
    st.pydeck_chart(deck, use_container_width=True, height=700)
