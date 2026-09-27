import { describe, expect, it } from 'vitest'
import { clock, hhmm, MAX_CAPACITY_KG, ROUTE_COLORS, routeColor, toOrder, toVehicle, vehicleLabel } from './format'

describe('hhmm', () => {
  it('formats hours as hours:minutes', () => {
    expect(hhmm(0)).toBe('00:00')
    expect(hhmm(1.5)).toBe('01:30')
    expect(hhmm(26.75)).toBe('26:45')
  })

  it('keeps the sign for time already missed', () => {
    expect(hhmm(-0.25)).toBe('-00:15')
  })

  it('rounds up to the next hour instead of showing :60', () => {
    expect(hhmm(1.9999)).toBe('02:00')
  })

  it('shows a dash when there is no value', () => {
    expect(hhmm(null)).toBe('–')
    expect(hhmm(undefined)).toBe('–')
  })
})

describe('clock', () => {
  const dispatch = new Date(2026, 0, 5, 8, 0) // 08:00 on the planning day

  it('counts calendar days from the dispatch day', () => {
    expect(clock(0, true, dispatch)).toMatch(/^Day 1 · 08[:.]00$/)
    expect(clock(15.5, true, dispatch)).toMatch(/^Day 1 · 23[:.]30$/)
    expect(clock(16, true, dispatch)).toMatch(/^Day 2 · 00[:.]00$/)
    expect(clock(41, true, dispatch)).toMatch(/^Day 3 · 01[:.]00$/)
  })

  it('leaves the day out for plans that finish on the dispatch day', () => {
    expect(clock(2.5, false, dispatch)).toMatch(/^10[:.]30$/)
  })
})

describe('route colours', () => {
  it('gives each of the first ten routes its own colour, then repeats the palette', () => {
    expect(new Set(ROUTE_COLORS).size).toBe(ROUTE_COLORS.length)
    expect(routeColor(3)).toBe(ROUTE_COLORS[3])
    expect(routeColor(ROUTE_COLORS.length)).toBe(ROUTE_COLORS[0])
  })
})

describe('vehicleLabel', () => {
  it('adds the driver in brackets when there is one', () => {
    expect(vehicleLabel({ name: 'Volvo FH', driver: 'Ana' })).toBe('Volvo FH (Ana)')
    expect(vehicleLabel({ name: 'Volvo FH', driver: '' })).toBe('Volvo FH')
  })
})

describe('toVehicle', () => {
  const cities = new Set(['Arad', 'Brasov'])

  it('reads fleets saved by the original Streamlit version (Romanian keys)', () => {
    expect(toVehicle({ nume: 'Volvo', capacitate: 24000, echipaj: true, numar: 2 }, cities)).toEqual({
      name: 'Volvo', driver: '', capacity_kg: 24000, fuel_l100km: 30, crew: true, count: 2, home_city: null,
    })
  })

  it('caps capacity at the legal maximum and keeps at least one truck', () => {
    const v = toVehicle({ name: 'Too big', capacity_kg: 90000, count: 0 }, cities)
    expect(v.capacity_kg).toBe(MAX_CAPACITY_KG)
    expect(v.count).toBe(1)
  })

  it('keeps a starting city only if it is on the map', () => {
    expect(toVehicle({ name: 'A', capacity_kg: 1000, home_city: 'Arad' }, cities).home_city).toBe('Arad')
    expect(toVehicle({ name: 'A', capacity_kg: 1000, home_city: 'Atlantis' }, cities).home_city).toBeNull()
  })
})

describe('toOrder', () => {
  it('reads legacy keys and fills in the defaults', () => {
    expect(toOrder({ pickup: 'Arad', delivery: 'Iasi', demand: 5000, time_limit_hrs: 36 })).toEqual({
      pickup: 'Arad', delivery: 'Iasi', demand_kg: 5000, deadline_h: 36, earliest_pickup_h: 0, priority: false,
    })
  })

  it('reads the current format as is', () => {
    const order = { pickup: 'Arad', delivery: 'Iasi', demand_kg: 8000, deadline_h: 48, earliest_pickup_h: 6, priority: true }
    expect(toOrder(order)).toEqual(order)
  })
})
