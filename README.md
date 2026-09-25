# FleetRoute

**A delivery route planner for truck fleets.** You enter a depot, your trucks and a list of
pickup-and-delivery orders. FleetRoute decides which truck carries which load, in what
order, and when. It keeps to truck capacity, delivery deadlines and EU driving-time rules.

The optimisation uses Google OR-Tools behind a Python / Starlette API. The interface is
React + TypeScript with an interactive Leaflet map. The road network of 59 Romanian cities
ships with the project, so planning runs entirely offline. Only the map background comes
from OpenStreetMap.

![FleetRoute overview: KPIs and the planned routes on the map](docs/screenshots/overview.png)

## Highlights

- **Vehicle routing with real constraints.** Pickup-and-delivery pairs on the same truck,
  capacity per vehicle, delivery deadlines, earliest pickup times and priority orders.
  All of it is modelled with the OR-Tools routing solver, with a greedy fallback.
- **Three planning goals.** Shortest distance, shortest driving time, or a weighted balance
  of both, plus a side-by-side comparison of four first-solution strategies.
- **Driver-hours compliance.** Every route is replayed against EU Regulation 561/2006:
  45-minute breaks, reduced and regular daily rests, weekly rests, the 56 h / 90 h
  weekly limits, and two-driver crews. Road segments are also checked against Romanian
  truck speed limits.
- **Load splitting.** Orders heavier than the biggest truck are split across several
  vehicles.
- **Route playback.** Trucks move across the map on their planned schedule, stopping for
  loading and unloading.
- **Operational dashboards.** Journey timeline, Gantt-style schedule, driver workload,
  cost breakdown, CO₂ footprint, alerts and customer notifications.
- **Exports.** Excel and PDF reports, plus JSON import and export of fleets, orders and
  whole scenarios.

## Screenshots

| Route playback | Journey timeline |
|---|---|
| ![Trucks moving along their routes](docs/screenshots/playback.png) | ![Step-by-step journey per truck](docs/screenshots/journey.png) |

| EU 561/2006 routing table | Schedule chart |
|---|---|
| ![Routing table with breaks, rests and deadlines](docs/screenshots/routing-table.png) | ![Gantt-style schedule per truck](docs/screenshots/schedule-chart.png) |

| Cost breakdown | Driver workload |
|---|---|
| ![Fuel, driver pay and vehicle wear](docs/screenshots/costs.png) | ![Driving hours against the EU allowance](docs/screenshots/workload.png) |

## Tech stack

| Layer | Technologies |
|-------|--------------|
| Frontend | React 19, TypeScript, Vite, Leaflet / react-leaflet, hand-written SVG charts |
| Backend | Python 3.11+, Starlette, Uvicorn |
| Optimisation | Google OR-Tools (constraint solver), NetworkX (Dijkstra shortest paths) |
| Reports | xlsxwriter, fpdf2 |
| Quality | pytest (47 tests), TypeScript strict type-checking, oxlint |

## Architecture

```mermaid
flowchart LR
    UI["React + TypeScript<br/>(Vite)"] -- "JSON over /api" --> API["Starlette API<br/>validation"]
    API --> PLAN["planning.py<br/>split loads, expand fleet"]
    PLAN --> SOLVER["solver.py<br/>OR-Tools model"]
    SOLVER --> GRAPH["graph.py<br/>road network + Dijkstra"]
    API --> RULES["compliance.py<br/>EU 561/2006 replay"]
    API --> ANALYTICS["analytics.py<br/>KPIs, timeline, CO₂"]
    API --> EXPORTS["exports.py<br/>Excel / PDF"]
    UI --> MAP["Leaflet map<br/>OpenStreetMap tiles"]
```

- The **solver** builds a pickup-and-delivery model: a capacity dimension, and a time
  dimension with loading time and waiting allowed. Deadlines and earliest-pickup windows
  are time-window constraints. Orders sit in drop penalties, weighted up for priority
  orders.
- The **compliance engine** is independent of the solver. It walks each planned route
  segment by segment and inserts breaks and rests where the regulation requires them. It
  then reports slack against each deadline, late deliveries and limit violations.
