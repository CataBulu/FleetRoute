import streamlit as st
try:
    from dotenv import load_dotenv
    load_dotenv()   # reads .env from current folder if present
except ImportError:
    pass
from vrp_solver import solve_vrp, compare_algorithms
from map_view import draw_initial_map, draw_route_map, draw_simulation_map, draw_route_map_3d
from table_view import draw_table
from dashboard import (
    render_alerts_panel, render_co2_summary, render_driver_workload,
    render_cost_breakdown, render_gantt_chart, render_customer_notifications,
    render_journey_timeline,
)
import json

# constants
DEFAULT_VEHICLE_NAME = "Truck"
DEFAULT_VEHICLE_CAPACITY_KG = 25000
VEHICLE_CAPACITY_STEP_KG = 100
DEFAULT_VEHICLE_COUNT = 1
DEFAULT_ORDER_DEMAND_KG = 1000
DEFAULT_TIME_LIMIT_H = 24
DEFAULT_FUEL_L100KM = 30.0

# Romanian HGV tonnage limits (OUG 195/2002, HG 1391/2006)
# Maximum authorised mass (MAM) by number of axles:
#   2-axle rigid:  18 000 kg   3-axle rigid:  26 000 kg
#   4-axle rigid:  32 000 kg   5-axle semi:   40 000 kg  ← standard legal max
# Exceptional transport (> 40 t) requires a special ARR permit.
MAX_VEHICLE_CAPACITY_KG = 40_000   # 40 t — hard cap without ARR exceptional permit
CAPACITY_HELP_TEXT = (
    "Maximum authorised mass (Romania OUG 195/2002):\n"
    "• 2-axle rigid truck → 18 000 kg\n"
    "• 3-axle rigid truck → 26 000 kg\n"
    "• 4-axle rigid truck → 32 000 kg\n"
    "• 5-axle semi-trailer → 40 000 kg  ← legal maximum without special permit\n"
    "Vehicles > 40 000 kg require an exceptional-transport permit from ARR."
)

