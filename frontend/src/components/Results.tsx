import { useState, type ReactNode } from 'react'
import { kg, km } from '../format'
import type { CompareRow, Order, PlanResult, Vehicle } from '../types'
import { Icon, type IconName } from './Icon'
import { AlertsTab, Co2Tab, CostTab, WorkloadTab } from './tabs/InsightTabs'
import { ScheduleTab } from './tabs/ScheduleTab'
import { GanttTab, JourneyTab, NotificationsTab } from './tabs/TimelineTabs'
import { Banner } from './ui'

export function Kpis({ result }: { result: PlanResult }) {
  const k = result.kpis
  const cards: [IconName, string, ReactNode][] = [
    ['truck', 'Vehicles on the road', k.vehicles_used],
    ['box', 'Orders delivered', <>{k.orders_delivered} <small>/ {k.orders_total}</small></>],
    ['route', 'Total distance', km(k.total_km)],
    ['gauge', 'Average per vehicle', km(k.avg_km_per_vehicle)],
  ]
  return (
    <div className="kpis">
      {cards.map(([icon, label, value]) => (
        <div className="card kpi" key={label}>
          <span className="kpi-icon"><Icon name={icon} size={20} /></span>
          <div>
            <div className="kpi-label">{label}</div>
            <div className="kpi-value">{value}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

export function DroppedOrders({ result }: { result: PlanResult }) {
  if (!result.dropped.length) return null
  return (
    <Banner tone="error" title={`${result.dropped.length} order${result.dropped.length > 1 ? 's' : ''} could not be planned`}>
      The fleet cannot deliver {result.dropped.length > 1 ? 'these' : 'this'} within the deadline or capacity:{' '}
      {result.dropped.map((d) => `${d.pickup} → ${d.delivery} (${kg(d.demand_kg)}, ${d.deadline_h} h)`).join('; ')}.
      Try a later deadline, a bigger truck, or another vehicle.
    </Banner>
  )
}

type TabId = 'journey' | 'schedule' | 'alerts' | 'workload' | 'costs' | 'co2' | 'gantt' | 'notifications'

export function ResultTabs({ result, fuelPrice, setFuelPrice, scenario }: {
  result: PlanResult
  fuelPrice: number
  setFuelPrice: (v: number) => void
  scenario: { depot: string | null; vehicles: Vehicle[]; orders: Order[] }
}) {
  const [tab, setTab] = useState<TabId>('journey')
  const tabs: [TabId, IconName, string, number?][] = [
    ['journey', 'route', 'Journey'],
    ['schedule', 'list', 'Routing table'],
    ['alerts', 'alert', 'Alerts', result.alerts.length || undefined],
    ['workload', 'clock', 'Driver workload'],
    ['costs', 'coins', 'Costs'],
    ['co2', 'leaf', 'CO₂'],
    ['gantt', 'calendar', 'Schedule chart'],
    ['notifications', 'bell', 'Notifications'],
  ]
  return (
    <div className="card">
      <div className="tabs" role="tablist">
        {tabs.map(([id, icon, label, badge]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>
            <Icon name={icon} size={15} /> {label}
            {badge !== undefined && <span className="badge red">{badge}</span>}
          </button>
        ))}
      </div>
      <div className="tab-panel" role="tabpanel">
        {tab === 'journey' && <JourneyTab timeline={result.timeline} />}
        {tab === 'schedule' && <ScheduleTab result={result} fuelPrice={fuelPrice} setFuelPrice={setFuelPrice} scenario={scenario} />}
        {tab === 'alerts' && <AlertsTab alerts={result.alerts} />}
        {tab === 'workload' && <WorkloadTab stats={result.vehicle_stats} />}
        {tab === 'costs' && <CostTab result={result} fuelPrice={fuelPrice} setFuelPrice={setFuelPrice} />}
        {tab === 'co2' && <Co2Tab stats={result.vehicle_stats} />}
        {tab === 'gantt' && <GanttTab timeline={result.timeline} />}
        {tab === 'notifications' && <NotificationsTab timeline={result.timeline} />}
      </div>
    </div>
  )
}

export function CompareCard({ rows, onClose }: { rows: CompareRow[]; onClose: () => void }) {
  const best = [...rows].sort((a, b) => a.orders_dropped - b.orders_dropped || a.total_km - b.total_km)[0]
  return (
    <div className="card">
      <div className="card-head">
        <h3><Icon name="compare" /> Algorithm comparison</h3>
        <button className="btn btn-ghost btn-sm" onClick={onClose}><Icon name="x" size={14} /> Close</button>
      </div>
      <div className="tab-panel">
        <p className="hint">
          The same plan solved with each OR-Tools first-solution strategy (10 s limit each).
          The highlighted row delivers the most orders with the shortest total distance.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Strategy</th><th className="num">Vehicles</th><th className="num">Total distance</th><th className="num">Dropped</th><th className="num">Solve time</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.algorithm} className={r === best ? 'best' : ''}>
                  <td>{r.algorithm.replaceAll('_', ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}{r === best && <span className="badge green" style={{ marginLeft: 8 }}>Best</span>}</td>
                  <td className="num">{r.vehicles_used}</td>
                  <td className="num">{km(r.total_km)}</td>
                  <td className="num">{r.orders_dropped}</td>
                  <td className="num">{r.solve_time_s.toFixed(2)} s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
