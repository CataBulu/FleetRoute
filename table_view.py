import streamlit as st
import pandas as pd
import json
from io import BytesIO
from fpdf import FPDF

__all__ = ["draw_table"]

# ---- constants (EU Regulation EC 561/2006 & Directive 2002/15) ----
SERVICE_TIME = 2.0                  # h per pickup/delivery (operational)
DRIVER_BREAK_ = 0.75                # 45 min mandatory break after 4.5h driving
BREAK_WINDOW = 4.5                  # h driving before 45-min break is due
SINGLE_DRIVER_DAILY_LIMIT = 9       # h max driving per day, single driver
CREW_DRIVER_DAILY_LIMIT = 18        # h max combined driving, multi-manning (9h x 2)
# Working window from end of last daily rest until next daily rest must start.
# After a REGULAR 11h rest: 13h window (24-11). After a REDUCED 9h rest: 15h (24-9).
APTITUDE_AFTER_NORMAL_REST = 13
APTITUDE_AFTER_REDUCED_REST = 15
CREW_DRIVER_APTITUDE = 21           # multi-manning: 30h cycle - 9h rest
DAILY_REST_NORMAL = 11              # h regular daily rest
DAILY_REST_REDUCED = 9              # h reduced daily rest (max 3x between weekly rests)
MAX_REDUCED_DAILY_RESTS = 3
# Weekly rules
WEEKLY_DRIVE_LIMIT = 56             # h max driving per week
BIWEEKLY_DRIVE_LIMIT = 90           # h max driving across any 2 consecutive weeks
WEEKLY_REST_NORMAL = 45             # h normal weekly rest
WEEKLY_REST_REDUCED = 24            # h reduced weekly rest (max 1 per 2 weeks, needs compensation)
MAX_HOURS_BEFORE_WEEKLY_REST = 6 * 24  # weekly rest must start no later than 6x24h after last one

# ---- Romanian speed limits for HGV > 3.5 t (OUG 195/2002, art. 50) ----
# Used to check each road segment's average speed and flag potential violations.
RO_HGV_SPEED_LOCALITY_KMPH  = 50   # în localități
RO_HGV_SPEED_HIGHWAY_KMPH   = 90   # autostradă (A)
RO_HGV_SPEED_EXPRESS_KMPH   = 80   # drum expres / european (E)
RO_HGV_SPEED_NATIONAL_KMPH  = 70   # drum național / județean
RO_HGV_SPEED_LIMITER_KMPH   = 105  # limitator hardware obligatoriu (Directiva CE 92/6)
RO_HGV_THRESHOLD_TONNES     = 3.5  # masă maximă autorizată de la care se aplică regulile HGV

DECIMALS_KM = 2
TABLE_COL_SPACE = 70

# ---------- helpers ----------
def _fmt_hhmm(x):
    try:
        if x is None or x == "-" or pd.isna(x):
            return "-"
        v = float(x)
        neg = v < 0
        v = abs(v)
        h = int(v)
        m = int(round((v - h) * 60))
        if m == 60:
            h += 1
            m = 0
        return f"{'-' if neg else ''}{h:02d}:{m:02d}"
    except Exception:
        return "-"

def _veh_name(v):
    if isinstance(v, dict):
        name   = v.get("nume", "Vehicle")
        driver = v.get("driver_name", "")
        return f"{name} ({driver})" if driver else name
    return str(v)

def _round_km(x):
    try:
        return round(float(x), DECIMALS_KM)
    except Exception:
        return x

def _driver_limits(veh_dict, last_rest_was_reduced):
    # Returns (max driving hours per day, max working window since last daily rest)
    crew = bool(veh_dict.get("echipaj", False)) if isinstance(veh_dict, dict) else False
    if crew:
        return CREW_DRIVER_DAILY_LIMIT, CREW_DRIVER_APTITUDE
    apt = APTITUDE_AFTER_REDUCED_REST if last_rest_was_reduced else APTITUDE_AFTER_NORMAL_REST
    return SINGLE_DRIVER_DAILY_LIMIT, apt

def _status_flag(slack):
    try:
        if slack is None or slack == "-" or pd.isna(slack):
            return "-"
        return "YES" if float(slack) >= 0 else "NO"
    except Exception:
        return "-"