def load_coordinates(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

st.set_page_config(
    page_title="Delivery Route Optimization",
    layout="wide",
    page_icon="🚚",
    initial_sidebar_state="expanded",
)

# ─────────────── Custom theme & animations (ULTRA DARK + NEON) ───────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Inter:wght@300;400;500;600&family=Share+Tech+Mono&display=swap');

:root {
    --neon-red:   #FF003C;
    --neon-amber:   #FF6B00;
    --neon-purple: #8B0000;
    --neon-yellow: #FFB700;
    --neon-green:  #00FF88;
    --bg-void:     #08020A;
    --bg-panel:    rgba(8, 13, 26, 0.85);
    --text-soft:   #D6E2F0;
    --text-dim:    #8FA3BD;
}

/* ──── Background with embedded animated grid + nebula glows ──── */
.stApp {
    background-color: #08020A;
    background-image:
        linear-gradient(rgba(255,0,60,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,0,60,0.035) 1px, transparent 1px),
        radial-gradient(ellipse at 20% 10%, rgba(255,0,60,0.10) 0%, transparent 45%),
        radial-gradient(ellipse at 80% 90%, rgba(255,107,0,0.08) 0%, transparent 45%),
        radial-gradient(ellipse at 50% 50%, rgba(139,0,0,0.05) 0%, transparent 60%);
    background-size: 60px 60px, 60px 60px, 100% 100%, 100% 100%, 100% 100%;
    animation: bg-drift 30s linear infinite;
    font-family: 'Inter', sans-serif;
    color: #D6E2F0;
}
@keyframes bg-drift {
    0%   { background-position: 0 0, 0 0, 0% 0%, 100% 100%, 50% 50%; }
    100% { background-position: 60px 60px, 60px 60px, 0% 0%, 100% 100%, 50% 50%; }
}
/* Grid moved INTO .stApp background to avoid overlay covering content */

/* ──── Title — glitch + chromatic aberration ──── */
h1 {
    font-family: 'Orbitron', sans-serif !important;
    font-weight: 900 !important;
    font-size: 3rem !important;
    background: linear-gradient(90deg, #FF003C 0%, #8B0000 33%, #FF6B00 66%, #FF003C 100%);
    background-size: 300% 100%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: holo-shift 4s ease-in-out infinite, title-glitch 7s steps(1) infinite;
    letter-spacing: 3px;
    text-transform: uppercase;
    position: relative;
    filter: drop-shadow(0 0 25px rgba(255,0,60,0.45));
}
@keyframes holo-shift {
    0%, 100% { background-position: 0% 50%; }
    50%      { background-position: 100% 50%; }
}
@keyframes title-glitch {
    0%, 90%, 100% { transform: translate(0); }
    92%           { transform: translate(-2px, 1px); filter: drop-shadow(2px 0 0 #FF6B00) drop-shadow(-2px 0 0 #FF003C); }
    94%           { transform: translate(2px, -1px); }
    96%           { transform: translate(-1px, 0); filter: drop-shadow(0 0 25px rgba(255,0,60,0.45)); }
}

/* ──── Subheaders ──── */
h2, h3 {
    color: var(--neon-red) !important;
    font-family: 'Orbitron', sans-serif !important;
    text-shadow: 0 0 12px rgba(255,0,60,0.6), 0 0 25px rgba(255,0,60,0.25);
    letter-spacing: 1px;
    text-transform: uppercase;
    position: relative;
    padding-left: 14px;
}
h2::before, h3::before {
    content: '';
    position: absolute;
    left: 0; top: 50%;
    transform: translateY(-50%);
    width: 4px; height: 70%;
    background: linear-gradient(180deg, var(--neon-red), var(--neon-amber));
    border-radius: 2px;
    box-shadow: 0 0 10px var(--neon-red);
    animation: pillar-pulse 2s ease-in-out infinite;
}
@keyframes pillar-pulse {
    0%, 100% { box-shadow: 0 0 10px var(--neon-red); opacity: 1; }
    50%      { box-shadow: 0 0 20px var(--neon-amber), 0 0 30px var(--neon-red); opacity: 0.7; }
}

/* ──── Sidebar — animated border ──── */
[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, rgba(21,6,10,0.95) 0%, rgba(3,5,10,0.98) 100%) !important;
    border-right: 1px solid rgba(255,0,60,0.3);
    box-shadow: 4px 0 30px rgba(255,0,60,0.08), inset -1px 0 0 rgba(255,0,60,0.15);
    position: relative;
}
[data-testid="stSidebar"]::after {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 1px; height: 100%;
    background: linear-gradient(180deg, transparent, var(--neon-red), transparent);
    animation: sidebar-scan 4s linear infinite;
}
@keyframes sidebar-scan {
    0%   { transform: translateY(-100%); opacity: 0; }
    50%  { opacity: 1; }
    100% { transform: translateY(100%); opacity: 0; }
}
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: var(--neon-yellow) !important;
    text-shadow: 0 0 10px rgba(255,183,0,0.5);
}

/* ──── Buttons — neon-edge with rotating gradient border ──── */
.stButton > button {
    background: linear-gradient(135deg, rgba(255,0,60,0.15), rgba(139,0,0,0.15)) !important;
    color: var(--neon-red) !important;
    border: 1px solid var(--neon-red) !important;
    font-weight: 700 !important;
    letter-spacing: 1px;
    border-radius: 6px !important;
    box-shadow:
        0 0 0 0 rgba(255,0,60,0),
        inset 0 0 15px rgba(255,0,60,0.1);
    transition: all 0.3s cubic-bezier(.2,.9,.3,1.4);
    text-transform: uppercase;
    font-size: 0.82rem !important;
    font-family: 'Share Tech Mono', monospace !important;
    position: relative;
    overflow: hidden;
}
.stButton > button::before {
    content: '';
    position: absolute;
    top: 50%; left: 50%;
    width: 0; height: 0;
    background: radial-gradient(circle, var(--neon-red), transparent 70%);
    transform: translate(-50%, -50%);
    border-radius: 50%;
    transition: width 0.5s ease, height 0.5s ease;
    opacity: 0.4;
    z-index: 0;
}
.stButton > button:hover::before {
    width: 300px; height: 300px;
}
.stButton > button:hover {
    color: var(--bg-void) !important;
    background: linear-gradient(135deg, var(--neon-red), var(--neon-purple)) !important;
    border-color: var(--neon-red) !important;
    transform: translateY(-2px);
    box-shadow:
        0 0 25px rgba(255,0,60,0.7),
        0 0 50px rgba(139,0,0,0.4),
        inset 0 0 20px rgba(255,255,255,0.2);
}
.stButton > button:active {
    transform: translateY(0) scale(0.97);
}

/* ──── Download buttons — pink/purple variant ──── */
.stDownloadButton > button {
    background: linear-gradient(135deg, rgba(255,107,0,0.2), rgba(139,0,0,0.2)) !important;
    color: var(--neon-amber) !important;
    border: 1px solid var(--neon-amber) !important;
    border-radius: 6px !important;
    font-weight: 700 !important;
    font-family: 'Share Tech Mono', monospace !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 0.72rem !important;
    white-space: nowrap;
    padding: 8px 6px !important;
    transition: all 0.3s ease;
    box-shadow: inset 0 0 15px rgba(255,107,0,0.1);
}
.stDownloadButton > button:hover {
    color: var(--bg-void) !important;
    background: linear-gradient(135deg, var(--neon-amber), var(--neon-purple)) !important;
    transform: translateY(-2px);
    box-shadow: 0 0 25px rgba(255,107,0,0.7), 0 0 50px rgba(139,0,0,0.3);
}

/* ──── Inputs — glassmorphism with neon focus ──── */
.stTextInput input, .stNumberInput input, .stSelectbox > div > div {
    background: rgba(21,6,10,0.7) !important;
    border: 1px solid rgba(255,0,60,0.3) !important;
    color: var(--text-soft) !important;
    border-radius: 4px !important;
    transition: all 0.2s ease;
    font-family: 'Share Tech Mono', monospace !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: var(--neon-red) !important;
    box-shadow: 0 0 0 2px rgba(255,0,60,0.2), 0 0 20px rgba(255,0,60,0.3) !important;
    background: rgba(255,0,60,0.05) !important;
}

/* ──── Dataframes ──── */
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 0 30px rgba(255,0,60,0.08), inset 0 0 0 1px rgba(255,0,60,0.2);
    background: rgba(21,6,10,0.5);
}

/* ──── Alerts ──── */
.stAlert {
    border-radius: 6px !important;
    border-left: 3px solid var(--neon-red) !important;
    background: rgba(21,6,10,0.7) !important;
    backdrop-filter: blur(10px);
    box-shadow: 0 0 20px rgba(255,0,60,0.1);
    animation: alert-glow 3s ease-in-out infinite;
}
@keyframes alert-glow {
    0%, 100% { box-shadow: 0 0 20px rgba(255,0,60,0.1); }
    50%      { box-shadow: 0 0 30px rgba(255,0,60,0.25); }
}

/* ──── Radio & Checkbox ──── */
.stRadio > div, .stCheckbox > label {
    color: var(--text-soft) !important;
}
.stRadio label:hover {
    color: var(--neon-red) !important;
    text-shadow: 0 0 5px var(--neon-red);
}

/* ──── Expander ──── */
.streamlit-expanderHeader {
    background: rgba(21,6,10,0.7) !important;
    border-radius: 6px !important;
    border: 1px solid rgba(255,0,60,0.25) !important;
}
.streamlit-expanderHeader:hover {
    border-color: var(--neon-red) !important;
    box-shadow: 0 0 15px rgba(255,0,60,0.2);
}

/* ──── Headline strip ──── */
.headline-strip {
    margin-top: -8px;
    margin-bottom: 28px;
    padding: 10px 18px;
    background:
        linear-gradient(90deg, rgba(255,0,60,0.12) 0%, rgba(139,0,0,0.08) 40%, transparent 100%);
    border-left: 3px solid var(--neon-red);
    border-right: 1px solid rgba(139,0,0,0.2);
    border-radius: 0 8px 8px 0;
    font-size: 0.95rem;
    color: #8FA3BD;
    letter-spacing: 0.5px;
    font-family: 'Share Tech Mono', monospace;
    position: relative;
    overflow: hidden;
}
.headline-strip::after {
    content: '';
    position: absolute;
    top: 0; left: -100%;
    width: 50%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,0,60,0.15), transparent);
    animation: strip-sweep 4s linear infinite;
}
@keyframes strip-sweep {
    0%   { left: -100%; }
    100% { left: 200%; }
}
.headline-strip .pulse-dot {
    display: inline-block;
    width: 10px; height: 10px;
    background: var(--neon-green);
    border-radius: 50%;
    margin-right: 10px;
    animation: pulse-dot 1.2s ease-in-out infinite;
    box-shadow: 0 0 12px var(--neon-green);
}
@keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1);   box-shadow: 0 0 12px var(--neon-green); }
    50%      { opacity: 0.4; transform: scale(1.5); box-shadow: 0 0 25px var(--neon-green); }
}

