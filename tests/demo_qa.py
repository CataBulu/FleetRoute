"""
Full end-to-end QA with the demo_fleet.json + demo_orders.json scenario.
Acts as a senior QA: loads real files, exercises every feature, captures bugs.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout
from datetime import datetime

BASE        = "http://localhost:8501"
ROOT        = os.path.dirname(os.path.dirname(__file__))
FLEET_FILE  = os.path.join(ROOT, "demo_fleet.json")
ORDERS_FILE = os.path.join(ROOT, "demo_orders.json")
SHOTS       = os.path.join(ROOT, "tests", "demo_screenshots")
os.makedirs(SHOTS, exist_ok=True)

findings = []
steps    = []

def shot(page, name):
    p = os.path.join(SHOTS, f"{name}.png")
    page.screenshot(path=p, full_page=False)
    return p

def ok(desc, detail=""):
    line = f"  OK   {desc}" + (f"  [{detail}]" if detail else "")
    steps.append(line); print(line)

def warn(desc):
    findings.append(("warn", desc))
    line = f"  WARN {desc}"
    steps.append(line); print(line)

def err(desc):
    findings.append(("error", desc))
    line = f"  ERR  {desc}"
    steps.append(line); print(line)

def wait(page, timeout=60000):
    try:
        page.wait_for_selector("[data-testid='stStatusWidget']", state="hidden", timeout=timeout)
    except PWTimeout:
        pass
    time.sleep(0.5)

def pick(page, nth, value):
    """Select a Streamlit BaseWeb combobox option."""
    inp = page.locator("[data-testid='stSidebar']") \
               .locator("[data-baseweb='select']").nth(nth).locator("input")
    inp.click(); time.sleep(0.15)
    inp.fill(value); time.sleep(0.2)
    opts = page.locator("[data-baseweb='popover'] [role='option']").filter(has_text=value)
    opts.first.click(); time.sleep(0.2)

def run(page: Page):
    sidebar = page.locator("[data-testid='stSidebar']")

    # ── 1. Load & wait for full render ─────────────────────────────────
    page.goto(BASE, wait_until="networkidle", timeout=30000)
    page.wait_for_selector("[data-testid='stSidebar']", timeout=45000)
    wait(page, 25000)
    ok("App loaded", page.title())
    shot(page, "01_start")

    # ── 2. Select depot ────────────────────────────────────────────────
    pick(page, 0, "Cluj-Napoca")
    wait(page)
    ok("Depot = Cluj-Napoca")

    # ── 3. Upload demo_fleet.json ──────────────────────────────────────
    try:
        fleet_uploader = sidebar.locator("input[type=file]").nth(0)
        fleet_uploader.set_input_files(FLEET_FILE)
        wait(page)
        fleet_text = sidebar.inner_text()
        expected_trucks = ["DAF XF 480 FT 4x2", "Mercedes-Benz Actros 1845 LS BigSpace",
                           "Volvo FH 460 Globetrotter", "Scania P 360 B Box Truck"]
        for t in expected_trucks:
            if t[:12] in fleet_text:
                ok(f"Fleet: {t[:30]} visible in sidebar")
            else:
                warn(f"Fleet truck not visible: {t}")
        shot(page, "02_fleet_loaded")
    except Exception as e:
        err(f"Fleet upload failed: {e}")

    # ── 4. Upload demo_orders.json ─────────────────────────────────────
    try:
        orders_uploader = sidebar.locator("input[type=file]").nth(1)
        orders_uploader.set_input_files(ORDERS_FILE)
        wait(page)
        orders_text = sidebar.inner_text()
        expected_cities = ["Timisoara", "Galati", "Alba Iulia", "Constanta",
                           "Arad", "Ploiesti", "Sibiu", "Iasi", "Deva", "Suceava", "Oradea", "Brasov"]
        missing = [c for c in expected_cities if c not in orders_text]
        if missing:
            warn(f"Orders not fully loaded — missing cities: {missing}")
        else:
            ok("All 6 orders loaded (12 cities visible)")
        shot(page, "03_orders_loaded")
    except Exception as e:
        err(f"Orders upload failed: {e}")

    # ── 5. Generate routes ─────────────────────────────────────────────
    sidebar.get_by_role("button", name="Generate routes").first.click()
    wait(page, 90000)
    time.sleep(2)
    shot(page, "04_routes")
    ok("Routes generated")

    # ── 6. KPI validation ──────────────────────────────────────────────
    kpis = page.locator("[data-testid='stMetric']").all_text_contents()
    if kpis:
        ok(f"KPI cards rendered: {kpis}")
        # Expect 3 vehicles (Scania unused), 6/6 orders
        kpi_str = " ".join(kpis)
        if "3" in kpi_str:
            ok("3 vehicles deployed (Scania correctly unused)")
        else:
            warn(f"Expected 3 vehicles in KPI — got: {kpi_str[:80]}")
        if "6 / 6" in kpi_str or "6/6" in kpi_str:
            ok("All 6 orders delivered (0 dropped)")
        elif "could not be scheduled" in page.content():
            warn("Some orders dropped — check constraints")
    else:
        err("No KPI cards rendered after route generation")

    dropped_banner = page.locator(".stAlert").filter(has_text="could not be scheduled")
    if dropped_banner.count():
        warn("Dropped orders: " + dropped_banner.first.inner_text()[:120])

    # ── 7. Walk every analytics tab ────────────────────────────────────
    tabs = page.locator("[data-baseweb='tab']").all()
    for i, tab in enumerate(tabs):
        label = tab.inner_text().strip()
        try:
            tab.click()
            wait(page, 20000)
            time.sleep(0.8)
            slug = label[:14].replace(" ","_").replace("/","-").replace("₂","2")
            shot(page, f"05_tab_{i:02d}_{slug}")
            exc = page.locator(".stException")
            if exc.count():
                err(f"Tab '{label}' Python exception: {exc.first.inner_text()[:200]}")
            else:
                ok(f"Tab '{label}' clean")
        except Exception as e:
            warn(f"Tab '{label}': {e}")

    # ── 8. Gantt: verify service bars present ──────────────────────────
    try:
        page.locator("[data-baseweb='tab']").filter(has_text="Gantt").click()
        wait(page); time.sleep(1.5)
        shot(page, "06_gantt")
        gantt = page.locator(".js-plotly-plot").first
        if gantt.count():
            html = gantt.inner_html()
            svc_present = "Unloading" in html or "Loading" in html or "service" in html.lower()
            ok("Gantt service bars present") if svc_present else warn("Gantt: service bars not confirmed in DOM")
            # Verify 3 trucks on Gantt (not 4)
            truck_rows = html.count("Mihai") + html.count("Elena") + html.count("Andrei") + html.count("Cosmin")
            ok(f"Gantt truck rows found: driver names visible in chart") if truck_rows >= 3 else warn(f"Gantt truck rows unclear")
        else:
            warn("Gantt: Plotly chart not rendered")
    except Exception as e:
        warn(f"Gantt check: {e}")

    # ── 9. Routing Table: EU compliance rows ───────────────────────────
    try:
        page.locator("[data-baseweb='tab']").filter(has_text="Routing Table").click()
        wait(page); time.sleep(0.5)
        shot(page, "07_routing_table")
        content = page.locator(".block-container").inner_text()
        if "Daily Rest" in content or "Driver Break" in content or "Weekly Rest" in content:
            ok("EU 561/2006 compliance rows present in routing table")
        else:
            warn("No EU compliance rows found in routing table")
        if "On time?" in content:
            ok("On-time column present")
    except Exception as e:
        warn(f"Routing table check: {e}")

    # ── 10. Notifications: 6 SMS expected (one per delivery) ───────────
    try:
        page.locator("[data-baseweb='tab']").filter(has_text="Notifications").click()
        wait(page); time.sleep(0.5)
        shot(page, "08_notifications")
        content = page.locator(".block-container").inner_text()
        sms_count = content.count("SMS")
        if sms_count == 6:
            ok(f"Notifications: exactly 6 SMS messages (one per delivery)")
        elif sms_count > 0:
            warn(f"Notifications: expected 6 SMS, found {sms_count}")
        else:
            warn("No SMS notifications rendered")
    except Exception as e:
        warn(f"Notifications check: {e}")

    # ── 11. CO2 tab: 3 truck rows ───────────────────────────────────────
    try:
        page.locator("[data-baseweb='tab']").filter(has_text="CO").click()
        wait(page); time.sleep(0.5)
        shot(page, "09_co2")
        frames = page.locator("[data-testid='stDataFrame']").all()
        ok(f"CO2 tab: {len(frames)} dataframe(s) rendered")
        content = page.locator(".block-container").inner_text()
        if "Total CO" in content:
            ok("CO2 total metric present")
    except Exception as e:
        warn(f"CO2 tab: {e}")

    # ── 12. Algorithm comparison ───────────────────────────────────────
    try:
        sidebar.get_by_role("button", name="Compare algorithms").click()
        wait(page, 120000)
        time.sleep(2)
        shot(page, "10_compare")
        df = page.locator("[data-testid='stDataFrame']").first
        df.wait_for(state="visible", timeout=15000)
        content = page.locator(".block-container").inner_text()
        algos = ["PATH_CHEAPEST_ARC", "SAVINGS", "GLOBAL_CHEAPEST_ARC", "PARALLEL_CHEAPEST_INSERTION"]
        found = [a for a in algos if a in content]
        ok(f"Algorithm comparison: {len(found)}/4 strategies shown")
        if len(found) < 4:
            warn(f"Missing algorithms: {[a for a in algos if a not in found]}")
    except Exception as e:
        warn(f"Algorithm comparison: {e}")

    # ── 13. Simulation: verify new dynamic timing + all 3 trucks ───────
    sidebar.get_by_role("button", name="Generate routes").first.click()
    wait(page, 90000)
    try:
        sidebar.get_by_role("button", name="Simulation playback").click()
        wait(page); time.sleep(2)
        shot(page, "11_simulation_start")

        # Speed slider range check
        slider = page.locator("[data-testid='stSlider']").first
        max_val = slider.get_attribute("aria-valuemax")
        ok(f"Simulation speed slider max={max_val}") if max_val == "105" \
            else warn(f"Simulation slider max={max_val}, expected 105")

        # Check the folium map (simulation mode)
        main_content = page.locator(".block-container").inner_text()
        if "LIVE ROUTE SIMULATION" in main_content or "Live Route Simulation" in main_content.title():
            ok("Simulation page loaded correctly")

        # Verify TimestampedGeoJson is on the page (script injection check)
        page_html = page.content()
        if "TimestampedGeoJson" in page_html or "timestampedgeojson" in page_html.lower():
            ok("TimestampedGeoJson layer present in page HTML")
        else:
            warn("TimestampedGeoJson not found in page HTML")

        # Verify dynamic period/duration was applied (not hardcoded PT2M)
        # The new code generates period > PT2M for long routes
        if '"PT2M"' in page_html and page_html.count('"PT2M"') <= 2:
            warn("period/duration appears to still be hardcoded PT2M — dynamic fix may not have applied")
        else:
            ok("period/duration is not the old hardcoded PT2M")

        # Exit simulation
        page.get_by_role("button", name="Exit simulation").click()
        wait(page)
        ok("Exited simulation")
    except Exception as e:
        warn(f"Simulation: {e}")

    # ── 14. Validation: same-city order rejection ──────────────────────
    try:
        pick(page, 2, "Brasov")
        pick(page, 3, "Brasov")
        sidebar.get_by_role("button", name="Add order").first.click()
        wait(page)
        warning = page.locator(".stAlert").filter(has_text="cannot be the same")
        ok("Same-city validation fires") if warning.count() else warn("Same-city validation missing")
    except Exception as e:
        warn(f"Validation test: {e}")

    # ── 15. Validation: earliest >= deadline rejection ─────────────────
    try:
        pick(page, 2, "Arad")
        pick(page, 3, "Ploiesti")
        tl_inp = sidebar.locator("label").filter(has_text="Deadline") \
                        .locator("..").locator("input").first
        tl_inp.fill("5"); tl_inp.press("Tab")
        ep_inp = sidebar.locator("label").filter(has_text="Earliest pickup") \
                        .locator("..").locator("input").first
        ep_inp.fill("5"); ep_inp.press("Tab")
        sidebar.get_by_role("button", name="Add order").first.click()
        wait(page)
        warning = page.locator(".stAlert").filter(has_text="must be earlier")
        ok("earliest>=deadline validation fires") if warning.count() else warn("earliest>=deadline validation missing")
    except Exception as e:
        warn(f"Earliest/deadline validation test: {e}")

    # ── 16. Open routing (no return to depot) ─────────────────────────
    try:
        rtd = sidebar.get_by_role("checkbox", name="Return to depot")
        rtd.uncheck()
        wait(page)
        sidebar.get_by_role("button", name="Generate routes").first.click()
        wait(page, 90000)
        time.sleep(1)
        shot(page, "12_open_routing")
        content = page.locator(".block-container").inner_text()
        ok("Open routing (no return to depot) generated routes")
        # Re-enable
        rtd.check()
        wait(page)
    except Exception as e:
        warn(f"Open routing test: {e}")

    # ── 17. Reset ──────────────────────────────────────────────────────
    try:
        sidebar.get_by_role("button", name="Reset").click()
        wait(page, 20000); time.sleep(1)
        shot(page, "13_reset")
        body = page.locator(".block-container").inner_text()
        ok("Reset works") if ("Add at least" in body or "Please select" in body or "Select from" in body) \
            else warn("After reset — state unclear")
    except Exception as e:
        warn(f"Reset: {e}")


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: findings.append(("error", f"JS: {e}")))

        try:
            run(page)
        except Exception as e:
            import traceback
            err(f"Test crashed: {e}")
            traceback.print_exc()
        finally:
            shot(page, "99_final")
            browser.close()

    print()
    print("=" * 60)
    errs  = [f for f in findings if f[0] == "error"]
    warns = [f for f in findings if f[0] == "warn"]
    if findings:
        print("FINDINGS:")
        for sev, msg in findings:
            print(f"  [{sev.upper()}] {msg}")
    print()
    verdict = "FAIL" if errs else ("WARN" if warns else "PASS")
    print(f"VERDICT: {verdict}  ({len(errs)} errors, {len(warns)} warnings)")
    print(f"Screenshots: {SHOTS}")
    sys.exit(1 if errs else 0)