def _find_delivery_deadline(steps, start_idx, order_id):
    for j in range(start_idx + 1, len(steps)):
        sp = steps[j] or {}
        if sp.get("tip") == "delivery":
            oid = sp.get("order_id", sp.get("comanda", ""))
            if oid == order_id:
                tl = sp.get("time_limit", None)
                if isinstance(tl, (int, float)):
                    return float(tl)
    return None

def _nearest_future_deadline(steps, cur_idx, onboard_deadlines, last_delivery_idx):
    cands = []
    if onboard_deadlines:
        cands.extend([float(v) for v in onboard_deadlines.values() if isinstance(v, (int, float))])
    end_idx = last_delivery_idx if last_delivery_idx != -1 else len(steps) - 1
    for j in range(cur_idx, end_idx + 1):
        sp = steps[j] or {}
        if sp.get("tip") in ("pickup", "delivery"):
            tl = sp.get("time_limit", None)
            if not isinstance(tl, (int, float)) and sp.get("tip") == "pickup":
                tl = _find_delivery_deadline(steps, j, sp.get("order_id", sp.get("comanda", "")))
            if isinstance(tl, (int, float)):
                cands.append(float(tl))
    if not cands:
        return None
    return min(cands)

def _add_row(rows, step_no, veh, descr, city, dist_km, elapsed, time_left, ontime_html,
             drive_time="-", breaks="-", tacho_rem="-", fuel_cost="-", avg_speed="-"):
    rows.append({
        "Step": step_no,
        "Vehicle": veh,
        "Description": descr,
        "City": city,
        "Distance (km)": "-" if dist_km == "-" else _round_km(dist_km),
        "Speed (km/h)": avg_speed,
        "Time elapsed (h)": _fmt_hhmm(elapsed),
        "Drive time (h)": _fmt_hhmm(drive_time) if drive_time != "-" else "-",
        "Breaks": breaks,
        "Tacho remaining (h)": _fmt_hhmm(tacho_rem) if tacho_rem != "-" else "-",
        "Fuel cost (RON)": fuel_cost if fuel_cost == "-" else round(float(fuel_cost), 2),
        "Time left (h)": _fmt_hhmm(time_left) if not isinstance(time_left, str) else time_left,
        "On time?": ontime_html
    })