/* Tabs — neon-styled segmented control */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: transparent;
    border-bottom: 1px solid rgba(255,0,60,0.2);
}
.stTabs [data-baseweb="tab"] {
    background: rgba(21,6,10,0.5) !important;
    color: var(--text-dim) !important;
    border: 1px solid rgba(255,0,60,0.2) !important;
    border-radius: 6px 6px 0 0 !important;
    padding: 8px 16px !important;
    font-family: 'Share Tech Mono', monospace !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 0.75rem !important;
    transition: all 0.2s ease;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--neon-amber) !important;
    border-color: var(--neon-amber) !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(255,0,60,0.3), rgba(139,0,0,0.3)) !important;
    color: var(--neon-red) !important;
    border-color: var(--neon-red) !important;
    box-shadow: 0 0 15px rgba(255,0,60,0.4), inset 0 0 10px rgba(255,0,60,0.1);
}

/* Progress bars — red glow */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, var(--neon-amber), var(--neon-red)) !important;
    box-shadow: 0 0 8px rgba(255,0,60,0.5);
}

/* KPI metric cards — neon bordered panels */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(21,6,10,0.7), rgba(8,2,10,0.85)) !important;
    border: 1px solid rgba(255,0,60,0.35);
    border-radius: 10px;
    padding: 14px 18px !important;
    box-shadow: 0 0 20px rgba(255,0,60,0.08), inset 0 0 30px rgba(255,0,60,0.04);
    transition: all 0.3s ease;
}
[data-testid="stMetric"]:hover {
    border-color: var(--neon-red);
    box-shadow: 0 0 30px rgba(255,0,60,0.25), inset 0 0 30px rgba(255,0,60,0.08);
    transform: translateY(-2px);
}
[data-testid="stMetricValue"] {
    color: var(--neon-red) !important;
    font-family: 'Orbitron', sans-serif !important;
    font-size: 1.8rem !important;
    text-shadow: 0 0 12px rgba(255,0,60,0.6);
}
[data-testid="stMetricLabel"] {
    color: var(--neon-amber) !important;
    font-family: 'Share Tech Mono', monospace !important;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 0.7rem !important;
}

/* Map container — neon bezel */
[data-testid="stIFrame"] {
    border-radius: 12px;
    box-shadow:
        0 0 0 1px rgba(255,0,60,0.4),
        0 0 40px rgba(255,0,60,0.15),
        0 0 80px rgba(139,0,0,0.08);
    overflow: hidden;
    animation: map-bezel-pulse 4s ease-in-out infinite;
}
@keyframes map-bezel-pulse {
    0%, 100% { box-shadow: 0 0 0 1px rgba(255,0,60,0.4), 0 0 40px rgba(255,0,60,0.15); }
    50%      { box-shadow: 0 0 0 1px rgba(255,107,0,0.4), 0 0 50px rgba(255,107,0,0.18); }
}

