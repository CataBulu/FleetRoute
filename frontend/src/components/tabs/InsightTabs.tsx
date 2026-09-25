import { useState } from 'react'
import { km, ron, routeColor } from '../../format'
import type { Alert, PlanResult, VehicleStat } from '../../types'
import { Banner, Field, NumberInput, Stat, VehicleDot } from '../ui'

export function AlertsTab({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length)
    return <Banner tone="success" title="No active alerts">All drivers are within their limits and every order is planned.</Banner>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Severity</th><th>Type</th><th>Vehicle</th><th>Detail</th></tr></thead>
        <tbody>
          {alerts.map((a, i) => (
            <tr key={i}>
              <td><span className={`badge ${a.severity === 'high' ? 'red' : 'amber'}`}>{a.severity === 'high' ? 'High' : 'Medium'}</span></td>
              <td>{a.type}</td>
              <td>{a.vehicle ?? '–'}</td>
              <td style={{ whiteSpace: 'normal' }}>{a.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function WorkloadTab({ stats }: { stats: VehicleStat[] }) {
  return (
    <>
      <p className="hint">
        Total driving compared with the EU 561/2006 allowance for the days the trip takes
        (9 h per day for one driver, 18 h for a crew of two). Day-by-day checks are in the routing table.
      </p>
      <div className="bars">
        {stats.map((s) => {
          const share = s.workload_share
          const color = share < 0.7 ? '#22C55E' : share < 0.95 ? '#F59E0B' : '#EF4444'
          return (
            <div className="bar-row" key={s.index}>
              <div className="bar-label"><VehicleDot color={routeColor(s.index)} />{s.vehicle}{s.crew && ' · crew'}</div>
              <div className="bar-track"><div className="bar-fill" style={{ width: `${share * 100}%`, background: color }} /></div>
              <div className="bar-value">
                {s.drive_h.toFixed(1)} h of {s.trip_limit_h} h{s.work_days > 1 && ` · ${s.work_days} days`}
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}

const COST_COLORS = ['#2B7DE9', '#38BDF8', '#A5B4FC']

function Donut({ parts }: { parts: { label: string; value: number }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  const r = 70
  const c = 2 * Math.PI * r
  const lengths = parts.map((p) => (p.value / total) * c)
  const offsets = lengths.map((_, i) => lengths.slice(0, i).reduce((s, l) => s + l, 0))
  return (
    <svg viewBox="0 0 200 200" width="200" height="200" role="img" aria-label="Cost breakdown">
      <circle cx="100" cy="100" r={r} fill="none" stroke="#EAF3FD" strokeWidth="28" />
      {parts.map((p, i) => (
        <circle key={p.label} cx="100" cy="100" r={r} fill="none" stroke={COST_COLORS[i]} strokeWidth="28"
          strokeDasharray={`${lengths[i]} ${c - lengths[i]}`} strokeDashoffset={-offsets[i]} transform="rotate(-90 100 100)">
          <title>{`${p.label}: ${ron(p.value)}`}</title>
        </circle>
      ))}
      <text x="100" y="96" textAnchor="middle" fontSize="12" fill="#46607F">Total</text>
      <text x="100" y="116" textAnchor="middle" fontSize="15" fontWeight="700" fill="#0F2742">
        {Math.round(total).toLocaleString()} RON
      </text>
    </svg>
  )
}

export function CostTab({ result, fuelPrice, setFuelPrice }: {
  result: PlanResult
  fuelPrice: number
  setFuelPrice: (v: number) => void
}) {
  const [wage, setWage] = useState(40)
  const [depreciation, setDepreciation] = useState(0.15)
  const n = (v: number) => (Number.isFinite(v) ? v : 0)
  const stats = result.vehicle_stats
  const parts = [
    { label: 'Fuel', value: stats.reduce((s, v) => s + v.fuel_l, 0) * n(fuelPrice) },
    { label: 'Driver pay', value: stats.reduce((s, v) => s + v.drive_h, 0) * n(wage) },
    { label: 'Vehicle wear', value: stats.reduce((s, v) => s + v.distance_km, 0) * n(depreciation) },
  ]
  const total = parts.reduce((s, p) => s + p.value, 0)

  return (
    <>
      <div className="filters">
        <Field label="Fuel price (RON/L)"><NumberInput value={fuelPrice} min={0} step={0.1} onChange={setFuelPrice} /></Field>
        <Field label="Driver pay (RON/h)"><NumberInput value={wage} min={0} step={5} onChange={setWage} /></Field>
        <Field label="Vehicle wear (RON/km)"><NumberInput value={depreciation} min={0} step={0.05} onChange={setDepreciation} /></Field>
      </div>
      <div className="cost-layout">
        <Donut parts={parts} />
        <div className="table-wrap">
          <table>
            <thead><tr><th>Category</th><th className="num">Cost</th><th className="num">Share</th></tr></thead>
            <tbody>
              {parts.map((p, i) => (
                <tr key={p.label}>
                  <td><VehicleDot color={COST_COLORS[i]} />{p.label}</td>
                  <td className="num">{ron(p.value)}</td>
                  <td className="num">{total ? ((p.value / total) * 100).toFixed(1) : '0.0'}%</td>
                </tr>
              ))}
              <tr><td><b>Total</b></td><td className="num"><b>{ron(total)}</b></td><td className="num">100%</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <p className="hint">Driver pay counts driving hours only. Vehicle wear is a flat rate per kilometre.</p>
    </>
  )
}

export function Co2Tab({ stats }: { stats: VehicleStat[] }) {
  const co2 = stats.reduce((s, v) => s + v.co2_kg, 0)
  return (
    <>
      <div className="stats">
        <Stat label="Total CO₂" value={`${co2.toFixed(1)} kg`} />
        <Stat label="Trees to absorb it in a year" value={(co2 / 21).toFixed(1)} />
        <Stat label="Carbon cost at €50 per tonne" value={`€${(co2 * 0.05).toFixed(2)}`} />
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Vehicle</th><th className="num">Distance</th><th className="num">Fuel</th><th className="num">CO₂</th><th className="num">Trees</th></tr>
          </thead>
          <tbody>
            {stats.map((s) => (
              <tr key={s.index}>
                <td><VehicleDot color={routeColor(s.index)} />{s.vehicle}</td>
                <td className="num">{km(s.distance_km)}</td>
                <td className="num">{s.fuel_l.toFixed(1)} L</td>
                <td className="num">{s.co2_kg.toFixed(1)} kg</td>
                <td className="num">{s.trees.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">Diesel emits about 2.68 kg of CO₂ per litre. A mature tree absorbs roughly 21 kg a year.</p>
    </>
  )
}
