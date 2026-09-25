import { useState } from 'react'
import { downloadJson } from '../api'
import { kg, toOrder } from '../format'
import type { Order } from '../types'
import { Icon } from './Icon'
import { ImportButton } from './ImportButton'
import { CitySelect, Field, NumberInput, Section } from './ui'

const blank = (): Order => ({
  pickup: '', delivery: '', demand_kg: 1000, deadline_h: 24, earliest_pickup_h: 0, priority: false,
})

export function OrdersSection({ orders, setOrders, cities }: {
  orders: Order[]
  setOrders: (o: Order[]) => void
  cities: string[]
}) {
  const [draft, setDraft] = useState<Order>(blank)
  const [editing, setEditing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof Order>(key: K, value: Order[K]) => setDraft({ ...draft, [key]: value })

  function save() {
    if (!draft.pickup || !draft.delivery) return setError('Choose both a pickup and a delivery city.')
    if (draft.pickup === draft.delivery) return setError('Pickup and delivery must be different cities.')
    if (!(draft.demand_kg > 0)) return setError('Quantity must be positive.')
    if (!(draft.deadline_h > 0)) return setError('Deadline must be positive.')
    if (!(draft.earliest_pickup_h >= 0) || draft.earliest_pickup_h >= draft.deadline_h)
      return setError(`Earliest pickup must be between 0 and the deadline (${draft.deadline_h} h).`)
    setOrders(editing === null ? [...orders, draft] : orders.map((o, i) => (i === editing ? draft : o)))
    cancel()
  }

  function cancel() {
    // keep the cities so several orders from the same place are quick to enter
    setDraft((d) => ({ ...blank(), pickup: editing === null ? d.pickup : '' }))
    setEditing(null)
    setError(null)
  }

  function remove(i: number) {
    setOrders(orders.filter((_, j) => j !== i))
    if (editing === i) cancel()
    else if (editing !== null && editing > i) setEditing(editing - 1)
  }

  return (
    <Section title="Orders" count={orders.length}>
      <div className="form-card">
        <div className="field-grid">
          <Field label="Pickup">
            <CitySelect value={draft.pickup || null} onChange={(v) => set('pickup', v ?? '')} cities={cities} placeholder="From…" />
          </Field>
          <Field label="Delivery">
            <CitySelect value={draft.delivery || null} onChange={(v) => set('delivery', v ?? '')} cities={cities} placeholder="To…" />
          </Field>
          <Field label="Quantity (kg)">
            <NumberInput value={draft.demand_kg} min={1} step={100} onChange={(v) => set('demand_kg', v)} />
          </Field>
          <Field label="Deadline (h)" hint="Hours after dispatch (08:00) by which the load must be delivered.">
            <NumberInput value={draft.deadline_h} min={1} onChange={(v) => set('deadline_h', v)} />
          </Field>
          <Field label="Earliest pickup (h)" hint="The load is not ready before this many hours after dispatch.">
            <NumberInput value={draft.earliest_pickup_h} min={0} onChange={(v) => set('earliest_pickup_h', v)} />
          </Field>
          <label className="check" style={{ alignSelf: 'end', height: 36 }}>
            <input type="checkbox" checked={draft.priority} onChange={(e) => set('priority', e.target.checked)} />
            Priority
          </label>
        </div>
        {error && <div className="form-error">{error}</div>}
        <div className="form-actions">
          {editing !== null && <button className="btn btn-ghost" onClick={cancel}>Cancel</button>}
          <button className="btn btn-secondary" onClick={save}>
            <Icon name={editing === null ? 'plus' : 'check'} size={16} />
            {editing === null ? 'Add order' : 'Save changes'}
          </button>
        </div>
      </div>

      {orders.length === 0 ? (
        <p className="empty-note">No orders yet.</p>
      ) : (
        <div className="list">
          {orders.map((o, i) => (
            <div key={i} className={`item ${editing === i ? 'editing' : ''}`}>
              <div className="item-main">
                <div className="item-title">{i + 1}. {o.pickup} → {o.delivery}</div>
                <div className="item-sub">
                  <span>{kg(o.demand_kg)}</span>
                  <span>within {o.deadline_h} h</span>
                  {o.earliest_pickup_h > 0 && <span>ready at {o.earliest_pickup_h} h</span>}
                  {o.priority && <span className="badge amber">Priority</span>}
                </div>
              </div>
              <div className="item-actions">
                <button className="icon-btn" title="Edit" aria-label={`Edit order ${i + 1}`} onClick={() => { setDraft(o); setEditing(i); setError(null) }}>
                  <Icon name="edit" size={16} />
                </button>
                <button className="icon-btn danger" title="Remove" aria-label={`Remove order ${i + 1}`} onClick={() => remove(i)}>
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="btn-row">
        <ImportButton
          label="Import"
          onData={(data) => {
            if (!Array.isArray(data)) throw new Error('An orders file must contain a JSON list.')
            const known = new Set(cities)
            const parsed = data.map(toOrder)
            const valid = parsed.filter((o) => known.has(o.pickup) && known.has(o.delivery) && o.pickup !== o.delivery)
            setOrders(valid)
            if (valid.length < parsed.length)
              throw new Error(`Skipped ${parsed.length - valid.length} order(s) with unknown or identical cities.`)
          }}
        />
        <button className="btn btn-ghost btn-sm" disabled={!orders.length} onClick={() => downloadJson(orders, 'orders.json')}>
          <Icon name="download" size={14} /> Export
        </button>
      </div>
    </Section>
  )
}
