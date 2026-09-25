"""Driver-hours schedule: replays each route against EU Regulation 561/2006 and the
Romanian HGV rules, inserting breaks and rests and tracking deadlines."""
from .planning import vehicle_label

# ---- EU Regulation 561/2006 & Directive 2002/15 ----
SERVICE_TIME = 2.0                  # h per pickup/delivery (operational)
DRIVER_BREAK = 0.75                 # 45 min mandatory break after 4.5h driving
BREAK_WINDOW = 4.5                  # h driving before the 45-min break is due
SINGLE_DRIVER_DAILY_LIMIT = 9       # h max driving per day, single driver
CREW_DRIVER_DAILY_LIMIT = 18        # h max combined driving, multi-manning (9h x 2)
# Working window from the end of the last daily rest until the next one must start.
# After a regular 11h rest: 13h (24-11). After a reduced 9h rest: 15h (24-9).
APTITUDE_AFTER_NORMAL_REST = 13
APTITUDE_AFTER_REDUCED_REST = 15
CREW_DRIVER_APTITUDE = 21           # multi-manning: 30h cycle - 9h rest
DAILY_REST_NORMAL = 11
DAILY_REST_REDUCED = 9              # max 3x between weekly rests
MAX_REDUCED_DAILY_RESTS = 3
WEEKLY_DRIVE_LIMIT = 56
BIWEEKLY_DRIVE_LIMIT = 90
WEEKLY_REST_NORMAL = 45
WEEKLY_REST_REDUCED = 24            # max 1 per 2 weeks
MAX_HOURS_BEFORE_WEEKLY_REST = 6 * 24

# ---- Romanian speed limits for HGV > 3.5 t (OUG 195/2002, art. 50) ----
RO_HGV_SPEED_LOCALITY_KMPH = 50
RO_HGV_SPEED_HIGHWAY_KMPH = 90
RO_HGV_SPEED_EXPRESS_KMPH = 80
RO_HGV_SPEED_NATIONAL_KMPH = 70
RO_HGV_SPEED_LIMITER_KMPH = 105     # mandatory hardware limiter (Directive 92/6/EEC)

ARRIVAL_TEXT = {
    "return": "Arrive depot",
    "arrive_depot": "Arrive depot (begin route)",
    "depart": "Depart depot",
}


def _limits(vehicle, last_rest_was_reduced):
    """(max driving per day, max working window since the last daily rest)."""
    if vehicle.get("crew"):
        return CREW_DRIVER_DAILY_LIMIT, CREW_DRIVER_APTITUDE
    window = APTITUDE_AFTER_REDUCED_REST if last_rest_was_reduced else APTITUDE_AFTER_NORMAL_REST
    return SINGLE_DRIVER_DAILY_LIMIT, window


def order_label(step):
    oid, part = step.get("order_id"), step.get("part")
    return f"{oid}.{part}" if part else f"{oid}"


def _delivery_deadline(steps, start, label):
    for s in steps[start + 1:]:
        if s.get("type") == "delivery" and order_label(s) == label:
            dl = s.get("deadline_h")
            if isinstance(dl, (int, float)):
                return float(dl)
    return None


def _nearest_deadline(steps, cur, onboard, last_delivery):
    """Tightest deadline among loads on board and stops still ahead."""
    cands = [float(v) for v in onboard.values()]
    end = last_delivery if last_delivery != -1 else len(steps) - 1
    for j in range(cur, end + 1):
        s = steps[j]
        if s.get("type") in ("pickup", "delivery"):
            dl = s.get("deadline_h")
            if not isinstance(dl, (int, float)) and s["type"] == "pickup":
                dl = _delivery_deadline(steps, j, order_label(s))
            if isinstance(dl, (int, float)):
                cands.append(float(dl))
    return min(cands) if cands else None


