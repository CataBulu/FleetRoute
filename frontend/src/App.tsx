import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { FleetSection } from './components/FleetSection'
import { Icon } from './components/Icon'
import { OrdersSection } from './components/OrdersSection'
import { CompareCard, DroppedOrders, Kpis, ResultTabs } from './components/Results'
import { RouteMap } from './components/RouteMap'
import { Banner, CitySelect, Section } from './components/ui'
import { DEFAULT_FUEL_PRICE } from './format'
import type { City, CompareRow, Mode, Order, PlanRequest, PlanResult, Vehicle } from './types'

const MODES: { id: Mode; title: string; text: string }[] = [
  { id: 'economic', title: 'Economic', text: 'Shortest total distance' },
  { id: 'fast', title: 'Fast', text: 'Shortest total driving time' },
  { id: 'balanced', title: 'Balanced', text: 'Half distance, half time' },
]

/** useState that survives a page reload. Storage can be unavailable (private mode), so every access is guarded. */
function usePersistent<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(`fleetroute.${key}`)
      return raw ? (JSON.parse(raw) as T) : initial
    } catch {
      return initial
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(`fleetroute.${key}`, JSON.stringify(value))
    } catch {
      /* storage full or blocked: the app still works without it */
    }
  }, [key, value])
  return [value, setValue] as const
}

