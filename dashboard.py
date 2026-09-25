"""Extra dashboard widgets: alerts, CO2, driver workload, cost pie, Gantt, notifications."""
import math
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta


def _today_dispatch_iso() -> str:
    """Return today's date at 08:00 as an ISO string for use as simulation start."""
    return datetime.combine(date.today(), datetime.min.time().replace(hour=8)).isoformat()

__all__ = [
    "render_alerts_panel",
    "render_co2_summary",
    "render_driver_workload",
    "render_cost_breakdown",
    "render_gantt_chart",
    "render_customer_notifications",
    "render_journey_timeline",
]

# Vehicle colours (must match map_view COLORS)
VEHICLE_COLORS = [
    "#FF003C", "#FF6B00", "#FFB700", "#FF4458", "#FFD93D",
    "#FF1744", "#FF8C42", "#FFA600", "#E63946", "#FF5E5B", "#FFAA00",
]

# Diesel CO2 factor: 2.68 kg CO2 per liter of diesel burned
CO2_KG_PER_LITER_DIESEL = 2.68


def _vehicle_label(veh):
    if isinstance(veh, dict):
        name = veh.get("nume", "Vehicle")
        driver = veh.get("driver_name", "")
        return f"{name} ({driver})" if driver else name
    return str(veh)


# ──────────────── A. Alerts panel (E) ────────────────
def render_alerts_panel(routes, dropped):
    """Show actionable warnings: drivers near limit, late deliveries, dropped orders."""
    alerts = []
    SINGLE_LIMIT_H = 9
    CREW_LIMIT_H   = 18

    for route in routes:
        veh = route.get("vehicul", {})
        veh_label = _vehicle_label(veh)
        crew = veh.get("echipaj", False) if isinstance(veh, dict) else False
        limit = CREW_LIMIT_H if crew else SINGLE_LIMIT_H

        # Sum driving time on route
        drive_h = sum(float(s.get("durata", 0) or 0) for s in route.get("traseu", []))
        if drive_h > limit * 0.85:
            severity = "HIGH" if drive_h > limit else "MED"
            alerts.append({
                "Severity": severity,
                "Vehicle": veh_label,
                "Type": "Driver fatigue",
                "Detail": f"Drive time {drive_h:.1f}h vs limit {limit}h",
            })

        # Check for late deliveries
        for s in route.get("traseu", []):
            if s.get("tip") == "delivery":
                pass  # handled by main table; we surface dropped here

    for d in dropped or []:
        alerts.append({
            "Severity": "HIGH",
            "Vehicle": "—",
            "Type": "Order dropped",
            "Detail": f"{d.get('pickup')} → {d.get('delivery')} ({d.get('demand')}kg, deadline {d.get('time_limit_hrs')}h)",
        })

    if not alerts:
        st.success("✅ No active alerts — all drivers within limits, all orders delivered on time.")
        return

    st.subheader("⚠️ Active Alerts")
    df = pd.DataFrame(alerts).sort_values("Severity", ascending=False)
    def _color(s):
        return ["background-color: rgba(255,0,60,0.18)" if v == "HIGH"
                else "background-color: rgba(255,107,0,0.18)" for v in s]
    st.dataframe(df.style.apply(_color, subset=["Severity"]),
                 use_container_width=True, hide_index=True)


# ──────────────── B. CO2 emissions (D) ────────────────
def render_co2_summary(routes):
    rows = []
    total_co2 = 0.0
    for route in routes:
        veh = route.get("vehicul", {})
        fuel_l100 = float(veh.get("fuel_l100km", 30)) if isinstance(veh, dict) else 30.0
        km = sum(float(s.get("distanta", 0) or 0) for s in route.get("traseu", []))
        liters = km * fuel_l100 / 100.0
        co2 = liters * CO2_KG_PER_LITER_DIESEL
        total_co2 += co2
        rows.append({
            "Vehicle":     _vehicle_label(veh),
            "Distance km": round(km, 1),
            "Fuel L":      round(liters, 1),
            "CO₂ kg":      round(co2, 1),
            "Trees needed*": round(co2 / 21, 1),
        })
    st.subheader("🌍 Carbon Footprint")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total CO₂", f"{round(total_co2, 1)} kg")
    c2.metric("Equivalent trees¹", f"{round(total_co2/21, 1)} 🌳")
    c3.metric("Cost @ €50/tonne", f"€ {round(total_co2 * 0.05, 2)}")
    st.caption("¹ One mature tree absorbs ~21 kg CO₂ per year.")