def build_schedule(routes):
    """Returns rows (one per event), late deliveries, legal arrival time per order,
    EU/RO violations and fuel use. Fuel is in litres; callers multiply by a fuel price."""
    rows, late, biweekly, arrivals = [], [], [], {}
    step_no = 1

    for v_idx, route in enumerate(routes):
        veh = route["vehicle"]
        label = vehicle_label(veh)
        steps = route["steps"]
        if not steps:
            continue
        depot = route.get("depot", steps[0]["city"])
        fuel_l100 = float(veh.get("fuel_l100km", 30))
        last_del = max((i for i, s in enumerate(steps) if s.get("type") == "delivery"), default=-1)

        t = since_break = since_rest = since_window = drive_total = km_total = 0.0
        breaks = 0
        reduced_daily_count = 0
        last_rest_reduced = False
        weekly_drive, weekly_start = 0.0, 0.0
        weekly_history = []
        reduced_weekly_used = False
        onboard = {}

        def add(kind, descr, city, time_left=None, dist=None, speed=None, tacho=None):
            nonlocal step_no
            rows.append({
                "step": step_no, "vehicle": label, "vehicle_index": v_idx, "kind": kind,
                "description": descr, "city": city,
                "distance_km": None if dist is None else round(dist, 2),
                "speed_kmh": speed, "elapsed_h": round(t, 4), "drive_h": round(drive_total, 4),
                "breaks": breaks, "tacho_remaining_h": None if tacho is None else round(tacho, 4),
                "fuel_l": round(km_total * fuel_l100 / 100.0, 3),
                "time_left_h": None if time_left is None else round(time_left, 4),
                "on_time": None if time_left is None else time_left >= 0,
            })
            step_no += 1

        def slack_at(i, show):
            if not show:
                return None
            dl = _nearest_deadline(steps, i, onboard, last_del)
            return None if dl is None else dl - t

        first = steps[0]
        first_text = "Depart current location" if first["type"] == "home_depart" else "Depart depot"
        daily_limit, window_limit = _limits(veh, last_rest_reduced)
        add("depart", first_text, first["city"],
            time_left=slack_at(1, last_del != -1), tacho=daily_limit)

        for i in range(1, len(steps)):
            s = steps[i]
            kind = s.get("type", "transit")
            city = s["city"]
            dist = float(s.get("distance_km") or 0.0)
            dur = float(s.get("duration_h") or 0.0)
            olabel = order_label(s)
            daily_limit, window_limit = _limits(veh, last_rest_reduced)
            show = i <= last_del if last_del != -1 else True

            while True:
                # weekly rest has priority: EU 561/2006 Art. 8(6)
                weekly_exceeded = weekly_drive + dur > WEEKLY_DRIVE_LIMIT
                six_days = t - weekly_start > MAX_HOURS_BEFORE_WEEKLY_REST
                if weekly_exceeded or six_days:
                    use_reduced = not reduced_weekly_used
                    rest = WEEKLY_REST_REDUCED if use_reduced else WEEKLY_REST_NORMAL
                    prev_week = weekly_history[-1] if weekly_history else 0.0
                    if prev_week + weekly_drive > BIWEEKLY_DRIVE_LIMIT:
                        biweekly.append({"vehicle": label, "drive_h": round(prev_week + weekly_drive, 2),
                                         "limit_h": BIWEEKLY_DRIVE_LIMIT})
                    weekly_history.append(weekly_drive)
                    reduced_weekly_used = use_reduced
                    t += rest
                    weekly_drive, weekly_start = 0.0, t
                    reduced_daily_count = 0
                    last_rest_reduced = False
                    since_break = since_rest = since_window = 0.0
                    reason = "weekly drive >56h" if weekly_exceeded else "6-day rule"
                    daily_limit, window_limit = _limits(veh, last_rest_reduced)
                    add("weekly_rest", f"Weekly rest ({rest}h, {'reduced' if use_reduced else 'normal'}), {reason}",
                        "On route", time_left=slack_at(i, show), tacho=daily_limit)
                    continue

                window_hit = since_window + dur > window_limit
                daily_hit = since_rest + dur > daily_limit
                if window_hit or daily_hit:
                    # Art. 8(4): up to 3 reduced (9h) daily rests between weekly rests
                    use_reduced = reduced_daily_count < MAX_REDUCED_DAILY_RESTS
                    rest = DAILY_REST_REDUCED if use_reduced else DAILY_REST_NORMAL
                    reduced_daily_count += use_reduced
                    last_rest_reduced = use_reduced
                    t += rest
                    since_break = since_rest = since_window = 0.0
                    cause = "working window reached" if window_hit else "daily driving limit reached"
                    daily_limit, window_limit = _limits(veh, last_rest_reduced)
                    add("daily_rest", f"Daily rest ({rest}h, {'reduced' if use_reduced else 'normal'}), {cause}",
                        "On route", time_left=slack_at(i, show), tacho=daily_limit)
                    continue

                if since_break + dur > BREAK_WINDOW:
                    t += DRIVER_BREAK
                    since_break = 0.0
                    since_window += DRIVER_BREAK
                    breaks += 1
                    add("break", "Driver break (45 min)", "On route",
                        time_left=slack_at(i, show), tacho=max(0.0, daily_limit - since_rest))
                    continue
                break

            t += dur
            since_break += dur
            since_rest += dur
            since_window += dur
            weekly_drive += dur
            drive_total += dur
            km_total += dist

            if kind in ("pickup", "delivery"):
                descr = f"Arrive order {olabel} ({kind})"
            else:
                descr = ARRIVAL_TEXT.get(kind, "Transit")

            if kind == "pickup":
                dl = s.get("deadline_h")
                if not isinstance(dl, (int, float)):
                    dl = _delivery_deadline(steps, i, olabel)
                if isinstance(dl, (int, float)):
                    onboard[olabel] = float(dl)

            if kind == "delivery":
                arrivals[olabel] = t
                own = s.get("deadline_h", onboard.get(olabel))
                if isinstance(own, (int, float)) and own - t < 0:
                    late.append({"vehicle": label, "order": olabel, "delay_h": round(t - own, 4)})

            speed = round(dist / dur, 1) if dur > 0 and dist > 0 else None
            add("arrive" if kind != "transit" else "transit", descr, city,
                time_left=slack_at(i, show), dist=dist, speed=speed,
                tacho=max(0.0, daily_limit - since_rest))

            if kind in ("pickup", "delivery"):
                t += SERVICE_TIME
                since_break = 0.0
                since_window += SERVICE_TIME
                if kind == "delivery":
                    onboard.pop(olabel, None)
                tacho = max(0.0, daily_limit - since_rest)
                if kind == "delivery" and i == last_del and city == depot:
                    add("arrive", "Arrive depot", city, tacho=tacho)
                else:
                    show_after = i < last_del if kind == "delivery" else i <= last_del
                    add("service", f"Depart order {olabel} ({kind})", city,
                        time_left=slack_at(i, show_after), tacho=tacho)

    speed_violations = [
        {"step": r["step"], "vehicle": r["vehicle"], "city": r["city"],
         "speed_kmh": r["speed_kmh"], "limit_kmh": RO_HGV_SPEED_HIGHWAY_KMPH}
        for r in rows if r["speed_kmh"] is not None and r["speed_kmh"] > RO_HGV_SPEED_HIGHWAY_KMPH
    ]

    fuel = []
    for route in routes:
        veh = route["vehicle"]
        km = sum(float(s.get("distance_km") or 0) for s in route["steps"])
        per100 = float(veh.get("fuel_l100km", 30))
        fuel.append({"vehicle": vehicle_label(veh), "distance_km": round(km, 2),
                     "fuel_l100km": per100, "fuel_l": round(km * per100 / 100.0, 2)})

    return {"rows": rows, "late": late, "arrivals": arrivals, "biweekly_violations": biweekly,
            "speed_violations": speed_violations, "fuel": fuel}
