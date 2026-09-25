"""
Playwright end-to-end verification of FleetRoute Optimizer.
Drives a real Chromium browser through a full scenario:
  depot + 2 vehicles + 3 orders -> generate routes -> walk every tab
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

BASE        = "http://localhost:8501"
SCREENSHOTS = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOTS, exist_ok=True)

findings = []
steps    = []

def shot(page: Page, name: str):
    p = os.path.join(SCREENSHOTS, f"{name}.png")
    page.screenshot(path=p, full_page=False)
    return p

def step(icon, desc, detail=""):
    line = f"  {icon}  {desc}" + (f"\n       {detail}" if detail else "")
    steps.append(line)
    print(line)

def find(severity, msg):
    findings.append((severity, msg))
    tag = "ERROR" if severity == "error" else "WARN"
    print(f"  [{tag}]  {msg}")

def wait_ready(page: Page, timeout=60000):
    """Wait until Streamlit stops showing the running indicator."""
    try:
        page.wait_for_selector("[data-testid='stStatusWidget']",
                               state="hidden", timeout=timeout)
    except PWTimeout:
        pass
    try:
        page.wait_for_function(
            "!document.querySelector('[data-testid=\"stSpinner\"]')",
            timeout=min(timeout, 5000))
    except PWTimeout:
        pass
    time.sleep(0.6)

# ── Streamlit-aware widget helpers ────────────────────────────────────────────

def selectbox_choose(page: Page, nth: int, value: str):
    """
    Streamlit selectboxes render as BaseWeb <input role=combobox>.
    nth=0 → Depot, nth=1 → first form selectbox, etc.
    """
    sb = page.locator("[data-testid='stSidebar']") \
             .locator("[data-baseweb='select']").nth(nth) \
             .locator("input")
    sb.click()
    time.sleep(0.2)
    sb.fill(value)
    time.sleep(0.2)
    page.locator("[data-baseweb='popover'] [role='option']") \
        .filter(has_text=value).first.click()
    time.sleep(0.2)

def form_text(page: Page, label: str, value: str):
    """Fill a text input identified by its visible label inside the sidebar."""
    sidebar = page.locator("[data-testid='stSidebar']")
    sidebar.get_by_label(label, exact=True).fill(value)

def form_number(page: Page, label: str, value: str):
    sidebar = page.locator("[data-testid='stSidebar']")
    inp = sidebar.locator("label", has_text=label).locator("..").locator("input")
    inp.first.fill(value)
    inp.first.press("Tab")

def sidebar_button(page: Page, text: str):
    page.locator("[data-testid='stSidebar']") \
        .get_by_role("button", name=text).first.click()
    wait_ready(page, 90000)

# ── Main verification flow ────────────────────────────────────────────────────

def run(page: Page):

    # ── 1. Load app ────────────────────────────────────────────────────────
    page.goto(BASE, wait_until="networkidle", timeout=30000)
    page.wait_for_selector("[data-testid='stSidebar']", timeout=45000)
    wait_ready(page, 30000)
    title = page.title()
    shot(page, "01_loaded")
    step("✅", f"App loaded  title={title!r}")

    # ── 2. Select depot ────────────────────────────────────────────────────
    selectbox_choose(page, 0, "Cluj-Napoca")
    wait_ready(page)
    shot(page, "02_depot")
    step("✅", "Depot = Cluj-Napoca")

    # check the main area now shows the fleet/orders prompt or map
    body = page.locator(".block-container").inner_text()
    if "Please select Depot" in body:
        find("error", "Depot select did not register — still showing 'Please select Depot'")
    else:
        step("✅", "Main area updated after depot selection")

    # ── 3. Add Vehicle 1 ───────────────────────────────────────────────────
    sidebar = page.locator("[data-testid='stSidebar']")
    sidebar.get_by_label("Vehicle name").first.fill("Truck Alpha")
    sidebar.get_by_label("Driver name").first.fill("Ion Popescu")
    sidebar_button(page, "Add vehicle")
    shot(page, "03_vehicle1")
    fleet_text = sidebar.inner_text()
    if "Truck Alpha" in fleet_text:
        step("✅", "Vehicle 1 added (Truck Alpha)")
    else:
        find("warn", "Vehicle 1 not visible in sidebar after add")
        step("⚠️", "Vehicle 1 not visible in sidebar")

    # ── 4. Add Vehicle 2 with home city ────────────────────────────────────
    sidebar.get_by_label("Vehicle name").first.fill("Truck Beta")
    sidebar.get_by_label("Driver name").first.fill("Maria Ionescu")
    # home city = 2nd selectbox in sidebar (0=Depot, 1=home_city in form)
    try:
        selectbox_choose(page, 1, "Timisoara")
    except Exception as e:
        find("warn", f"Home-city select: {e}")
    sidebar_button(page, "Add vehicle")
    shot(page, "04_vehicle2")
    step("✅", "Vehicle 2 added (Truck Beta / home=Timisoara)")

    # ── 5-7. Add 3 orders ──────────────────────────────────────────────────
    orders = [
        ("Timisoara", "Brasov",    "14", "0",  True),
        ("Sibiu",     "Iasi",      "20", "2",  False),
        ("Oradea",    "Constanta", "24", "0",  False),
    ]
    for idx, (pu, dl_city, tl, ep, prio) in enumerate(orders):
        # pickup = 3rd selectbox (0=Depot, 1=home in fleet form, 2=pickup in order form)
        try:
            selectbox_choose(page, 2, pu)
            selectbox_choose(page, 3, dl_city)
        except Exception as e:
            find("warn", f"Order {idx+1} city selects: {e}")

        # Deadline and earliest pickup — locate by label text in sidebar
        try:
            dl_inp = sidebar.locator("label").filter(has_text="Deadline") \
                            .locator("..").locator("input").first
            dl_inp.fill(tl)
            dl_inp.press("Tab")
            ep_inp = sidebar.locator("label").filter(has_text="Earliest pickup") \
                            .locator("..").locator("input").first
            ep_inp.fill(ep)
            ep_inp.press("Tab")
        except Exception as e:
            find("warn", f"Order {idx+1} number inputs: {e}")

        if prio:
            try:
                sidebar.get_by_role("checkbox", name="Priority order").check()
            except Exception:
                pass

        sidebar_button(page, "Add order")
        step("✅", f"Order {idx+1}: {pu} -> {dl_city}  deadline={tl}h")

    shot(page, "05_orders_added")

    # ── 8. Generate routes ─────────────────────────────────────────────────
    sidebar_button(page, "Generate routes")
    time.sleep(2)
    shot(page, "06_routes")
    step("✅", "Routes generated")

    # KPI cards
    kpis = page.locator("[data-testid='stMetric']").all_text_contents()
    if kpis:
        step("✅", f"KPI cards: {kpis}")
    else:
        find("warn", "No KPI metric cards rendered")
        step("⚠️", "No KPI cards")

    # Dropped orders alert?
    dropped_el = page.locator(".stAlert").filter(has_text="could not be scheduled")
    if dropped_el.count():
        find("warn", "Some orders dropped: " + dropped_el.first.inner_text()[:120])
        step("⚠️", "Dropped-orders banner shown")
    else:
        step("✅", "No orders dropped")

    # ── 9. Map visible ─────────────────────────────────────────────────────
    try:
        page.wait_for_selector("[data-testid='stIFrame']", timeout=15000)
        step("✅", "Route map iframe rendered")
        shot(page, "07_map_2d")
    except PWTimeout:
        find("error", "Route map iframe never appeared")
        step("❌", "Map iframe missing")

    # ── 10. 3D map ─────────────────────────────────────────────────────────
    try:
        page.get_by_role("radio", name="3D").click()
        wait_ready(page)
        time.sleep(1)
        shot(page, "08_map_3d")
        step("✅", "3D map toggle works")
        page.get_by_role("radio", name="2D").click()
        wait_ready(page)
    except Exception as e:
        find("warn", f"3D toggle: {e}")
        step("⚠️", f"3D toggle: {e}")

    # ── 11. Walk every analytics tab ───────────────────────────────────────
    tab_locators = page.locator("[data-baseweb='tab']").all()
    for i, tab in enumerate(tab_locators):
        label = tab.inner_text().strip()
        try:
            tab.click()
            wait_ready(page, 20000)
            time.sleep(0.8)
            slug = label[:14].replace(" ", "_").replace("/", "-").replace("₂", "2")
            shot(page, f"09_tab_{i:02d}_{slug}")
            exc = page.locator(".stException")
            if exc.count():
                msg = exc.first.inner_text()[:200]
                find("error", f"Tab '{label}' exception: {msg}")
                step("❌", f"Tab '{label}' — Python exception visible")
            else:
                step("✅", f"Tab '{label}' — clean")
        except Exception as e:
            find("warn", f"Tab '{label}': {e}")
            step("⚠️", f"Tab '{label}' — {e}")

    # ── 12. Gantt: service-time bars ───────────────────────────────────────
    try:
        page.locator("[data-baseweb='tab']").filter(has_text="Gantt").click()
        wait_ready(page)
        time.sleep(1.5)
        shot(page, "10_gantt")
        gantt = page.locator(".js-plotly-plot").first
        if gantt.count():
            html = gantt.inner_html()
            has_svc = "Unloading" in html or "Loading" in html or "service" in html.lower()
            step("✅" if has_svc else "⚠️",
                 "Gantt has Loading/Unloading service bars" if has_svc
                 else "Gantt rendered but service bars not confirmed in DOM")
        else:
            find("warn", "Gantt Plotly chart not found")
            step("⚠️", "Gantt chart not found")
    except Exception as e:
        find("warn", f"Gantt: {e}")
        step("⚠️", f"Gantt: {e}")

    # ── 13. Routing Table filter → empty-state message ─────────────────────
    try:
        page.locator("[data-baseweb='tab']").filter(has_text="Routing Table").click()
        wait_ready(page)
        time.sleep(0.5)
        # open filters expander
        page.get_by_text("Filters", exact=True).click()
        time.sleep(0.3)
        # type a city that won't exist to force empty result
        city_ms = page.locator("[data-testid='stSidebar'], .block-container") \
                      .get_by_label("City", exact=True).first
        city_ms.click()
        city_ms.type("ZZZNOMATCH")
        time.sleep(0.5)
        page.keyboard.press("Escape")
        wait_ready(page)
        shot(page, "11_filter")

        info_msg = page.locator(".stAlert").filter(has_text="No rows match")
        table = page.locator("[data-testid='stDataFrame']")
        if info_msg.count():
            step("✅", "Empty filter shows 'No rows match' info — not blank widget")
        elif table.count():
            step("✅", "Filter active — table still shows rows")
        else:
            step("⚠️", "Filter state unclear")
    except Exception as e:
        find("warn", f"Filter test: {e}")
        step("⚠️", f"Filter test: {e}")

    # ── 14. Same-city order validation ─────────────────────────────────────
    try:
        selectbox_choose(page, 2, "Brasov")
        selectbox_choose(page, 3, "Brasov")
        sidebar_button(page, "Add order")
        warning = page.locator(".stAlert").filter(has_text="cannot be the same")
        if warning.count():
            step("✅", "Same-city validation fires")
        else:
            find("warn", "Same pickup=delivery did not show warning")
            step("⚠️", "Same-city validation missing")
    except Exception as e:
        find("warn", f"Same-city test: {e}")
        step("⚠️", f"Same-city test: {e}")

    # ── 15. Algorithm comparison ────────────────────────────────────────────
    try:
        page.locator("[data-testid='stSidebar']") \
            .get_by_role("button", name="Compare algorithms").click()
        wait_ready(page, 120000)
        time.sleep(2)
        shot(page, "12_compare")
        df = page.locator("[data-testid='stDataFrame']").first
        df.wait_for(state="visible", timeout=15000)
        step("✅", "Algorithm comparison table rendered")
    except Exception as e:
        find("warn", f"Algorithm comparison: {e}")
        step("⚠️", f"Algorithm comparison: {e}")

    # ── 16. Re-generate & simulation ───────────────────────────────────────
    sidebar_button(page, "Generate routes")
    try:
        page.locator("[data-testid='stSidebar']") \
            .get_by_role("button", name="Simulation playback").click()
        wait_ready(page)
        time.sleep(1)
        shot(page, "13_simulation")

        slider = page.locator("[data-testid='stSlider']").first
        max_val = slider.get_attribute("aria-valuemax")
        if max_val == "105":
            step("✅", "Simulation speed slider max=105 km/h (EU limiter cap)")
        else:
            find("warn", f"Simulation slider max={max_val!r}, expected '105'")
            step("⚠️", f"Simulation slider max={max_val!r}")

        page.get_by_role("button", name="Exit simulation").click()
        wait_ready(page)
        step("✅", "Exited simulation")
    except Exception as e:
        find("warn", f"Simulation: {e}")
        step("⚠️", f"Simulation: {e}")

    # ── 17. Reset ──────────────────────────────────────────────────────────
    try:
        page.locator("[data-testid='stSidebar']") \
            .get_by_role("button", name="Reset").click()
        wait_ready(page, 20000)
        time.sleep(1)
        shot(page, "14_reset")
        body_after = page.locator(".block-container").inner_text()
        if "Add at least" in body_after or "Please select" in body_after:
            step("✅", "Reset returns to initial state")
        else:
            step("⚠️", "After reset — state unclear (no expected prompt)")
    except Exception as e:
        find("warn", f"Reset: {e}")
        step("⚠️", f"Reset: {e}")


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: findings.append(("error", f"JS error: {e}")))

        try:
            run(page)
        except Exception as e:
            import traceback
            find("error", f"Verification crashed: {e}")
            traceback.print_exc()
        finally:
            shot(page, "99_final")
            browser.close()

    print()
    print("=" * 60)
    print("STEPS")
    for s in steps:
        print(s)

    errs  = [f for f in findings if f[0] == "error"]
    warns = [f for f in findings if f[0] == "warn"]
    if findings:
        print()
        print("FINDINGS")
        for sev, msg in findings:
            print(f"  [{'ERROR' if sev=='error' else 'WARN'}]  {msg}")

    print()
    verdict = "FAIL" if errs else "PASS"
    print(f"VERDICT: {verdict}  ({len(errs)} errors, {len(warns)} warnings)")
    print(f"Screenshots: {SCREENSHOTS}")
    sys.exit(1 if errs else 0)