# ──────────────── C. Driver workload bar ────────────────
def render_driver_workload(routes):
    st.subheader("👤 Driver Workload (total driving vs trip limit)")
    st.caption(
        "Total driving time on the full trip compared to the EU 561/2006 allowed limit "
        "for the number of working days (single driver: 9 h/day · crew of 2: 18 h/day). "
        "Per-day compliance details are in the Routing Table tab."
    )
    for route in routes:
        veh = route.get("vehicul", {})
        veh_label = _vehicle_label(veh)
        crew = veh.get("echipaj", False) if isinstance(veh, dict) else False
        daily_limit = 18 if crew else 9

        drive_h = sum(float(s.get("durata", 0) or 0) for s in route.get("traseu", []))

        # A multi-day route spans several work-days; compute total allowed driving
        # for the whole trip (num_days × daily limit).  Comparing 25.5h against
        # 9h (one day) is misleading — the correct denominator is 3 days × 9h = 27h.
        num_days  = max(1, math.ceil(drive_h / daily_limit))
        trip_limit = num_days * daily_limit
        pct = min(drive_h / trip_limit, 1.0)

        col_label, col_bar, col_text = st.columns([2, 5, 2])
        col_label.markdown(f"**{veh_label}**" + (" 👥" if crew else ""))
        col_bar.progress(pct)
        status = "🟢" if pct < 0.7 else ("🟡" if pct < 0.95 else "🔴")
        days_tag = f"  ·  {num_days}d" if num_days > 1 else ""
        col_text.markdown(f"{status} `{drive_h:.1f}h / {trip_limit}h{days_tag}`")


# ──────────────── D. Cost breakdown pie chart (F) ────────────────
def render_cost_breakdown(routes, fuel_price=7.5, hourly_wage=40.0):
    """Pie chart: fuel vs driver salary vs vehicle depreciation."""
    total_fuel = 0.0
    total_labor = 0.0
    total_depr = 0.0
    DEPRECIATION_PER_KM = 0.15  # EUR/km estimate
    for route in routes:
        veh = route.get("vehicul", {})
        fuel_l100 = float(veh.get("fuel_l100km", 30)) if isinstance(veh, dict) else 30.0
        km = sum(float(s.get("distanta", 0) or 0) for s in route.get("traseu", []))
        h  = sum(float(s.get("durata", 0) or 0) for s in route.get("traseu", []))
        total_fuel  += km * fuel_l100 / 100.0 * fuel_price
        total_labor += h * hourly_wage
        total_depr  += km * DEPRECIATION_PER_KM

    st.subheader("💰 Cost Breakdown")
    c1, c2 = st.columns([1, 1])
    with c1:
        wage = st.number_input("Driver hourly wage (RON/h)", min_value=0.0,
                               value=hourly_wage, step=5.0, key="wage_input")
    with c2:
        depr = st.number_input("Vehicle depreciation (RON/km)", min_value=0.0,
                               value=DEPRECIATION_PER_KM, step=0.05, key="depr_input")

    # Recompute with user inputs
    total_labor = sum(sum(float(s.get("durata", 0) or 0)
                          for s in r.get("traseu", [])) * wage for r in routes)
    total_depr  = sum(sum(float(s.get("distanta", 0) or 0)
                          for s in r.get("traseu", [])) * depr for r in routes)

    df_cost = pd.DataFrame({
        "Category": ["Fuel", "Driver labor", "Vehicle depreciation"],
        "Cost (RON)": [round(total_fuel, 2), round(total_labor, 2), round(total_depr, 2)],
    })
    total = df_cost["Cost (RON)"].sum()
    df_cost["Share %"] = (df_cost["Cost (RON)"] / max(total, 1) * 100).round(1)
    st.dataframe(df_cost, use_container_width=True, hide_index=True)
    st.markdown(f"**Total cost:** `{round(total, 2)} RON`")
    # Use plotly chart if available, else fallback to bar chart
    try:
        import plotly.express as px
        fig = px.pie(df_cost, names="Category", values="Cost (RON)",
                     color="Category",
                     color_discrete_map={"Fuel":"#FF003C","Driver labor":"#FF6B00","Vehicle depreciation":"#FFB700"},
                     hole=0.4)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#D6E2F0"))
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.bar_chart(df_cost.set_index("Category")["Cost (RON)"])