/* Markdown bold — neon highlights */
strong {
    color: var(--neon-red);
    text-shadow: 0 0 4px rgba(255,0,60,0.4);
}

/* ── Hide Streamlit chrome (footer, menu, deploy) ── */
footer { visibility: hidden !important; }
#MainMenu { visibility: hidden !important; }
.stDeployButton { display: none !important; }
[data-testid="stDecoration"]  { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }

/* Make the top header bar transparent & zero-height so it doesn't show
   but stays IN the DOM — this is critical because the sidebar
   collapse/expand toggle (collapsedControl) is a child of the header
   in some Streamlit builds and needs its parent present to position correctly. */
header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
    box-shadow: none !important;
    min-height: 0 !important;
    height: 0 !important;
    padding: 0 !important;
    overflow: visible !important;   /* let collapsedControl escape the 0-height box */
}

/* Hide all header children EXCEPT the sidebar toggle */
header[data-testid="stHeader"] > *:not([data-testid="collapsedControl"]),
[data-testid="stToolbar"],
[data-testid="stToolbarActions"] {
    visibility: hidden !important;
    pointer-events: none !important;
}

/* Sidebar expand button — pin it in the viewport so it's always reachable
   even when the header has zero height (button would otherwise be at y<0) */
[data-testid="stExpandSidebarButton"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] {
    position:   fixed      !important;
    top:        10px       !important;
    left:       10px       !important;
    display:    flex       !important;
    visibility: visible    !important;
    opacity:    1          !important;
    z-index:    999999     !important;
    pointer-events: auto   !important;
    background: rgba(255,0,60,0.15) !important;
    border: 1px solid rgba(255,0,60,0.5) !important;
    border-radius: 6px !important;
}

/* Tighten top spacing now that header is zero-height */
.block-container { padding-top: 1.5rem !important; }

/* Scrollbar — neon */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: #08020A; }
::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--neon-red), var(--neon-purple));
    border-radius: 10px;
    box-shadow: 0 0 10px rgba(255,0,60,0.4);
}
::-webkit-scrollbar-thumb:hover { background: linear-gradient(180deg, var(--neon-amber), var(--neon-yellow)); }

