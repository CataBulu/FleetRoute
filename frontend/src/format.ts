import type { Order, Vehicle } from './types'

export const ROUTE_COLORS = [
  '#2563EB', '#F97316', '#16A34A', '#9333EA', '#DC2626',
  '#0891B2', '#DB2777', '#CA8A04', '#4F46E5', '#059669',
]

export const routeColor = (index: number) => ROUTE_COLORS[index % ROUTE_COLORS.length]

export const MAX_CAPACITY_KG = 40_000
export const DEFAULT_FUEL_PRICE = 7.5

/** 1.5 -> "01:30", -0.25 -> "-00:15" */
export function hhmm(hours: number | null | undefined): string {
  if (hours == null) return '–'
  const neg = hours < 0
  const v = Math.abs(hours)
  let h = Math.floor(v)
  let m = Math.round((v - h) * 60)
  if (m === 60) {
    h += 1
    m = 0
  }
  return `${neg ? '-' : ''}${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** Routes are dispatched today at 08:00; timeline offsets are hours from then. */
export function dispatchTime(): Date {
  const d = new Date()
  d.setHours(8, 0, 0, 0)
  return d
}

export function clock(offsetH: number, multiDay: boolean, base = dispatchTime()): string {
  const t = new Date(base.getTime() + offsetH * 3_600_000)
  const time = t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  if (!multiDay) return time
  const day = Math.floor((t.getTime() - new Date(base).setHours(0, 0, 0, 0)) / 86_400_000) + 1
  return `Day ${day} · ${time}`
}

export const km = (v: number) => `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })} km`
export const kg = (v: number) => `${v.toLocaleString()} kg`
export const ron = (v: number) => `${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} RON`

export const vehicleLabel = (v: Pick<Vehicle, 'name' | 'driver'>) => (v.driver ? `${v.name} (${v.driver})` : v.name)

// Accept configs saved by the original Streamlit version (Romanian keys) as well as the current format.
type Raw = Record<string, unknown>
const pick = (o: Raw, ...keys: string[]) => keys.map((k) => o[k]).find((v) => v !== undefined && v !== null)

export function toVehicle(o: Raw, cityNames: Set<string>): Vehicle {
  const home = pick(o, 'home_city') as string | undefined
  return {
    name: String(pick(o, 'name', 'nume') ?? 'Truck'),
    driver: String(pick(o, 'driver', 'driver_name') ?? ''),
    capacity_kg: Math.min(Number(pick(o, 'capacity_kg', 'capacitate') ?? 0), MAX_CAPACITY_KG),
    fuel_l100km: Number(pick(o, 'fuel_l100km') ?? 30),
    crew: Boolean(pick(o, 'crew', 'echipaj')),
    count: Math.max(1, Number(pick(o, 'count', 'numar') ?? 1)),
    home_city: home && cityNames.has(home) ? home : null,
  }
}

export function toOrder(o: Raw): Order {
  return {
    pickup: String(o.pickup ?? ''),
    delivery: String(o.delivery ?? ''),
    demand_kg: Number(pick(o, 'demand_kg', 'demand') ?? 0),
    deadline_h: Number(pick(o, 'deadline_h', 'time_limit_hrs') ?? 24),
    earliest_pickup_h: Number(pick(o, 'earliest_pickup_h', 'earliest_pickup_hrs') ?? 0),
    priority: Boolean(o.priority),
  }
}