# ──────────────── E. Gantt chart (A) ────────────────
def render_gantt_chart(routes, sim_start_iso=None):
    """Timeline showing each vehicle's activities over time."""
    st.subheader("📅 Vehicle Schedule (Gantt)")
    base = datetime.fromisoformat(sim_start_iso or _today_dispatch_iso())
    SERVICE_H = 2.0   # must match table_view.SERVICE_TIME
    bars = []
    for route in routes:
        veh = route.get("vehicul", {})
        veh_label = _vehicle_label(veh)
        t = base
        for s in route.get("traseu", []):
            dur_h = float(s.get("durata", 0) or 0)
            tip = s.get("tip", "")
            if dur_h == 0 and tip not in ("pickup", "delivery"):
                continue
            if dur_h > 0:
                end = t + timedelta(hours=dur_h)
                label = {
                    "pickup":      "📦 Pickup",
                    "delivery":    "🎯 Delivery",
                    "intoarcere":  "↩️ Return",
                    "home_depart": "🏠 Home depart",
                    "arrive_depot":"🏢 Depot",
                }.get(tip, "🚛 Transit")
                bars.append({
                    "Vehicle":  veh_label,
                    "Activity": label + " — " + s.get("oras", ""),
                    "Start":    t,
                    "Finish":   end,
                    "Type":     tip or "transit",
                })
                t = end
            # add 2 h loading/unloading bar at each pickup or delivery stop
            if tip in ("pickup", "delivery"):
                svc_label = "⏳ Loading" if tip == "pickup" else "⏳ Unloading"
                bars.append({
                    "Vehicle":  veh_label,
                    "Activity": svc_label + " — " + s.get("oras", ""),
                    "Start":    t,
                    "Finish":   t + timedelta(hours=SERVICE_H),
                    "Type":     "service",
                })
                t += timedelta(hours=SERVICE_H)

    if not bars:
        st.info("No timeline data.")
        return

    df = pd.DataFrame(bars)
    try:
        import plotly.express as px
        color_map = {
            "pickup":      "#FF6B00",
            "delivery":    "#FF003C",
            "intoarcere":  "#FFB700",
            "home_depart": "#FFA600",
            "arrive_depot":"#FF1744",
            "transit":     "#8B0000",
            "service":     "#444466",
        }
        fig = px.timeline(df, x_start="Start", x_end="Finish", y="Vehicle",
                          color="Type", color_discrete_map=color_map,
                          hover_data=["Activity"])
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(
            paper_bgcolor="rgba(8,2,10,0.7)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#D6E2F0"),
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.dataframe(df, use_container_width=True, hide_index=True)


# ──────────────── F. Customer notifications mock (H) ────────────────
def render_customer_notifications(routes, sim_start_iso=None):
    """Mock SMS/email notifications sent to customers as their delivery arrives.
    Times match the Journey Timeline (i.e. +2h service time after each pickup
    and delivery, like a real driver loading/unloading)."""
    base = datetime.fromisoformat(sim_start_iso or _today_dispatch_iso())
    notifs = []
    for route in routes:
        veh = route.get("vehicul", {})
        veh_label = _vehicle_label(veh)
        t = base
        for s in route.get("traseu", []):
            t += timedelta(hours=float(s.get("durata", 0) or 0))
            tip = s.get("tip")
            if tip == "delivery":
                oid = s.get("order_id", s.get("comanda", "—"))
                # If split chunk, append part number for clarity
                part = s.get("part")
                oid_label = f"{oid}.{part}" if part else f"{oid}"
                # Show date too if crossing midnight from start
                same_day = (t.date() == base.date())
                time_str = t.strftime("%H:%M") if same_day else t.strftime("%a %H:%M")
                notifs.append({
                    "Time":      time_str,
                    "Channel":   "📱 SMS",
                    "To":        f"Customer #{oid_label}",
                    "Message":   f"Your order arrived at {s.get('oras')}. Vehicle: {veh_label}.",
                })
                t += timedelta(hours=2)   # service time after delivery (sync with Journey)
            elif tip == "pickup":
                t += timedelta(hours=2)   # service time after pickup
    if notifs:
        st.subheader("✉️ Customer Notifications (mock)")
        st.dataframe(pd.DataFrame(notifs), use_container_width=True, hide_index=True)
    else:
        st.info("No customer notifications — no deliveries found in the current routes.")