</style>
""", unsafe_allow_html=True)

# session state
for key, default in [
    ("vehicle_profiles", []),
    ("edit_vehicle_index", -1),
    ("requests", []),
    ("edit_index", -1),
    ("last_routes", []),
    ("last_cost", 0),
    ("last_polylines", []),
    ("routes_generated", False),
    ("allow_split", True),
    ("compare_results", None),
    ("simulation_mode", False),
    ("sim_speed", 60),
    ("map_3d", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# data
city_coords = load_coordinates("coords.json")
cities = [c for c, v in city_coords.items() if v.get("visible", False)]
placeholder = "Select from the list or type"
cities_placeholder = [placeholder] + cities

# depot
selected_hq = st.sidebar.selectbox("Depot", options=cities_placeholder, index=0, key="hq_select")
start_city = None if selected_hq == placeholder else selected_hq

# ─────────────────── Fleet sidebar ───────────────────
st.sidebar.header("🚚 Fleet configuration")
st.sidebar.info("All freight vehicles in the fleet are considered, according to European legislation, to be equipped with a tachograph.")

with st.sidebar.form("fleet_form", clear_on_submit=False):
    idx = st.session_state.edit_vehicle_index
    if idx != -1 and len(st.session_state.vehicle_profiles) > idx:
        vdata = st.session_state.vehicle_profiles[idx]
        v_name   = st.text_input("Vehicle name", vdata['nume'])
        v_driver = st.text_input("Driver name", vdata.get('driver_name', ''))
        v_cap    = st.number_input(
            "Capacity (kg)", min_value=1, max_value=MAX_VEHICLE_CAPACITY_KG,
            value=min(int(vdata['capacitate']), MAX_VEHICLE_CAPACITY_KG),
            step=VEHICLE_CAPACITY_STEP_KG,
            help=CAPACITY_HELP_TEXT,
        )
        v_fuel   = st.number_input("Fuel consumption (L/100km)", min_value=1.0, value=float(vdata.get('fuel_l100km', DEFAULT_FUEL_L100KM)), step=0.5)
        v_ech    = st.checkbox("Crew of 2 drivers?", value=vdata.get('echipaj', False))
        v_count  = st.number_input("Quantity (units in fleet)", min_value=1, value=int(vdata['numar']), step=1)
        existing_home = vdata.get('home_city')
        home_idx = cities_placeholder.index(existing_home) if existing_home and existing_home in cities_placeholder else 0
        v_home   = st.selectbox("Current location (optional)", options=cities_placeholder, index=home_idx)
        label = "Save changes"
        cancel = st.form_submit_button("Cancel edit")
        if cancel:
            st.session_state.edit_vehicle_index = -1
            st.session_state.routes_generated = False
            st.rerun()
    else:
        v_name   = st.text_input("Vehicle name", DEFAULT_VEHICLE_NAME)
        v_driver = st.text_input("Driver name", "")
        v_cap    = st.number_input(
            "Capacity (kg)", min_value=1, max_value=MAX_VEHICLE_CAPACITY_KG,
            value=DEFAULT_VEHICLE_CAPACITY_KG,
            step=VEHICLE_CAPACITY_STEP_KG,
            help=CAPACITY_HELP_TEXT,
        )
        v_fuel   = st.number_input("Fuel consumption (L/100km)", min_value=1.0, value=DEFAULT_FUEL_L100KM, step=0.5)
        v_ech    = st.checkbox("Crew of 2 drivers?")
        v_home   = st.selectbox("Current location (optional)", options=cities_placeholder, index=0)
        v_count  = st.number_input("Quantity (units in fleet)", min_value=1, value=DEFAULT_VEHICLE_COUNT, step=1)
        label = "Add vehicle"

    save_v = st.form_submit_button(label)
    if save_v:
        vehicul_nou = {
            "nume":        v_name,
            "driver_name": v_driver.strip(),
            "capacitate":  v_cap,
            "fuel_l100km": v_fuel,
            "tahograf":    True,
            "echipaj":     v_ech,
            "numar":       v_count,
            "home_city":   None if v_home == placeholder else v_home,
        }
        if st.session_state.edit_vehicle_index != -1:
            st.session_state.vehicle_profiles[st.session_state.edit_vehicle_index] = vehicul_nou
            st.session_state.edit_vehicle_index = -1
            st.session_state.routes_generated = False
            st.success("Vehicle updated.")
        else:
            st.session_state.vehicle_profiles.append(vehicul_nou)
            st.session_state.routes_generated = False
            st.success(f"Vehicle {v_name} added.")
        st.rerun()

# save/load fleet
c1, c2 = st.sidebar.columns([1, 1])
with c1:
    st.download_button("💾 Save fleet", data=json.dumps(st.session_state.vehicle_profiles, indent=2),
                       file_name="fleet_config.json", mime="application/json", use_container_width=True)
with c2:
    fleet_file = st.file_uploader("Upload fleet config", type="json", key="fleet_upld")
    if fleet_file:
        try:
            loaded = json.load(fleet_file)
            if not isinstance(loaded, list):
                raise ValueError("fleet config must be a JSON list")
            for v in loaded:
                v['tahograf'] = True
                v.setdefault('driver_name', '')
                v.setdefault('fuel_l100km', DEFAULT_FUEL_L100KM)
                v.setdefault('numar', 1)
                v.setdefault('echipaj', False)
                home = v.get('home_city')
                if home and home not in city_coords:
                    v['home_city'] = None  # drop invalid home city
            st.session_state.vehicle_profiles = loaded
            st.sidebar.success("Fleet loaded!")
        except Exception as e:
            st.sidebar.error(f"Invalid fleet JSON: {e}")

if st.session_state.vehicle_profiles:
    st.sidebar.markdown("### 🚚 Current fleet:")
    for i, vp in enumerate(st.session_state.vehicle_profiles):
        c1, c2, c3 = st.sidebar.columns([6, 1.2, 1.2])
        qty    = vp['numar']
        qty_tag = f" ×{qty}" if qty > 1 else ""
        crew   = "Crew 2" if vp.get("echipaj") else ""
        driver = f"Driver: {vp['driver_name']}" if vp.get("driver_name") else ""
        home   = f"From: {vp['home_city']}" if vp.get("home_city") else ""
        tags   = " | ".join(filter(None, ["Tachograph", crew, driver, home]))
        tags   = ("\n   " + tags) if tags else ""
        c1.write(f"{i+1}. **{vp['nume']}**{qty_tag} — {vp['capacitate']} kg{tags}")
        if c2.button("✏️", key=f"editv_{i}"):
            st.session_state.edit_vehicle_index = i
            st.session_state.routes_generated = False
            st.rerun()
        if c3.button("❌", key=f"delv_{i}"):
            st.session_state.vehicle_profiles.pop(i)
            st.session_state.routes_generated = False
            if st.session_state.edit_vehicle_index == i:
                st.session_state.edit_vehicle_index = -1
            elif st.session_state.edit_vehicle_index > i:
                st.session_state.edit_vehicle_index -= 1
            st.rerun()

# ─────────────────── Orders sidebar ───────────────────
st.sidebar.header("📦 Orders (pickup & delivery)")
with st.sidebar.form("request_form", clear_on_submit=False):
    idx = st.session_state.edit_index
    if idx != -1 and len(st.session_state.requests) > idx:
        req      = st.session_state.requests[idx]
        p_idx    = cities_placeholder.index(req['pickup'])   if req['pickup']   in cities_placeholder else 0
        d_idx    = cities_placeholder.index(req['delivery']) if req['delivery'] in cities_placeholder else 0
        pickup   = st.selectbox("Pickup",   cities_placeholder, index=p_idx)
        delivery = st.selectbox("Delivery", cities_placeholder, index=d_idx)
        demand   = st.number_input("Quantity (kg)", min_value=1, value=int(req['demand']), step=VEHICLE_CAPACITY_STEP_KG)
        tl       = st.number_input("Deadline (h)", min_value=1, value=int(req['time_limit_hrs']))
        ep       = st.number_input("Earliest pickup (h)", min_value=0, value=int(req.get('earliest_pickup_hrs', 0)))
        priority = st.checkbox("Priority order ⚡", value=req.get('priority', False))
        labelr   = "Save change"
        cancel   = st.form_submit_button("Cancel edit")
        if cancel:
            st.session_state.edit_index = -1
            st.session_state.routes_generated = False
            st.rerun()
    else:
        pickup   = st.selectbox("Pickup",   cities_placeholder, index=0, key="pickup_req")
        delivery = st.selectbox("Delivery", cities_placeholder, index=0, key="delivery_req")
        demand   = st.number_input("Quantity (kg)", min_value=1, value=DEFAULT_ORDER_DEMAND_KG, step=VEHICLE_CAPACITY_STEP_KG)
        tl       = st.number_input("Deadline (h)", min_value=1, value=DEFAULT_TIME_LIMIT_H)
        ep       = st.number_input("Earliest pickup (h)", min_value=0, value=0)
        priority = st.checkbox("Priority order ⚡", value=False)
        labelr   = "Add order"

    if st.form_submit_button(labelr):
        if pickup == placeholder or delivery == placeholder:
            st.warning("Please select both Pickup and Delivery cities.")
        elif pickup == delivery:
            st.warning("Pickup and Delivery cannot be the same city.")
        elif ep >= tl:
            st.warning(f"Earliest pickup ({ep}h) must be earlier than deadline ({tl}h).")
        else:
            req_nou = {
                "pickup": pickup, "delivery": delivery,
                "demand": demand, "time_limit_hrs": tl,
                "earliest_pickup_hrs": ep, "priority": priority,
            }
            if st.session_state.edit_index != -1:
                st.session_state.requests[st.session_state.edit_index] = req_nou
                st.session_state.edit_index = -1
                st.session_state.routes_generated = False
                st.success("Order modified.")
            else:
                st.session_state.requests.append(req_nou)
                st.session_state.routes_generated = False
                st.success("Order added.")
            st.rerun()

# ── Divisible-load switch (OUTSIDE the form so it reacts live) ──
# Auto-enabled when any order exceeds the largest vehicle's capacity.
_max_cap = max([v['capacitate'] for v in st.session_state.vehicle_profiles], default=0)
_any_oversize = any((r.get('demand', 0) > _max_cap) for r in st.session_state.requests)
if _any_oversize:
    # Initialise sticky widget key on first appearance so the default is "on"
    if "user_allow_split" not in st.session_state:
        st.session_state["user_allow_split"] = True
    st.sidebar.checkbox(
        "✂️ Allow load splitting (oversized order detected)",
        key="user_allow_split",
        help="Splits a load larger than the biggest truck into chunks across multiple trucks.",
    )
    st.session_state.allow_split = st.session_state["user_allow_split"]
else:
    st.session_state.allow_split = False

# save/load orders
c1, c2 = st.sidebar.columns([1, 1])
with c1:
    st.download_button("💾 Save orders", data=json.dumps(st.session_state.requests, indent=2),
                       file_name="orders_config.json", mime="application/json", use_container_width=True)
with c2:
    orders_file = st.file_uploader("Upload orders config", type="json", key="orders_upld")
    if orders_file:
        try:
            loaded = json.load(orders_file)
            if not isinstance(loaded, list):
                raise ValueError("orders config must be a JSON list")
            valid_orders = []
            skipped = 0
            for o in loaded:
                if o.get('pickup') in city_coords and o.get('delivery') in city_coords:
                    o.setdefault('earliest_pickup_hrs', 0)
                    o.setdefault('priority', False)
                    valid_orders.append(o)
                else:
                    skipped += 1
            st.session_state.requests = valid_orders
            if skipped:
                st.sidebar.warning(f"Skipped {skipped} order(s) with unknown cities.")
            else:
                st.sidebar.success("Orders loaded!")
        except Exception as e:
            st.sidebar.error(f"Invalid orders JSON: {e}")

if st.session_state.requests:
    st.sidebar.markdown("### 📦 Active Orders:")
    for i, r in enumerate(st.session_state.requests):
        c1, c2, c3 = st.sidebar.columns([6, 1.2, 1.2])
        prio_tag = " ⚡" if r.get('priority') else ""
        c1.write(f"{i+1}. {r['pickup']} → {r['delivery']} ({r['demand']}kg, {r['time_limit_hrs']}h){prio_tag}")
        if c2.button("✏️", key=f"editr_{i}"):
            st.session_state.edit_index = i
            st.session_state.routes_generated = False
            st.rerun()
        if c3.button("❌", key=f"delr_{i}"):
            st.session_state.requests.pop(i)
            st.session_state.routes_generated = False
            if st.session_state.edit_index == i:
                st.session_state.edit_index = -1
            elif st.session_state.edit_index > i:
                st.session_state.edit_index -= 1
            st.rerun()

# ─────────────────── Routing mode ───────────────────
st.sidebar.markdown("### Routing mode")
mode = st.sidebar.radio(
    "Select routing mode:",
    options=["Economic", "Fast", "Balanced"],
    format_func=lambda m: {
        "Economic":  "Economic (minimize total distance km)",
        "Fast":      "Fast (minimize total travel time)",
        "Balanced":  "Balanced (50% distance + 50% time)",
    }[m],
    horizontal=False,
)
st.sidebar.markdown("---")

return_to_depot = st.sidebar.checkbox(
    "🏠 Return to depot after deliveries", value=True,
    help="ON: trucks return home after the last delivery. OFF: trucks wait at last delivery (open routing)."
)
import vrp_solver as _vs
_vs.RETURN_TO_DEPOT = return_to_depot

gen_rute = st.sidebar.button("Generate routes", use_container_width=True)
if gen_rute:
    st.session_state.routes_generated = True
    st.session_state.compare_results = None
    st.rerun()

compare_btn = st.sidebar.button("📊 Compare algorithms", use_container_width=True)
if compare_btn:
    st.session_state.compare_results = "pending"
    st.session_state.routes_generated = False
    st.session_state.simulation_mode = False
    st.rerun()

sim_btn = st.sidebar.button("🎬 Simulation playback", use_container_width=True,
                            help="Replay the truck moving along the route in fast-forward")
if sim_btn:
    if st.session_state.last_routes:
        st.session_state.simulation_mode = True
        st.session_state.compare_results = None
        st.rerun()
    else:
        st.sidebar.warning("Generate routes first.")

if st.sidebar.button("Reset", use_container_width=True):
    # Nuclear reset: clear every key except the depot widget so the UI
    # refreshes completely (fixes the bug where orders/comparison persisted).
    _PRESERVE = {"hq_select"}
    for k in list(st.session_state.keys()):
        if k not in _PRESERVE:
            del st.session_state[k]
    # Flag a pending hard-reload so the NEXT script run emits the JS reload
    # BEFORE any cached components paint stale content.
    st.session_state["_pending_reload"] = True
    st.rerun()

# ── Pending hard-reload (consume flag and trigger browser reload) ─────────
if st.session_state.get("_pending_reload"):
    st.session_state["_pending_reload"] = False
    st.components.v1.html(
        "<script>window.parent.location.reload();</script>",
        height=0,
    )
    st.stop()

# ═══════════════════ Main area ═══════════════════
st.title("FleetRoute Optimizer")
st.markdown(
    '<div class="headline-strip">'
    '<span class="pulse-dot"></span>'
    'Multi-vehicle delivery route optimization · EU Regulation 561/2006 compliant · Real-time'
    '</div>',
    unsafe_allow_html=True,
)

if not start_city:
    st.info("Please select Depot first.")
    draw_initial_map(city_coords, None)
    st.stop()

if not st.session_state.requests or not st.session_state.vehicle_profiles:
    st.info("Add at least one vehicle and one order to generate routes.")
    draw_initial_map(city_coords, start_city)
    st.stop()

# split requests if divisible
chunks = []
max_cap = max((v['capacitate'] for v in st.session_state.vehicle_profiles), default=0)
if st.session_state.allow_split:
    for oid, r in enumerate(st.session_state.requests, start=1):
        rem, part = r['demand'], 1
        while rem > 0:
            c = min(rem, max_cap)
            rr = dict(r); rr['demand'] = c; rr['id'] = oid; rr['part'] = part
            chunks.append(rr); rem -= c; part += 1
else:
    for oid, r in enumerate(st.session_state.requests, start=1):
        if r['demand'] > max_cap:
            st.error(f"Order {r['pickup']}→{r['delivery']} ({r['demand']}kg) exceeds max capacity.")
            st.stop()
        rr = dict(r); rr['id'] = oid; chunks.append(rr)

# priority orders first, then tightest deadline
chunks = sorted(chunks, key=lambda x: (not x.get('priority', False), x['time_limit_hrs']))

# expand fleet
profile_expanded = []
for vp in sorted(st.session_state.vehicle_profiles, key=lambda v: v['capacitate']):
    for _ in range(vp['numar']):
        profile_expanded.append(vp)

# ──── Algorithm comparison mode ────
if st.session_state.compare_results == "pending":
    with st.spinner("Running all algorithms… this may take ~60s"):
        results = compare_algorithms(
            start_city=start_city,
            pd_requests=chunks,
            coords=city_coords,
            vehicle_profiles=profile_expanded,
            routing_mode=mode,
            allow_split=st.session_state.allow_split,
        )
    st.session_state.compare_results = results

if st.session_state.compare_results and st.session_state.compare_results != "pending":
    st.subheader("📊 Algorithm Comparison")
    import pandas as pd
    df_cmp = pd.DataFrame(st.session_state.compare_results)
    st.dataframe(df_cmp, use_container_width=True, hide_index=True)
    draw_initial_map(city_coords, start_city)
    st.stop()

# ──── Simulation mode ────
if st.session_state.simulation_mode and st.session_state.last_routes:
    st.subheader("🎬 Live Route Simulation")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        speed = st.slider(
                          "Truck speed (km/h) — controls how fast each km is traversed",
                          min_value=20, max_value=105,  # 105 km/h = EU hardware-limiter cap (Dir. 92/6/CEE)
                          value=min(st.session_state.sim_speed, 105),
                          step=5,
                          key="sim_speed_slider")
        st.session_state.sim_speed = speed
    with c2:
        if st.button("⏹ Exit simulation", use_container_width=True):
            st.session_state.simulation_mode = False
            st.rerun()
    with c3:
        st.metric("Vehicles", len(st.session_state.last_routes))

    st.info("▶ Use the play/pause and speed (×1, ×2, ×5…) controls at the bottom of the map. The truck advances along the planned route in fast-forward.")

    # Voice announcement toggle (feature K)
    voice_on = st.checkbox("🔊 Voice announcements (Web Speech API)", value=False,
                           help="Browser will speak each delivery arrival.")
    if voice_on:
        import json as _json
        deliveries = [s.get("oras") for r in st.session_state.last_routes for s in r.get("traseu", []) if s.get("tip") == "delivery"]
        js = "<script>"
        js += "if ('speechSynthesis' in window) {"
        for i, city in enumerate(deliveries):
            msg = _json.dumps(f"Delivery arrived at {city}")   # safe JS string literal
            js += f"setTimeout(() => {{ const u = new SpeechSynthesisUtterance({msg}); u.rate=1.1; speechSynthesis.speak(u); }}, {i*3000});"
        js += "}</script>"
        st.markdown(js, unsafe_allow_html=True)

    draw_simulation_map(
        city_coords, start_city,
        st.session_state.last_polylines,
        routes=st.session_state.last_routes,
        sim_speed_kmh=speed,
    )
    st.stop()

# ──── Normal route generation ────
if st.session_state.routes_generated:
    with st.spinner("Building routes…"):
        routes, polylines, total_cost, dropped = solve_vrp(
            start_city=start_city,
            pd_requests=chunks,
            coords=city_coords,
            vehicle_profiles=profile_expanded,
            routing_mode=mode,
            allow_split=st.session_state.allow_split,
        )

    st.session_state.last_routes   = routes
    st.session_state.last_polylines = polylines
    st.session_state.last_cost      = total_cost

    # ──── KPI Dashboard (top cards) ────
    if routes:
        total_km = sum(
            float(s.get("distanta", 0) or 0)
            for r in routes for s in r.get("traseu", [])
        )
        # Count UNIQUE delivered orders (a split order counts once, not per chunk)
        delivered_oids = set()
        for r in routes:
            for s in r.get("traseu", []):
                if s.get("tip") == "delivery":
                    oid = s.get("order_id") or s.get("comanda")
                    if oid is not None:
                        delivered_oids.add(oid)
        # also count unique dropped order ids so the two numbers tally to the
        # actual count of distinct customer orders
        dropped_oids = set()
        for d in (dropped or []):
            doid = d.get("id") or d.get("order_id")
            if doid is not None:
                dropped_oids.add(doid)
        # Total unique customer orders (excluding chunks)
        total_unique_input = len(st.session_state.requests)
        delivered_count = len(delivered_oids - dropped_oids) or len(delivered_oids)
        vehicles_used = len(routes)
        avg_km_per_vehicle = total_km / max(vehicles_used, 1)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🚚 Vehicles deployed", vehicles_used)
        k2.metric("📦 Orders delivered",
                  f"{delivered_count} / {total_unique_input}")
        k3.metric("🛣️ Total distance", f"{round(total_km, 1)} km")
        k4.metric("📊 Avg per vehicle", f"{round(avg_km_per_vehicle, 1)} km")

    if dropped:
        st.error(
            f"⚠️ {len(dropped)} order(s) could not be scheduled within the requested deadline "
            "given the available fleet (capacity or time constraints). They were excluded."
        )
        import pandas as pd
        st.dataframe(
            pd.DataFrame([{"Pickup": d.get("pickup"), "Delivery": d.get("delivery"),
                           "Quantity (kg)": d.get("demand"), "Deadline (h)": d.get("time_limit_hrs")}
                          for d in dropped]),
            use_container_width=True, hide_index=True
        )

    # ──── 2D / 3D toggle above map ────
    mc1, mc2, mc3 = st.columns([2, 1, 1])
    with mc1:
        st.markdown("### 🗺️ Route Map")
    with mc2:
        view_mode = st.radio(
            "Map view", ["2D", "3D"],
            horizontal=True, label_visibility="collapsed",
            index=1 if st.session_state.map_3d else 0,
            key="map_view_radio",
        )
        st.session_state.map_3d = (view_mode == "3D")
    with mc3:
        if st.session_state.map_3d:
            pitch = st.slider("Tilt", 0, 75, 55, 5, key="pitch_slider", label_visibility="collapsed")
        else:
            pitch = 0

    if st.session_state.map_3d:
        draw_route_map_3d(city_coords, start_city, polylines, routes=routes, pitch=pitch)
    else:
        st.caption(
            "ℹ️ Routes are drawn as straight-line segments between network nodes "
            "(road geometry is not loaded). Animated arrows show direction of travel."
        )
        draw_route_map(city_coords, start_city, polylines, routes=routes)

    # ──── Extended analytics dashboard (tabbed) ────
    tab_journey, tab_table, tab_alerts, tab_workload, tab_cost, tab_co2, tab_gantt, tab_notif = st.tabs([
        "🛣️ Journey",
        "📋 Routing Table",
        "⚠️ Alerts",
        "👤 Driver Workload",
        "💰 Cost Breakdown",
        "🌍 CO₂",
        "📅 Gantt",
        "✉️ Notifications",
    ])
    with tab_journey:
        render_journey_timeline(routes)
    with tab_table:
        draw_table(st.session_state.last_routes, st.session_state.last_cost,
                   None, dropped=dropped)
    with tab_alerts:
        render_alerts_panel(routes, dropped)
    with tab_workload:
        render_driver_workload(routes)
    with tab_cost:
        render_cost_breakdown(routes, fuel_price=st.session_state.get("fuel_price_input", 7.5))
    with tab_co2:
        render_co2_summary(routes)
    with tab_gantt:
        render_gantt_chart(routes)
    with tab_notif:
        render_customer_notifications(routes)
else:
    draw_initial_map(city_coords, start_city)