def _to_latin1(s):
    """Normalize unicode to Latin-1 for fpdf2's default Helvetica.
    Replaces Romanian diacritics with ASCII equivalents."""
    if s is None:
        return ""
    s = str(s)
    repl = {
        "ă":"a","Ă":"A","â":"a","Â":"A","î":"i","Î":"I",
        "ș":"s","Ș":"S","ş":"s","Ş":"S",
        "ț":"t","Ț":"T","ţ":"t","Ţ":"T",
        "—":"-","–":"-","‘":"'","’":"'","“":'"',"”":'"',
        "…":"...","•":"*","→":"->","←":"<-","⚡":"!","⚠":"!",
        "🚚":"","📦":"","🎯":"","🏢":"","✅":"","❌":"",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    # Drop anything still outside latin-1
    return s.encode("latin-1", errors="replace").decode("latin-1").replace("?", "")


def _build_pdf(routes, df_routing, late_rows, fuel_rows):
    """Generate a PDF report and return bytes."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Delivery Route Optimization - Report", ln=True)
    pdf.set_font("Helvetica", "", 9)
    orders_delivered = int(df_routing["Description"].str.match(r"^Arrive order .+ \(delivery\)$").sum())
    pdf.cell(0, 5, f"Vehicles: {len(routes)}   Orders delivered: {orders_delivered}", ln=True)
    pdf.ln(3)

    # ── Route summary ──
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Route Summary", ln=True)
    pdf.set_font("Helvetica", "", 8)
    col_w = [10, 40, 55, 30, 25, 25]
    headers = ["#", "Vehicle", "Description", "City", "Elapsed", "On time?"]
    pdf.set_fill_color(220, 220, 220)
    for w, h in zip(col_w, headers):
        pdf.cell(w, 5, h, border=1, fill=True)
    pdf.ln()
    pdf.set_fill_color(255, 255, 255)
    for _, row in df_routing.iterrows():
        vals = [
            _to_latin1(row.get("Step", "")),
            _to_latin1(row.get("Vehicle", ""))[:22],
            _to_latin1(row.get("Description", ""))[:28],
            _to_latin1(row.get("City", ""))[:18],
            _to_latin1(row.get("Time elapsed (h)", "")),
            _to_latin1(row.get("On time?", "")),
        ]
        for w, v in zip(col_w, vals):
            pdf.cell(w, 4, v, border=1)
        pdf.ln()

    # ── Delays ──
    if late_rows:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Late Deliveries", ln=True)
        pdf.set_font("Helvetica", "", 8)
        for r in late_rows:
            line = f"  Vehicle {r.get('Vehicle')}  Order {r.get('Order')}  Delay: {r.get('Delay (h)')}"
            pdf.cell(0, 5, _to_latin1(line), ln=True)

    # ── Fuel ──
    if fuel_rows:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Fuel Cost Estimate", ln=True)
        pdf.set_font("Helvetica", "", 8)
        for r in fuel_rows:
            line = f"  {r.get('Vehicle')}:  {r.get('Distance (km)')} km  {r.get('Fuel used (L)')} L  {r.get('Cost (RON)')} RON"
            pdf.cell(0, 5, _to_latin1(line), ln=True)
        total = sum(r.get("Cost (RON)", 0) for r in fuel_rows)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, _to_latin1(f"  TOTAL: {round(total, 2)} RON"), ln=True)

    return bytes(pdf.output())


def draw_table(routes, _total_cost, _deprecated_time_limit, dropped=None):
    if not routes:
        st.warning("No routes to display.")
        return

    # ── Romanian HGV Regulations panel ──────────────────────────────────────
    with st.expander("🇷🇴 Romanian HGV Regulations (vehicles > 3.5 t)", expanded=False):
        col_regs, col_equip = st.columns(2)
        with col_regs:
            st.markdown("##### Speed limits (OUG 195/2002, art. 50)")
            st.table(pd.DataFrame({
                "Road type": [
                    "In localities",
                    "Motorway (A)",
                    "Express / European (E) roads",
                    "Other national / county roads",
                ],
                "HGV limit (km/h)": [
                    RO_HGV_SPEED_LOCALITY_KMPH,
                    RO_HGV_SPEED_HIGHWAY_KMPH,
                    RO_HGV_SPEED_EXPRESS_KMPH,
                    RO_HGV_SPEED_NATIONAL_KMPH,
                ],
            }))
            st.caption(
                f"Hardware speed limiter mandatory: **≤ {RO_HGV_SPEED_LIMITER_KMPH} km/h** "
                "(Directive 92/6/CEE, applies to all HGV > 3.5 t)"
            )
        with col_equip:
            st.markdown("##### Mandatory equipment & rules")
            st.markdown(
                "- ✅ **Tachograph** — digital/analogue, records all driving activity "
                  "(all fleet vehicles are modelled with tachograph)\n"
                "- ✅ **Speed limiter** — hardware device, max 105 km/h\n"
                "- ✅ **EU Reg. 561/2006 driving/rest times** — fully modelled in routing table:\n"
                "  - Break ≥ 45 min after 4.5 h driving\n"
                "  - Daily driving ≤ 9 h (extendable to 10 h, max 2×/week)\n"
                "  - Weekly driving ≤ 56 h\n"
                "  - Biweekly driving ≤ 90 h\n"
                "- ⚠️ **Weekend / holiday bans** may apply for vehicles > 7.5 t "
                  "— verify against ARR calendar before dispatching"
            )

    # Read fuel price ONCE at the top so it can be used in the routing table cells
    st.subheader("⛽ Fuel pricing")
    fuel_price = st.number_input(
        "Fuel price (RON/L)", min_value=0.0, value=7.5, step=0.1,
        key="fuel_price_input", help="Updates the Fuel cost column in real-time."
    )

    rows = []
    late = []
    step_no = 1

    biweekly_violations = []

    for r_idx, route in enumerate(routes):
        veh = route.get("vehicul", {"nume": f"Vehicle {r_idx+1}"})
        veh_label = _veh_name(veh)
        steps = route.get("traseu", [])
        if not steps:
            continue

        depot_city = route.get("depot", steps[0].get("oras", ""))
        last_del_idx = max((i for i, p in enumerate(steps) if (p or {}).get("tip") == "delivery"), default=-1)

        # Clocks
        t = 0.0
        since_break = 0.0
        since_rest = 0.0
        since_apt = 0.0
        drive_total = 0.0                # cumulative pure driving time (new)
        breaks_count = 0                 # 45-min breaks taken (new)
        km_total = 0.0                   # cumulative distance for fuel cost
        fuel_l100 = float(veh.get("fuel_l100km", 30)) if isinstance(veh, dict) else 30.0
        cost_so_far = 0.0                # running fuel cost in RON
        # Daily-rest tracking (EU 561/2006 Art. 8)
        reduced_daily_count = 0          # reduced (9h) daily rests since last weekly rest, max 3
        last_rest_was_reduced = False    # determines next working window (15h vs 13h)
        # Weekly-rest tracking
        weekly_drive = 0.0                # h driven since last weekly rest
        weekly_t_start = 0.0              # t when current "driving week" started
        weekly_rest_history = []          # list of (drive_in_week, was_reduced) for past weeks
        reduced_weekly_used_in_cycle = False  # max 1 reduced weekly rest per 2-week cycle

        onboard = {}

        # First row: depart from home or depot
        first_step = steps[0]
        first_tip = first_step.get("tip", "")
        if first_tip == "home_depart":
            first_label = f"Depart current location"
        else:
            first_label = "Depart depot"
        active_deadline = _nearest_future_deadline(steps, 1, onboard, last_del_idx)
        slack0 = None if last_del_idx == -1 else (None if active_deadline is None else (active_deadline - t))
        rest_limit0, _ = _driver_limits(veh, last_rest_was_reduced)
        _add_row(rows, step_no, veh_label, first_label, first_step.get("oras", ""), "-", t,
                 "-" if slack0 is None else slack0,
                 "-" if slack0 is None else _status_flag(slack0),
                 drive_time=0.0, breaks=breaks_count, tacho_rem=rest_limit0,
                 fuel_cost=cost_so_far)
        step_no += 1

        i = 1
        while i < len(steps):
            pas = steps[i] or {}
            tip_pas = pas.get("tip", "")
            city = pas.get("oras", "")
            dist = float(pas.get("distanta", 0) or 0.0)
            dur = float(pas.get("durata", 0) or 0.0)
            oid = pas.get("order_id", pas.get("comanda", ""))

            rest_limit, apt_limit = _driver_limits(veh, last_rest_was_reduced)
            show_time_now = (i <= last_del_idx) if last_del_idx != -1 else True

            while True:
                # ---- Weekly rest (highest priority): EU 561/2006 Art. 8(6) ----
                weekly_drive_exceeded = (weekly_drive + dur) > WEEKLY_DRIVE_LIMIT
                six_day_rule_hit = (t - weekly_t_start) > MAX_HOURS_BEFORE_WEEKLY_REST
                if weekly_drive_exceeded or six_day_rule_hit:
                    can_reduce = not reduced_weekly_used_in_cycle
                    use_reduced = can_reduce  # prefer the shorter rest when permitted
                    rest_len = WEEKLY_REST_REDUCED if use_reduced else WEEKLY_REST_NORMAL
                    # bi-weekly check: drive in (current_week + previous_week) must be <= 90h
                    prev_week_drive = weekly_rest_history[-1][0] if weekly_rest_history else 0.0
                    if (prev_week_drive + weekly_drive) > BIWEEKLY_DRIVE_LIMIT:
                        biweekly_violations.append({
                            "Vehicle": veh_label,
                            "Drive in 2 weeks (h)": _fmt_hhmm(prev_week_drive + weekly_drive),
                            "Limit (h)": f"{BIWEEKLY_DRIVE_LIMIT:02d}:00",
                        })
                    weekly_rest_history.append((weekly_drive, use_reduced))
                    # toggle 2-week cycle
                    if use_reduced:
                        reduced_weekly_used_in_cycle = True
                    else:
                        reduced_weekly_used_in_cycle = False  # cycle resets after a normal rest

                    t += rest_len
                    weekly_drive = 0.0
                    weekly_t_start = t
                    reduced_daily_count = 0
                    last_rest_was_reduced = False  # weekly rest counts as a normal-equivalent reset for window logic
                    since_break = 0.0
                    since_rest = 0.0
                    since_apt = 0.0

                    reason = "weekly drive >56h" if weekly_drive_exceeded else "6-day rule"
                    label = f"Weekly Rest ({rest_len}h, {'reduced' if use_reduced else 'normal'}) — {reason}"
                    active_deadline = _nearest_future_deadline(steps, i, onboard, last_del_idx) if show_time_now else None
                    slack = None if active_deadline is None else (active_deadline - t)
                    rest_limit, apt_limit = _driver_limits(veh, last_rest_was_reduced)
                    _add_row(rows, step_no, veh_label, label, "On Route", "-", t,
                             "-" if (not show_time_now or slack is None) else slack,
                             "-" if (not show_time_now or slack is None) else _status_flag(slack),
                             drive_time=drive_total, breaks=breaks_count, tacho_rem=rest_limit,
                             fuel_cost=cost_so_far)
                    step_no += 1
                    continue

                apt_needed = (since_apt + dur) > apt_limit
                rest_needed = (since_rest + dur) > rest_limit
                break_needed = (since_break + dur) > BREAK_WINDOW

                if apt_needed or rest_needed:
                    # EU 561/2006 Art. 8(4): up to 3 reduced (9h) daily rests between weekly rests
                    use_reduced_daily = reduced_daily_count < MAX_REDUCED_DAILY_RESTS
                    rest_len = DAILY_REST_REDUCED if use_reduced_daily else DAILY_REST_NORMAL
                    if use_reduced_daily:
                        reduced_daily_count += 1
                    last_rest_was_reduced = use_reduced_daily

                    t += rest_len
                    since_break = 0.0
                    since_rest = 0.0
                    since_apt = 0.0

                    cause = "aptitude window reached" if apt_needed else "daily drive limit reached"
                    label = f"Daily Rest ({rest_len}h, {'reduced' if use_reduced_daily else 'normal'}) — {cause}"
                    active_deadline = _nearest_future_deadline(steps, i, onboard, last_del_idx) if show_time_now else None
                    slack = None if active_deadline is None else (active_deadline - t)
                    rest_limit, apt_limit = _driver_limits(veh, last_rest_was_reduced)
                    _add_row(rows, step_no, veh_label, label, "On Route", "-", t,
                             "-" if (not show_time_now or slack is None) else slack,
                             "-" if (not show_time_now or slack is None) else _status_flag(slack),
                             drive_time=drive_total, breaks=breaks_count, tacho_rem=rest_limit,
                             fuel_cost=cost_so_far)
                    step_no += 1
                    continue

                if break_needed:
                    t += DRIVER_BREAK_
                    since_break = 0.0
                    since_apt += DRIVER_BREAK_
                    breaks_count += 1

                    active_deadline = _nearest_future_deadline(steps, i, onboard, last_del_idx) if show_time_now else None
                    slack = None if active_deadline is None else (active_deadline - t)
                    tacho_now = max(0.0, rest_limit - since_rest)
                    _add_row(rows, step_no, veh_label, "Driver Break (45min)", "On Route", "-", t,
                             "-" if (not show_time_now or slack is None) else slack,
                             "-" if (not show_time_now or slack is None) else _status_flag(slack),
                             drive_time=drive_total, breaks=breaks_count, tacho_rem=tacho_now,
                             fuel_cost=cost_so_far)
                    step_no += 1
                    continue

                break

            t += dur
            since_break += dur
            since_rest += dur
            since_apt += dur
            weekly_drive += dur
            drive_total += dur
            km_total += dist
            cost_so_far = km_total * fuel_l100 / 100.0 * fuel_price

            # description
            if tip_pas == "pickup":
                descr = f"Arrive order {oid} (pickup)"
            elif tip_pas == "delivery":
                descr = f"Arrive order {oid} (delivery)"
            elif tip_pas == "intoarcere":
                descr = "Arrive depot"
            elif tip_pas == "arrive_depot":
                descr = "Arrive depot (begin route)"
            elif tip_pas == "plecare":
                descr = "Depart depot"
            else:
                descr = "Transit"

            # at pickup: registers deadline for this order
            if tip_pas == "pickup":
                dl = pas.get("time_limit", None)
                if not isinstance(dl, (int, float)):
                    dl = _find_delivery_deadline(steps, i, oid)
                if isinstance(dl, (int, float)) and oid != "":
                    onboard[oid] = float(dl)

            # computes time left for this row
            time_left_cell = "-"
            ontime_cell = "-"
            if show_time_now:
                active_deadline = _nearest_future_deadline(steps, i, onboard, last_del_idx)
                if active_deadline is not None:
                    slack = active_deadline - t
                    time_left_cell = slack
                    ontime_cell = _status_flag(slack)

            # for delivery row, also checks lateness vs its own deadline
            if tip_pas == "delivery":
                own_dl = pas.get("time_limit", onboard.get(oid, None))
                if isinstance(own_dl, (int, float)):
                    own_slack = own_dl - t
                    if own_slack < 0:
                        late.append({"Vehicle": veh_label, "Order": oid, "Delay (h)": _fmt_hhmm(abs(own_slack))})

            tacho_now = max(0.0, rest_limit - since_rest)
            # Implied average speed for this segment (used for HGV speed-limit check)
            avg_speed = round(dist / dur, 1) if (dur > 0 and dist > 0) else "-"
            _add_row(rows, step_no, veh_label, descr, city, dist, t, time_left_cell, ontime_cell,
                     drive_time=drive_total, breaks=breaks_count, tacho_rem=tacho_now,
                     fuel_cost=cost_so_far, avg_speed=avg_speed)
            step_no += 1

            # service time at pickup/delivery
            if tip_pas in ("pickup", "delivery"):
                t += SERVICE_TIME
                since_break = 0.0
                since_apt += SERVICE_TIME

                # after delivery: remove order from onboard
                if tip_pas == "delivery" and oid in onboard:
                    del onboard[oid]

                # special case: delivery in depot city 
                tacho_svc = max(0.0, rest_limit - since_rest)
                if tip_pas == "delivery" and i == last_del_idx and city == depot_city:
                    _add_row(rows, step_no, veh_label, "Arrive depot", city, "-", t, "-", "-",
                             drive_time=drive_total, breaks=breaks_count, tacho_rem=tacho_svc,
                             fuel_cost=cost_so_far)
                    step_no += 1
                else:
                    show_after = (i < last_del_idx) if tip_pas == "delivery" else (i <= last_del_idx)
                    time_left_after = "-"
                    ontime_after = "-"
                    if show_after:
                        active_deadline = _nearest_future_deadline(steps, i, onboard, last_del_idx)
                        if active_deadline is not None:
                            slack_after = active_deadline - t
                            time_left_after = slack_after
                            ontime_after = _status_flag(slack_after)

                    _add_row(rows, step_no, veh_label, f"Depart order {oid} ({tip_pas})",
                             city, "-", t, time_left_after, ontime_after,
                             drive_time=drive_total, breaks=breaks_count, tacho_rem=tacho_svc,
                             fuel_cost=cost_so_far)
                    step_no += 1

            i += 1

    # render
    df = pd.DataFrame(rows)
    col_order = ["Step", "Vehicle", "Description", "City", "Distance (km)", "Speed (km/h)",
                 "Time elapsed (h)", "Drive time (h)", "Breaks", "Tacho remaining (h)",
                 "Fuel cost (RON)", "Time left (h)", "On time?"]
    df = df[[c for c in col_order if c in df.columns]]

    df["On time (flag)"] = df["On time?"].astype(str).eq("YES")

    st.subheader("📋 Routing Table")

    with st.expander("Filters", expanded=False):
        sel_veh = st.multiselect("Vehicle", sorted(df["Vehicle"].unique()))
        sel_city = st.multiselect("City", sorted(df["City"].unique()))
        sel_status = st.multiselect("Status", ["On time", "Late"])
        if sel_veh:   df = df[df["Vehicle"].isin(sel_veh)]
        if sel_city:  df = df[df["City"].isin(sel_city)]
        if sel_status:
            want = {"On time": True, "Late": False}
            df = df[df["On time (flag)"].isin([want[s] for s in sel_status])]

    if df.empty:
        st.info("No rows match the current filters — try clearing one or more filters.")
    else:
        st.dataframe(
            df.drop(columns=["On time (flag)"]),
            use_container_width=True,
            hide_index=True
        )

    total_km = pd.to_numeric(df["Distance (km)"].replace({"": 0, "-": 0}),
                             errors="coerce").fillna(0).sum()
    st.markdown(f"**Estimated total distance:** `{round(total_km, DECIMALS_KM)} km`")
    st.markdown(f"**Vehicles used:** `{len(routes)}`")

    if late:
        st.subheader("📊 Delay details")
        st.dataframe(pd.DataFrame(late), use_container_width=True)
    if dropped:
        st.warning(
            f"⚠️ {len(dropped)} order(s) were excluded entirely from the plan "
            "(capacity/time infeasible). See the KPI dropped panel above."
        )
    if not late and not dropped:
        st.success("✅ All deliveries on time")

    if biweekly_violations:
        st.subheader("⚖️ EU Regulation 561/2006 — Bi-weekly drive limit exceeded (90h)")
        st.dataframe(pd.DataFrame(biweekly_violations), use_container_width=True)

    # ── HGV speed-limit compliance check (Romanian OUG 195/2002) ──────────
    speed_violations = [
        {
            "Step":          row.get("Step"),
            "Vehicle":       row.get("Vehicle"),
            "City":          row.get("City"),
            "Segment avg speed (km/h)": row.get("Speed (km/h)"),
            "HGV highway limit (km/h)": RO_HGV_SPEED_HIGHWAY_KMPH,
        }
        for row in rows
        if isinstance(row.get("Speed (km/h)"), (int, float))
        and float(row["Speed (km/h)"]) > RO_HGV_SPEED_HIGHWAY_KMPH
    ]
    if speed_violations:
        st.subheader("⚠️ Speed limit check — HGV > 3.5 t (Romania)")
        st.warning(
            f"{len(speed_violations)} road segment(s) have an average speed above the "
            f"maximum HGV motorway limit ({RO_HGV_SPEED_HIGHWAY_KMPH} km/h). "
            "Check whether these segments use a road category with a lower limit."
        )
        st.dataframe(pd.DataFrame(speed_violations), use_container_width=True, hide_index=True)
    else:
        st.success(
            f"✅ All road segments comply with the Romanian HGV speed limit "
            f"(max motorway limit: {RO_HGV_SPEED_HIGHWAY_KMPH} km/h)"
        )

    # ── Fuel cost per-vehicle summary ─────────────────────────────────────
    fuel_rows = []
    for route in routes:
        veh = route.get("vehicul", {})
        veh_label_ = _veh_name(veh)
        fuel_l100 = float(veh.get("fuel_l100km", 30)) if isinstance(veh, dict) else 30.0
        km_vehicle = sum(float(s.get("distanta", 0) or 0) for s in route.get("traseu", []))
        liters = km_vehicle * fuel_l100 / 100.0
        cost   = liters * fuel_price
        fuel_rows.append({
            "Vehicle":          veh_label_,
            "Distance (km)":    round(km_vehicle, 2),
            "Fuel (L/100km)":   fuel_l100,
            "Fuel used (L)":    round(liters, 1),
            "Cost (RON)":       round(cost, 2),
        })
    if fuel_rows:
        st.subheader("⛽ Fuel cost per vehicle")
        df_fuel = pd.DataFrame(fuel_rows)
        total_fuel_cost = df_fuel["Cost (RON)"].sum()
        st.dataframe(df_fuel, use_container_width=True, hide_index=True)
        st.markdown(f"**Total estimated fuel cost:** `{round(total_fuel_cost, 2)} RON`")

    # ── Export note ──────────────────────────────────────────────────────────
    if sel_veh or sel_city or sel_status:
        st.info(
            "ℹ️ Active filters are applied — the Excel and PDF exports below "
            "contain only the currently visible rows. Clear the filters to export "
            "the complete route report."
        )

    # export scenario
    scenario_json = BytesIO()
    scenario_json.write(json.dumps({
        "fleet": st.session_state.get("vehicle_profiles", []),
        "orders": st.session_state.get("requests", []),
        "routes": routes,
    }, indent=2).encode("utf-8"))
    scenario_json.seek(0)
    st.download_button(
        "💾 Save current scenario",
        data=scenario_json,
        file_name="scenario_export.json",
        mime="application/json"
    )

    # export Excel
    df_export = df.drop(columns=["On time (flag)"], errors="ignore")
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as w:
        df_export.to_excel(w, sheet_name='Routing', index=False)
        if late:
            pd.DataFrame(late).to_excel(w, sheet_name='Delays', index=False)
        if fuel_rows:
            pd.DataFrame(fuel_rows).to_excel(w, sheet_name='Fuel', index=False)
        w.sheets['Routing'].set_column(0, len(df_export.columns)-1, 18)
    st.download_button(
        "📥 Export table to Excel",
        data=out.getvalue(),
        file_name="routing_table.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # export PDF
    pdf_bytes = _build_pdf(routes, df_export, late, fuel_rows if fuel_rows else [])
    st.download_button(
        "📄 Export report to PDF",
        data=pdf_bytes,
        file_name="routing_report.pdf",
        mime="application/pdf"
    )