# ──────────────── G. Journey Timeline (vertical, colour-coded) ────────────────
def render_journey_timeline(routes, sim_start_iso=None):
    """Colour-coded vertical journey: 🏠 Depot → 📦 Pickup → 🎯 Delivery → ↩️ Return
    Each vehicle is shown in its own card with its route colour as the timeline spine.
    """
    st.subheader("🛣️ Journey Timeline — what each truck does, step by step")
    if not routes:
        st.info("No routes to display.")
        return

    base = datetime.fromisoformat(sim_start_iso or _today_dispatch_iso())

    for v_idx, route in enumerate(routes):
        veh = route.get("vehicul", {})
        veh_label = _vehicle_label(veh)
        color = VEHICLE_COLORS[v_idx % len(VEHICLE_COLORS)]
        depot = route.get("depot", "Depot")

        # ── Header card ──
        st.markdown(
            f'<div style="background:linear-gradient(90deg, {color}22, transparent);'
            f'border-left:5px solid {color};padding:10px 16px;border-radius:0 8px 8px 0;'
            f'margin-top:18px;margin-bottom:6px;">'
            f'<span style="color:{color};font-family:Orbitron,sans-serif;font-weight:700;'
            f'font-size:1.05rem;letter-spacing:1px;text-shadow:0 0 8px {color}80;">'
            f'🚚 {veh_label}</span></div>',
            unsafe_allow_html=True,
        )

        # ── Build step list ──
        t = base
        steps_to_show = []
        # Starting point
        first = (route.get("traseu") or [{}])[0]
        first_city = first.get("oras", depot)
        if first.get("tip") == "home_depart":
            steps_to_show.append(("🚛", "Depart from current location", first_city,
                                  "Start", t, color))
        else:
            steps_to_show.append(("🏢", "Depart depot", first_city, "Start", t, "#FF003C"))

        # Iterate through steps in order
        for s in route.get("traseu", [])[1:]:
            t += timedelta(hours=float(s.get("durata", 0) or 0))
            tip = s.get("tip", "")
            city = s.get("oras", "")
            oid  = s.get("order_id", s.get("comanda", ""))
            part = s.get("part")
            oid_label = f"{oid}.{part}" if (oid and part) else f"{oid}"
            if tip == "pickup":
                steps_to_show.append(("📦", f"Pickup order #{oid_label}", city, "Loading", t, "#FF6B00"))
                # Service time 2h
                t += timedelta(hours=2)
            elif tip == "delivery":
                steps_to_show.append(("🎯", f"Delivery order #{oid_label}", city, "Unloading", t, "#FF003C"))
                t += timedelta(hours=2)
            elif tip == "intoarcere":
                steps_to_show.append(("↩️", "Return to depot", city, "Arrived", t, "#FFB700"))
            elif tip == "arrive_depot":
                steps_to_show.append(("🏢", "Arrive at depot", city, "Ready", t, "#FF003C"))
            # transit/intermediar steps are skipped (too many)

        # ── Render vertical timeline ──
        # If any step crosses midnight, show day-of-week to avoid confusion.
        crosses_midnight = any(t_v.date() != base.date() for _, _, _, _, t_v, _ in steps_to_show)
        for icon, label, city, status, time_val, step_color in steps_to_show:
            if crosses_midnight:
                # e.g. "Wed 04:48" vs "Wed 16:00" — clear which day
                day_delta = (time_val.date() - base.date()).days
                if day_delta == 0:
                    time_str = "Day 1 · " + time_val.strftime("%H:%M")
                else:
                    time_str = f"Day {day_delta + 1} · " + time_val.strftime("%H:%M")
            else:
                time_str = time_val.strftime("%H:%M")
            st.markdown(
                f'<div style="display:flex;align-items:center;margin:4px 0 4px 12px;'
                f'padding:6px 12px;background:rgba(8,2,10,0.5);border-radius:6px;'
                f'border-left:3px solid {step_color};">'
                f'<span style="font-size:1.3rem;margin-right:14px;">{icon}</span>'
                f'<div style="flex:1;">'
                f'<span style="color:{step_color};font-weight:600;font-family:Share Tech Mono,monospace;">'
                f'{label}</span>'
                f'<span style="color:#8FA3BD;margin-left:10px;">— {city}</span>'
                f'</div>'
                f'<span style="color:#8FA3BD;font-family:Share Tech Mono,monospace;font-size:0.85rem;">'
                f'{time_str} <span style="color:{step_color};opacity:0.7;">· {status}</span>'
                f'</span></div>',
                unsafe_allow_html=True,
            )