export default function App() {
  const [cities, setCities] = useState<City[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [depot, setDepot] = usePersistent<string | null>('depot', null)
  const [vehicles, setVehicles] = usePersistent<Vehicle[]>('vehicles', [])
  const [orders, setOrders] = usePersistent<Order[]>('orders', [])
  const [mode, setMode] = usePersistent<Mode>('mode', 'economic')
  const [returnToDepot, setReturnToDepot] = usePersistent('returnToDepot', true)
  const [allowSplit, setAllowSplit] = usePersistent('allowSplit', true)
  const [fuelPrice, setFuelPrice] = usePersistent('fuelPrice', DEFAULT_FUEL_PRICE)

  const [result, setResult] = useState<PlanResult | null>(null)
  const [resultKey, setResultKey] = useState('')
  const [comparison, setComparison] = useState<CompareRow[] | null>(null)
  const [simulate, setSimulate] = useState(false)
  const [busy, setBusy] = useState<'plan' | 'compare' | 'demo' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.cities().then(setCities).catch((e: Error) => setLoadError(e.message))
  }, [])

  const cityNames = useMemo(() => cities.map((c) => c.name), [cities])
  const maxCapacity = Math.max(0, ...vehicles.map((v) => v.capacity_kg))
  const oversized = orders.some((o) => o.demand_kg > maxCapacity) && vehicles.length > 0
  const request: PlanRequest | null = depot
    ? { depot, vehicles, orders, mode, return_to_depot: returnToDepot, allow_split: oversized && allowSplit }
    : null
  const requestKey = JSON.stringify(request)
  const stale = result !== null && requestKey !== resultKey
  const ready = !!depot && vehicles.length > 0 && orders.length > 0

  async function run<T>(kind: 'plan' | 'compare' | 'demo', task: () => Promise<T>) {
    setBusy(kind)
    setError(null)
    try {
      return await task()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const plan = () => run('plan', async () => {
    if (!request) return
    const res = await api.plan(request)
    setResult(res)
    setResultKey(requestKey)
    setComparison(null)
    setSimulate(false)
  })

  const compare = () => run('compare', async () => {
    if (request) setComparison(await api.compare(request))
  })

  const loadDemo = () => run('demo', async () => {
    const demo = await api.demo()
    setDepot(demo.depot)
    setVehicles(demo.vehicles)
    setOrders(demo.orders)
    setResult(null)
  })

  function reset() {
    setVehicles([])
    setOrders([])
    setResult(null)
    setComparison(null)
    setSimulate(false)
    setError(null)
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo"><Icon name="route" size={22} /></div>
          <div>
            <h1>FleetRoute</h1>
            <p>Delivery route planner for truck fleets</p>
          </div>
        </div>

        <div className="sidebar-body">
          <Section title="Depot">
            <CitySelect value={depot} onChange={setDepot} cities={cityNames} placeholder="Where trucks are based" />
            <button className="btn btn-ghost btn-sm" onClick={loadDemo} disabled={busy !== null}>
              {busy === 'demo' ? <span className="spinner" /> : <Icon name="sparkles" size={14} />} Load demo fleet and orders
            </button>
          </Section>
          <FleetSection vehicles={vehicles} setVehicles={setVehicles} cities={cityNames} />
          <OrdersSection orders={orders} setOrders={setOrders} cities={cityNames} />
          <Section title="Planning">
            <div className="segmented" role="radiogroup" aria-label="Routing mode">
              {MODES.map((m) => (
                <label key={m.id} className={mode === m.id ? 'active' : ''}>
                  <input type="radio" name="mode" checked={mode === m.id} onChange={() => setMode(m.id)} />
                  <span><b>{m.title}</b><small>{m.text}</small></span>
                </label>
              ))}
            </div>
            <label className="check">
              <input type="checkbox" checked={returnToDepot} onChange={(e) => setReturnToDepot(e.target.checked)} />
              Return to the depot after the last delivery
            </label>
            {oversized && (
              <label className="check">
                <input type="checkbox" checked={allowSplit} onChange={(e) => setAllowSplit(e.target.checked)} />
                Split loads larger than the biggest truck ({maxCapacity.toLocaleString()} kg)
              </label>
            )}
          </Section>
        </div>

        <div className="sidebar-actions">
          <button className="btn btn-primary btn-lg" disabled={!ready || busy !== null} onClick={plan}>
            {busy === 'plan' ? <><span className="spinner" /> Planning routes…</> : <><Icon name="route" /> Generate routes</>}
          </button>
          <div className="row">
            <button className="btn btn-ghost" disabled={!ready || busy !== null} onClick={compare}>
              {busy === 'compare' ? <span className="spinner" /> : <Icon name="compare" size={16} />} Compare
            </button>
            <button className="btn btn-ghost" disabled={!result || busy !== null} onClick={() => setSimulate(!simulate)}>
              <Icon name={simulate ? 'x' : 'play'} size={16} /> {simulate ? 'Stop' : 'Playback'}
            </button>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={reset}>Clear fleet and orders</button>
        </div>
      </aside>

      <main className="main">
        <header className="page-head">
          <div>
            <h2>Route planner</h2>
            <p>Multi-vehicle pickup and delivery across Romania, checked against EU Regulation 561/2006.</p>
          </div>
        </header>

        {loadError && <Banner tone="error" title="Could not load the city list">{loadError}</Banner>}
        {error && <Banner tone="error" title="Something went wrong">{error}</Banner>}
        {busy === 'compare' && <Banner tone="info" title="Comparing strategies">Each one gets up to 10 seconds, so this takes under a minute.</Banner>}
        {busy === 'plan' && (mode !== 'economic') && <Banner tone="info" title="Optimising">Fast and Balanced modes search for about 20 seconds.</Banner>}

        {!result && !comparison && (
          <div className="card hero">
            <div>
              <h3>{ready ? 'Ready to plan' : 'Plan your first routes'}</h3>
              <p>
                FleetRoute assigns each order to a truck and orders the stops, respecting capacity,
                delivery deadlines and driving-time rules.
              </p>
              <ol>
                <li className={depot ? 'muted' : ''}>Choose the depot where trucks are based</li>
                <li className={vehicles.length ? 'muted' : ''}>Add the vehicles in your fleet</li>
                <li className={orders.length ? 'muted' : ''}>Add pickup and delivery orders</li>
                <li>Press <b>Generate routes</b></li>
              </ol>
            </div>
            {!ready && (
              <button className="btn btn-secondary btn-lg" onClick={loadDemo} disabled={busy !== null}>
                <Icon name="sparkles" /> Try the demo data
              </button>
            )}
          </div>
        )}

        {comparison && <CompareCard rows={comparison} onClose={() => setComparison(null)} />}

        {stale && (
          <Banner tone="warn" title="The inputs changed since this plan was made"
            action={<button className="btn btn-primary btn-sm" onClick={plan} disabled={!ready || busy !== null}>Update routes</button>} />
        )}
        {result && <Kpis result={result} />}
        {result && <DroppedOrders result={result} />}

        <RouteMap cities={cities} depot={depot} result={result} simulate={simulate && !!result} onExitSimulation={() => setSimulate(false)} />

        {result && (
          <ResultTabs result={result} fuelPrice={fuelPrice} setFuelPrice={setFuelPrice} scenario={{ depot, vehicles, orders }} />
        )}
      </main>
    </div>
  )
}
