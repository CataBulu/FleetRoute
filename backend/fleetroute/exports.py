"""Excel and PDF reports built from a driver-hours schedule."""
from io import BytesIO

import xlsxwriter
from fpdf import FPDF


def fmt_hhmm(hours):
    if hours is None:
        return "-"
    neg, v = hours < 0, abs(hours)
    h, m = int(v), int(round((v - int(v)) * 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{'-' if neg else ''}{h:02d}:{m:02d}"


def _on_time(row):
    return "-" if row["on_time"] is None else ("YES" if row["on_time"] else "NO")


ROUTING_COLUMNS = [
    ("Step", lambda r, p: r["step"]),
    ("Vehicle", lambda r, p: r["vehicle"]),
    ("Description", lambda r, p: r["description"]),
    ("City", lambda r, p: r["city"]),
    ("Distance (km)", lambda r, p: r["distance_km"] if r["distance_km"] is not None else "-"),
    ("Speed (km/h)", lambda r, p: r["speed_kmh"] if r["speed_kmh"] is not None else "-"),
    ("Time elapsed", lambda r, p: fmt_hhmm(r["elapsed_h"])),
    ("Drive time", lambda r, p: fmt_hhmm(r["drive_h"])),
    ("Breaks", lambda r, p: r["breaks"]),
    ("Tacho remaining", lambda r, p: fmt_hhmm(r["tacho_remaining_h"])),
    ("Fuel cost (RON)", lambda r, p: round(r["fuel_l"] * p, 2)),
    ("Time left", lambda r, p: fmt_hhmm(r["time_left_h"])),
    ("On time?", lambda r, p: _on_time(r)),
]


def _fuel_rows(schedule, fuel_price):
    return [{**f, "cost": round(f["fuel_l"] * fuel_price, 2)} for f in schedule["fuel"]]


def build_excel(schedule, fuel_price):
    out = BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True})
    bold = wb.add_format({"bold": True, "bg_color": "#DBEAFE"})

    def sheet(name, headers, rows):
        ws = wb.add_worksheet(name)
        ws.write_row(0, 0, headers, bold)
        for i, row in enumerate(rows, start=1):
            ws.write_row(i, 0, row)
        ws.set_column(0, len(headers) - 1, 18)

    sheet("Routing", [c for c, _ in ROUTING_COLUMNS],
          [[fn(r, fuel_price) for _, fn in ROUTING_COLUMNS] for r in schedule["rows"]])
    if schedule["late"]:
        sheet("Delays", ["Vehicle", "Order", "Delay"],
              [[d["vehicle"], d["order"], fmt_hhmm(d["delay_h"])] for d in schedule["late"]])
    sheet("Fuel", ["Vehicle", "Distance (km)", "Fuel (L/100km)", "Fuel used (L)", "Cost (RON)"],
          [[f["vehicle"], f["distance_km"], f["fuel_l100km"], f["fuel_l"], f["cost"]]
           for f in _fuel_rows(schedule, fuel_price)])
    wb.close()
    return out.getvalue()


_LATIN1 = str.maketrans({
    "ă": "a", "Ă": "A", "â": "a", "Â": "A", "î": "i", "Î": "I", "ș": "s", "Ș": "S", "ş": "s",
    "Ş": "S", "ț": "t", "Ț": "T", "ţ": "t", "Ţ": "T", "—": "-", "–": "-", "’": "'", "‘": "'",
    "“": '"', "”": '"', "…": "...", "→": "->",
})


def _latin1(value):
    """fpdf2's built-in Helvetica only covers Latin-1."""
    s = str(value if value is not None else "").translate(_LATIN1)
    return s.encode("latin-1", errors="ignore").decode("latin-1")


def build_pdf(schedule, fuel_price, vehicles_used):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "FleetRoute - Route report", new_x="LMARGIN", new_y="NEXT")
    delivered = sum(1 for r in schedule["rows"]
                    if r["kind"] == "arrive" and r["description"].endswith("(delivery)"))
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Vehicles: {vehicles_used}   Deliveries: {delivered}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    def heading(text):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)

    heading("Route summary")
    widths = [10, 40, 55, 30, 25, 25]
    pdf.set_fill_color(219, 234, 254)
    for w, h in zip(widths, ["#", "Vehicle", "Description", "City", "Elapsed", "On time?"]):
        pdf.cell(w, 5, h, border=1, fill=True)
    pdf.ln()
    for r in schedule["rows"]:
        values = [r["step"], _latin1(r["vehicle"])[:22], _latin1(r["description"])[:30],
                  _latin1(r["city"])[:18], fmt_hhmm(r["elapsed_h"]), _on_time(r)]
        for w, v in zip(widths, values):
            pdf.cell(w, 4, str(v), border=1)
        pdf.ln()

    if schedule["late"]:
        heading("Late deliveries")
        for d in schedule["late"]:
            pdf.cell(0, 5, _latin1(f"  {d['vehicle']}  order {d['order']}  delay {fmt_hhmm(d['delay_h'])}"),
                     new_x="LMARGIN", new_y="NEXT")

    fuel = _fuel_rows(schedule, fuel_price)
    if fuel:
        heading("Fuel cost estimate")
        for f in fuel:
            pdf.cell(0, 5, _latin1(f"  {f['vehicle']}: {f['distance_km']} km, {f['fuel_l']} L, {f['cost']} RON"),
                     new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, f"  Total: {round(sum(f['cost'] for f in fuel), 2)} RON", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
