import { useState } from 'react'
import { downloadJson } from '../api'
import { MAX_CAPACITY_KG, kg, toVehicle } from '../format'
import type { Vehicle } from '../types'
import { Icon } from './Icon'
import { ImportButton } from './ImportButton'
import { CitySelect, Field, NumberInput, Section } from './ui'

const CAPACITY_HINT =
  'Maximum authorised mass in Romania (OUG 195/2002): 2 axles 18 t, 3 axles 26 t, 4 axles 32 t, ' +
  '5-axle semi-trailer 40 t. Heavier loads need an ARR exceptional-transport permit.'

const blank = (): Vehicle => ({
  name: 'Truck', driver: '', capacity_kg: 25000, fuel_l100km: 30, crew: false, count: 1, home_city: null,
})

export function FleetSection({ vehicles, setVehicles, cities }: {
  vehicles: Vehicle[]
  setVehicles: (v: Vehicle[]) => void
  cities: string[]
}) {
  const [draft, setDraft] = useState<Vehicle>(blank)
  const [editing, setEditing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof Vehicle>(key: K, value: Vehicle[K]) => setDraft({ ...draft, [key]: value })

  function save() {
    if (!draft.name.trim()) return setError('Give the vehicle a name.')
    if (!(draft.capacity_kg > 0 && draft.capacity_kg <= MAX_CAPACITY_KG))
      return setError(`Capacity must be between 1 and ${MAX_CAPACITY_KG.toLocaleString()} kg.`)
    if (!(draft.fuel_l100km > 0)) return setError('Fuel consumption must be positive.')
    if (!(draft.count >= 1)) return setError('Quantity must be at least 1.')
    const clean = { ...draft, name: draft.name.trim(), driver: draft.driver.trim(), count: Math.floor(draft.count) }
    setVehicles(editing === null ? [...vehicles, clean] : vehicles.map((v, i) => (i === editing ? clean : v)))
    cancel()
  }

  function cancel() {
    setDraft(blank())
    setEditing(null)
    setError(null)
  }

  function edit(i: number) {
    setDraft(vehicles[i])
    setEditing(i)
    setError(null)
  }

  function remove(i: number) {
    setVehicles(vehicles.filter((_, j) => j !== i))
    if (editing === i) cancel()
    else if (editing !== null && editing > i) setEditing(editing - 1)
  }

  const trucks = vehicles.reduce((n, v) => n + v.count, 0)

  return (
    <Section title="Fleet" count={trucks}>
      <div className="form-card">
        <div className="field-grid">
          <Field label="Vehicle name">
            <input className="input" value={draft.name} onChange={(e) => set('name', e.target.value)} />
          </Field>
          <Field label="Driver">
            <input className="input" value={draft.driver} placeholder="Optional" onChange={(e) => set('driver', e.target.value)} />
          </Field>
          <Field label="Capacity (kg)" hint={CAPACITY_HINT}>
            <NumberInput value={draft.capacity_kg} min={1} max={MAX_CAPACITY_KG} step={100} onChange={(v) => set('capacity_kg', v)} />
          </Field>
          <Field label="Fuel (L/100 km)">
            <NumberInput value={draft.fuel_l100km} min={1} step={0.5} onChange={(v) => set('fuel_l100km', v)} />
          </Field>
          <Field label="Quantity">
            <NumberInput value={draft.count} min={1} onChange={(v) => set('count', v)} />
          </Field>
          <Field label="Starts from" hint="Where the truck is now. It drives to the depot first.">
            <CitySelect value={draft.home_city} onChange={(v) => set('home_city', v)} cities={cities} placeholder="The depot" allowEmpty />
          </Field>
        </div>
        <label className="check">
          <input type="checkbox" checked={draft.crew} onChange={(e) => set('crew', e.target.checked)} />
          Two-driver crew (18 h driving per day)
        </label>
        {error && <div className="form-error">{error}</div>}
        <div className="form-actions">
          {editing !== null && <button className="btn btn-ghost" onClick={cancel}>Cancel</button>}
          <button className="btn btn-secondary" onClick={save}>
            <Icon name={editing === null ? 'plus' : 'check'} size={16} />
            {editing === null ? 'Add vehicle' : 'Save changes'}
          </button>
        </div>
      </div>

      {vehicles.length === 0 ? (
        <p className="empty-note">No vehicles yet. Add one above or load the demo data.</p>
      ) : (
        <div className="list">
          {vehicles.map((v, i) => (
            <div key={i} className={`item ${editing === i ? 'editing' : ''}`}>
              <div className="item-main">
                <div className="item-title">{v.name}{v.count > 1 && ` ×${v.count}`}</div>
                <div className="item-sub">
                  <span>{kg(v.capacity_kg)}</span>
                  <span>{v.fuel_l100km} L/100 km</span>
                  {v.driver && <span>{v.driver}</span>}
                  {v.crew && <span className="badge blue">Crew of 2</span>}
                  {v.home_city && <span className="badge">From {v.home_city}</span>}
                </div>
              </div>
              <div className="item-actions">
                <button className="icon-btn" title="Edit" aria-label={`Edit ${v.name}`} onClick={() => edit(i)}><Icon name="edit" size={16} /></button>
                <button className="icon-btn danger" title="Remove" aria-label={`Remove ${v.name}`} onClick={() => remove(i)}><Icon name="trash" size={16} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="btn-row">
        <ImportButton
          label="Import"
          onData={(data) => {
            if (!Array.isArray(data)) throw new Error('A fleet file must contain a JSON list.')
            const names = new Set(cities)
            setVehicles(data.map((d) => toVehicle(d, names)).filter((v) => v.capacity_kg > 0))
          }}
        />
        <button className="btn btn-ghost btn-sm" disabled={!vehicles.length} onClick={() => downloadJson(vehicles, 'fleet.json')}>
          <Icon name="download" size={14} /> Export
        </button>
      </div>
    </Section>
  )
}