- Solver calls run in a worker thread (`run_in_threadpool`), so the API stays responsive
  during longer optimisations.
- In production, Starlette serves the built frontend and the API from a single port.

## Getting started

Requirements: **Python 3.11+** and **Node.js 20.19+**.

### Windows

| Script | What it does |
|--------|--------------|
| `dev.bat` | Starts the API (auto-reload) and the Vite dev server in two windows, then opens the app |
| `run.bat` | Builds the interface once and serves everything at http://localhost:8000 |

Both scripts create the Python environment and install the packages on first run.

### macOS / Linux

```bash
./dev.sh
```

### Manual setup

```bash
python -m venv .venv
```

```bash
.venv/bin/pip install -r backend/requirements-dev.txt
```

```bash
npm --prefix frontend install
```

Then run the API and the frontend in two terminals:

```bash
.venv/bin/python -m uvicorn fleetroute.app:app --app-dir backend --reload
```

```bash
npm --prefix frontend run dev
```

Open http://localhost:5173 and click **Try the demo data**, then **Generate routes**.

On Windows, use `.venv\Scripts\` instead of `.venv/bin/`.

## Tests

```bash
.venv/bin/python -m pytest backend
```

```bash
npm --prefix frontend run typecheck
```

```bash
npm --prefix frontend run lint
```

The backend suite has 47 tests:
- solver behaviour on a small fixed network: deadlines, waiting for pickup windows,
  priorities, open routing, fallback
- the EU rules engine
- input normalisation and load splitting
- the HTTP API end to end on the real road network

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/cities` | Selectable cities with coordinates |
| GET | `/api/demo` | Sample depot, fleet and orders |
| POST | `/api/plan` | Solve a plan. Returns routes, map lines, KPIs, schedule, timeline and alerts |
| POST | `/api/compare` | Solve with each first-solution strategy and compare the results |
| POST | `/api/export/{xlsx,pdf}` | Report for a set of planned routes |

<details>
<summary>Example plan request</summary>

```json
{
  "depot": "Brasov",
  "vehicles": [{ "name": "Truck 1", "driver": "Ana", "capacity_kg": 24000, "fuel_l100km": 30,
                 "crew": false, "count": 1, "home_city": null }],
  "orders": [{ "pickup": "Arad", "delivery": "Iasi", "demand_kg": 8000, "deadline_h": 36,
               "earliest_pickup_h": 0, "priority": false }],
  "mode": "economic",
  "return_to_depot": true,
  "allow_split": false
}
```

Times are hours after dispatch (08:00 on the planning day). Invalid input returns
`400` with a readable `error` message.
</details>

## Project structure

```
backend/
  fleetroute/
    app.py          Starlette routes and input validation
    solver.py       OR-Tools model, greedy fallback, strategy comparison
    planning.py     Input normalisation, load splitting, fleet expansion
    compliance.py   EU 561/2006 and Romanian HGV rules
    analytics.py    KPIs, workload, CO2, alerts, timeline
    exports.py      Excel and PDF reports
    graph.py        Road network and shortest paths
    data/           City coordinates, road network, demo data
  tests/
frontend/
  src/
    App.tsx         Planner state and layout
    components/     Sidebar forms, map and playback, result tabs
    api.ts          Typed API client
    types.ts        Types matching the API responses
docs/screenshots/
dev.bat, dev.sh     Start backend and frontend for development
run.bat             Build once and serve on one port
```

## Modelling assumptions

- Distances and driving times come from the bundled road graph (shortest path by
  distance). Map lines connect the cities along that path rather than the exact road
  geometry.
- Every pickup and delivery takes 2 hours of loading or unloading.
- The optimiser plans against delivery deadlines using pure driving time. Mandatory
  breaks and rests are added afterwards by the compliance check. That is why the routing
  table can flag a delivery as late that the optimiser accepted: it shows the real
  impact of driving-time rules on a plan.
- Weekend and holiday driving bans for trucks over 7.5 t are not modelled.

---

Built by [Catalin](https://github.com/CataBulu). Map data ©
[OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
