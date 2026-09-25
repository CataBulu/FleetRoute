# FleetRoute Optimizer

FleetRoute plans delivery routes for a fleet of vehicles. You give it a depot, a list
of trucks and a list of orders, and it works out which vehicle carries which order and
in what sequence, while staying inside vehicle capacity, delivery deadlines and the
EU/Romanian rules on driver working time. It runs in the browser as a Streamlit app and
uses Google OR-Tools for the routing.

The road network covers Romanian cities. Distances and travel times come from a
precomputed road graph that ships with the project, so the optimization runs on your own
machine without calling any external service.

## What you need before you start

The only thing you install by hand is Python. Everything the app depends on is pulled in
later with a single pip command.

- **Python 3.11**, 64-bit. Newer 3.x versions usually work too, but the app was built and
  tested on 3.11.
- **An internet connection** the first time you install (pip downloads the packages) and
  while you use the app (the map background tiles are served by OpenStreetMap). The route
  calculation itself works offline.
- **Windows** if you want the `run.bat` launcher. On Linux or macOS you start the app with
  one command instead, shown further down.

There is no database to set up, no account to register and no API key to paste in.

### Installing Python (skip if you already have 3.11)

1. Download Python 3.11 from <https://www.python.org/downloads/>.
2. Run the installer. On the very first screen, tick **Add python.exe to PATH** before you
   click Install. This step is easy to miss and the terminal will not find Python without
   it.
3. When it finishes, open a new terminal and check it:

   ```
   python --version
   ```

   You should see `Python 3.11.x`.

## Installing the app

Open a terminal inside the FleetRoute folder. On Windows, hold Shift, right-click an empty
spot in the folder and choose *Open in Terminal* (or *Open PowerShell window here*).

Create a virtual environment. This keeps FleetRoute's packages in their own folder so they
do not mix with anything else on your computer:

```
python -m venv .venv
```

Activate it:

```
.venv\Scripts\activate
```

On Linux or macOS run `source .venv/bin/activate` instead. When it is active the prompt
shows `(.venv)` at the start of the line.

Install the dependencies:

```
pip install -r requirements.txt
```

This reads `requirements.txt` and downloads everything the app uses. The first run takes a
couple of minutes, mostly because OR-Tools is a large download.

### What gets installed and why

| Package | What it does in the app |
|---------|-------------------------|
| streamlit | Runs the whole interface in the browser |
| ortools | Google's solver that computes the routes |
| networkx | Builds the road network graph and finds shortest paths between cities |
| folium, streamlit-folium | The interactive 2D maps with depots, stops and routes |
| plotly | The dashboard charts for cost, fuel, emissions and driver workload |
| pandas | Holds the route and results tables |
| xlsxwriter | Writes the Excel export |
| fpdf2 | Writes the PDF report |
| python-dotenv | Optional. Loads a `.env` file if you have one; not needed for normal use |

The 3D map view uses pydeck, which Streamlit installs on its own, so it is not listed
separately above.

## Running the app

### Windows, with the launcher

Double-click `run.bat`, or run it from the terminal:

```
run.bat
```

It starts the server and opens your browser at <http://localhost:8501> as soon as the app
is ready. Keep the terminal window open while you work; close it or press Ctrl+C to stop
the app.

### Any platform, direct command

With the virtual environment active:

```
streamlit run main.py
```

Then open <http://localhost:8501> if the browser does not open by itself.

## A short walkthrough

1. **Pick a depot.** In the sidebar, choose the city the vehicles start from.
2. **Add vehicles.** Give each one a name, a capacity in kilograms and a fuel consumption.
   You can add as many as you need and they do not have to be the same.
3. **Add orders.** Each order has a pickup city, a delivery city, a quantity and a
   deadline.
4. **Press Generate routes.** The app assigns orders to vehicles, sequences the stops and
   draws the result on the map.
5. **Read the results.** The route table lists every leg with its distance and time and
   flags any driver-hours problems. The dashboard tab has the cost, fuel and emissions
   charts, and you can export the plan to Excel or PDF.

### Trying it with the sample data

If you just want to see it run without typing anything in:

1. In the sidebar, use *Upload fleet config* and pick `demo_fleet.json`.
2. Use *Upload orders config* and pick `demo_orders.json`.
3. Press **Generate routes**.

## If something does not work

- **`python` is not recognised.** Python is not on PATH. Reinstall it with *Add python.exe
  to PATH* ticked, then open a fresh terminal.
- **PowerShell refuses to run the activate script** ("running scripts is disabled on this
  system"). Run this once in the same window and then activate again:

  ```
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ```

- **Port 8501 is already in use.** An earlier instance is still running. The Windows
  launcher stops it for you; otherwise close the old terminal, or start on another port
  with `streamlit run main.py --server.port 8502`.
- **The map area is blank.** That is the OpenStreetMap tiles failing to load, usually a
  dropped internet connection. The routing still works; only the map background is
  affected.

## Project files

| File | Purpose |
|------|---------|
| `main.py` | The user interface and overall flow |
| `vrp_solver.py` | Route optimization with OR-Tools |
| `graph_builder.py` | Builds the road network graph |
| `map_view.py` | 2D and 3D maps and the route simulation |
| `table_view.py` | Route table and driver-hours checks |
| `dashboard.py` | Charts, reports and exports |
| `coords.json`, `roads.json` | City coordinates and the road network |
| `demo_fleet.json`, `demo_orders.json` | Sample data for a quick test |
| `requirements.txt` | The packages pip installs |
| `run.bat` | Windows launcher |
