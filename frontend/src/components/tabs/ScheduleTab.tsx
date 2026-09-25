import { useMemo, useState } from 'react'
import { api, downloadJson } from '../../api'
import { hhmm, km, ron, routeColor } from '../../format'
import type { Order, PlanResult, Vehicle } from '../../types'
import { Icon } from '../Icon'
import { Banner, Field, NumberInput, Stat, VehicleDot } from '../ui'

const HGV_LIMITS: [string, number][] = [
  ['In towns and villages', 50],
  ['Motorway (A)', 90],
  ['Express / European (E) roads', 80],
  ['Other national and county roads', 70],
]

export function ScheduleTab({ result, fuelPrice, setFuelPrice, scenario }: {
  result: PlanResult
  fuelPrice: number
  setFuelPrice: (v: number) => void
  scenario: { depot: string | null; vehicles: Vehicle[]; orders: Order[] }
}) {
  const { schedule } = result
  const [vehicle, setVehicle] = useState('all')
  const [status, setStatus] = useState<'all' | 'on_time' | 'late'>('all')
  const [search, setSearch] = useState('')
  const [exporting, setExporting] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const price = Number.isFinite(fuelPrice) ? fuelPrice : 0

  const vehicles = useMemo(() => [...new Set(schedule.rows.map((r) => r.vehicle))], [schedule])
  const rows = schedule.rows.filter((r) =>
    (vehicle === 'all' || r.vehicle === vehicle) &&
    (status === 'all' || (status === 'on_time' ? r.on_time === true : r.on_time === false)) &&
    (!search || r.city.toLowerCase().includes(search.toLowerCase()) || r.description.toLowerCase().includes(search.toLowerCase())),
  )
  const totalFuelCost = schedule.fuel.reduce((s, f) => s + f.fuel_l * price, 0)

  async function exportReport(format: 'xlsx' | 'pdf') {
    setExporting(format)
    setExportError(null)
    try {
      await api.exportReport(format, result.routes, price)
    } catch (e) {
      setExportError((e as Error).message)
    } finally {
      setExporting(null)
    }
  }

  return (
    <>
      <details className="panel">
        <summary>EU 561/2006 and Romanian HGV rules applied to this plan</summary>
        <div>
          <div>
            <h4 style={{ marginBottom: 8 }}>Speed limits for trucks over 3.5 t</h4>
            <table>
              <tbody>
                {HGV_LIMITS.map(([road, limit]) => (
                  <tr key={road}><td>{road}</td><td className="num">{limit} km/h</td></tr>
                ))}
              </tbody>
            </table>
            <p className="hint" style={{ marginTop: 6 }}>A hardware speed limiter caps every HGV at 105 km/h (Directive 92/6/EEC).</p>
          </div>
          <div>
            <h4 style={{ marginBottom: 8 }}>Driving and rest times</h4>
            <ul>
              <li>45 min break after 4.5 h of driving</li>
              <li>At most 9 h driving per day (18 h for a two-driver crew)</li>
              <li>Daily rest of 11 h, or 9 h up to three times between weekly rests</li>
              <li>At most 56 h per week and 90 h over two weeks</li>
              <li>Every vehicle is assumed to carry a tachograph</li>
              <li>Weekend and holiday bans for trucks over 7.5 t are not modelled; check the ARR calendar</li>
            </ul>
          </div>
        </div>
      </details>

      <div className="filters">
        <Field label="Vehicle">
          <select className="select" value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
            <option value="all">All vehicles</option>
            {vehicles.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </Field>
        <Field label="Status">
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
            <option value="all">Any status</option>
            <option value="on_time">On time</option>
            <option value="late">Late</option>
          </select>
        </Field>
        <Field label="Search">
          <input className="input" placeholder="City or event" value={search} onChange={(e) => setSearch(e.target.value)} />
        </Field>
        <Field label="Fuel price (RON/L)">
          <NumberInput value={fuelPrice} min={0} step={0.1} onChange={setFuelPrice} />
        </Field>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>Vehicle</th><th>Event</th><th>City</th>
              <th className="num">Distance</th><th className="num">Avg speed</th>
              <th className="num">Elapsed</th><th className="num">Driving</th><th className="num">Breaks</th>
              <th className="num">Tacho left</th><th className="num">Fuel cost</th>
              <th className="num">Time left</th><th>On time</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.step} className={`kind-${r.kind}`}>
                <td className="num">{r.step}</td>
                <td><VehicleDot color={routeColor(r.vehicle_index)} />{r.vehicle}</td>
                <td>{r.description}</td>
                <td>{r.city}</td>
                <td className="num">{r.distance_km != null ? km(r.distance_km) : '–'}</td>
                <td className="num">{r.speed_kmh != null ? `${r.speed_kmh} km/h` : '–'}</td>
                <td className="num">{hhmm(r.elapsed_h)}</td>
                <td className="num">{hhmm(r.drive_h)}</td>
                <td className="num">{r.breaks}</td>
                <td className="num">{hhmm(r.tacho_remaining_h)}</td>
                <td className="num">{(r.fuel_l * price).toFixed(2)}</td>
                <td className="num">{hhmm(r.time_left_h)}</td>
                <td>
                  {r.on_time == null ? '–' : r.on_time
                    ? <span className="badge green">Yes</span>
                    : <span className="badge red">No</span>}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={13} className="muted" style={{ textAlign: 'center', padding: 24 }}>No rows match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="stats">
        <Stat label="Total distance" value={km(result.kpis.total_km)} />
        <Stat label="Vehicles used" value={result.kpis.vehicles_used} />
        <Stat label="Estimated fuel cost" value={ron(totalFuelCost)} />
        <Stat label="Driver breaks" value={schedule.rows.filter((r) => r.kind === 'break').length} />
      </div>

      {schedule.late.length === 0 && result.dropped.length === 0 ? (
        <Banner tone="success" title="Every delivery arrives on time." />
      ) : schedule.late.length > 0 && (
        <div>
          <h4 style={{ marginBottom: 8 }}>Late deliveries</h4>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Vehicle</th><th>Order</th><th className="num">Delay</th></tr></thead>
              <tbody>
                {schedule.late.map((l, i) => (
                  <tr key={i}><td>{l.vehicle}</td><td>#{l.order}</td><td className="num">{hhmm(l.delay_h)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {schedule.biweekly_violations.length > 0 && (
        <Banner tone="error" title="Two-week driving limit (90 h) exceeded">
          {schedule.biweekly_violations.map((v) => `${v.vehicle}: ${hhmm(v.drive_h)}`).join(' · ')}
        </Banner>
      )}

      {schedule.speed_violations.length > 0 ? (
        <Banner tone="warn" title={`${schedule.speed_violations.length} road segment(s) average more than 90 km/h`}>
          That is above the HGV motorway limit, so the planned time on these segments is optimistic:{' '}
          {schedule.speed_violations.map((v) => `${v.city} (${v.speed_kmh} km/h)`).join(', ')}.
        </Banner>
      ) : (
        <Banner tone="success" title="All road segments respect the Romanian HGV speed limits." />
      )}

      <div>
        <h4 style={{ marginBottom: 8 }}>Fuel per vehicle</h4>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Vehicle</th><th className="num">Distance</th><th className="num">Consumption</th><th className="num">Fuel</th><th className="num">Cost</th></tr>
            </thead>
            <tbody>
              {schedule.fuel.map((f, i) => (
                <tr key={i}>
                  <td><VehicleDot color={routeColor(i)} />{f.vehicle}</td>
                  <td className="num">{km(f.distance_km)}</td>
                  <td className="num">{f.fuel_l100km} L/100 km</td>
                  <td className="num">{f.fuel_l.toFixed(1)} L</td>
                  <td className="num">{ron(f.fuel_l * price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="btn-row">
        <button className="btn btn-secondary" disabled={!!exporting} onClick={() => exportReport('xlsx')}>
          {exporting === 'xlsx' ? <span className="spinner" /> : <Icon name="download" size={16} />} Excel report
        </button>
        <button className="btn btn-secondary" disabled={!!exporting} onClick={() => exportReport('pdf')}>
          {exporting === 'pdf' ? <span className="spinner" /> : <Icon name="download" size={16} />} PDF report
        </button>
        <button className="btn btn-ghost" onClick={() => downloadJson({ ...scenario, routes: result.routes }, 'fleetroute-scenario.json')}>
          <Icon name="save" size={16} /> Save scenario
        </button>
        <span className="hint" style={{ alignSelf: 'center' }}>Reports always cover the full plan, whatever the filters show.</span>
      </div>
      {exportError && <Banner tone="error" title="Export failed">{exportError}</Banner>}
    </>
  )
}
