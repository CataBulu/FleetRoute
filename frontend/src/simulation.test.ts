import { describe, expect, it } from 'vitest'
import { buildTrack, positionAt, SERVICE_TIME_H } from './simulation'
import type { LatLng, Route, StepType } from './types'

const step = (type: StepType, coords: LatLng, duration_h: number) => ({ type, city: type, coords, distance_km: 0, duration_h })

// depot (0,0) -> 5 h -> pickup (0,10) -> 5 h -> delivery (10,10) -> 4 h -> back at (10,0)
const route: Route = {
  vehicle: { name: 'Truck', driver: '', capacity_kg: 24000, fuel_l100km: 30, crew: false, count: 1, home_city: null },
  depot: 'depot',
  steps: [step('depart', [0, 0], 0), step('pickup', [0, 10], 5), step('delivery', [10, 10], 5), step('return', [10, 0], 4)],
}

describe('buildTrack', () => {
  it('adds the loading time at every pickup and delivery', () => {
    const track = buildTrack(route)
    expect(track.end).toBe(5 + SERVICE_TIME_H + 5 + SERVICE_TIME_H + 4)
    expect(track.legs.map((l) => [l.start, l.end])).toEqual([[0, 5], [5, 7], [7, 12], [12, 14], [14, 18]])
  })
})

describe('positionAt', () => {
  const track = buildTrack(route)

  it('starts at the first stop', () => {
    expect(positionAt(track, 0)).toEqual([0, 0])
  })

  it('moves along a leg in proportion to the time driven', () => {
    expect(positionAt(track, 2.5)).toEqual([0, 5])
    expect(positionAt(track, 9.5)).toEqual([5, 10])
  })

  it('waits at the pickup while the truck is loaded', () => {
    expect(positionAt(track, 6)).toEqual([0, 10])
  })

  it('stays at the last stop after the route ends', () => {
    expect(positionAt(track, 100)).toEqual([10, 0])
  })

  it('stays put for a route with a single stop', () => {
    const idle = buildTrack({ ...route, steps: [route.steps[0]] })
    expect(idle.end).toBe(0)
    expect(positionAt(idle, 3)).toEqual([0, 0])
  })
})

describe('following the road shape', () => {
  // an L-shaped road from (0, 0) to (10, 10) round the corner at (0, 10), driven in 5 h
  const bent: Route = {
    ...route,
    steps: [step('depart', [0, 0], 0), { ...step('pickup', [10, 10], 5), geometry: [[0, 0], [0, 10], [10, 10]] }],
  }
  const track = buildTrack(bent)

  it('keeps the step time, split along the road', () => {
    expect(track.end).toBe(5 + SERVICE_TIME_H)
    expect(track.legs.filter((l) => l.from !== l.to).at(-1)?.end).toBe(5)
  })

  it('is at the corner halfway through, not on the straight line', () => {
    const [lat, lon] = positionAt(track, 2.5)
    expect(lat).toBeCloseTo(0, 5)
    expect(lon).toBeCloseTo(10, 5)
  })

  it('reaches the stop when the drive ends', () => {
    expect(positionAt(track, 5)).toEqual([10, 10])
  })
})
