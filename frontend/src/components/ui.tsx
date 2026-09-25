import { useState, type ReactNode } from 'react'
import { Icon, type IconName } from './Icon'

export function Section({ title, count, defaultOpen = true, children }: {
  title: string
  count?: number
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="section">
      <button className="section-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <h3>
          {title}
          {count !== undefined && <span className="count">{count}</span>}
        </h3>
        <Icon name="chevron" size={16} className={`chev ${open ? 'open' : ''}`} />
      </button>
      {open && <div className="section-body">{children}</div>}
    </section>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field" title={hint}>
      <span>
        {label}
        {hint && <Icon name="info" size={13} />}
      </span>
      {children}
    </label>
  )
}

export function NumberInput({ value, onChange, min, max, step = 1 }: {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
}) {
  return (
    <input
      className="input"
      type="number"
      value={Number.isFinite(value) ? value : ''}
      min={min}
      max={max}
      step={step}
      onChange={(e) => onChange(e.target.value === '' ? NaN : Number(e.target.value))}
    />
  )
}

export function CitySelect({ value, onChange, cities, placeholder = 'Select a city', allowEmpty = false }: {
  value: string | null
  onChange: (v: string | null) => void
  cities: string[]
  placeholder?: string
  allowEmpty?: boolean
}) {
  return (
    <select className="select" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)}>
      <option value="" disabled={!allowEmpty}>{placeholder}</option>
      {cities.map((c) => (
        <option key={c} value={c}>{c}</option>
      ))}
    </select>
  )
}

export function Banner({ tone, icon, title, children, action }: {
  tone: 'info' | 'warn' | 'error' | 'success'
  icon?: IconName
  title?: string
  children?: ReactNode
  action?: ReactNode
}) {
  const fallback: Record<string, IconName> = { info: 'info', warn: 'alert', error: 'alert', success: 'check' }
  return (
    <div className={`banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon name={icon ?? fallback[tone]} />
      <div>
        {title && <b>{title}</b>}
        {children}
      </div>
      {action}
    </div>
  )
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  )
}

export function VehicleDot({ color }: { color: string }) {
  return <span className="veh-dot" style={{ background: color }} />
}
