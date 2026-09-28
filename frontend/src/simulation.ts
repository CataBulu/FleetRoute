import type { LatLng, Route } from './types'

export const SERVICE_TIME_H = 2 // loading/unloading, matches the backend

interface Leg {
  from: LatLng
  to: LatLng
  start: number
  end: number
}

export interface Track {
  legs: Leg[]
  end: number
  start: LatLng
}

/** Rough ground distance for splitting a step's time along its road shape. */
function flatKm(a: LatLng, b: LatLng) {
  const x = (b[1] - a[1]) * Math.cos(((a[0] + b[0]) / 2) * (Math.PI / 180))
  const y = b[0] - a[0]
  return Math.hypot(x, y) * 111.2
}

/** Turn a route into timed legs (hours after dispatch), including the 2 h stops
 *  at every pickup and delivery. Same timing as the Gantt and journey views.
 *  A step with a road shape is split into one leg per piece of road, each taking
 *  its share of the step's time, so trucks follow the roads drawn on the map. */
export function buildTrack(route: Route): Track {
  const legs: Leg[] = []
  let t = 0
  const steps = route.steps
  for (let i = 1; i < steps.length; i++) {
    const s = steps[i]
    if (s.duration_h > 0) {
      const path = s.geometry && s.geometry.length > 1 ? s.geometry : [steps[i - 1].coords, s.coords]
      const lengths = path.slice(1).map((p, j) => flatKm(path[j], p))
      const total = lengths.reduce((sum, l) => sum + l, 0)
      let at = t
      lengths.forEach((l, j) => {
        const end = j === lengths.length - 1 ? t + s.duration_h : at + (total ? (s.duration_h * l) / total : s.duration_h / lengths.length)
        legs.push({ from: path[j], to: path[j + 1], start: at, end })
        at = end
      })
      t += s.duration_h
    }
    if (s.type === 'pickup' || s.type === 'delivery') {
      legs.push({ from: s.coords, to: s.coords, start: t, end: t + SERVICE_TIME_H })
      t += SERVICE_TIME_H
    }
  }
  return { legs, end: t, start: steps[0].coords }
}

export function positionAt(track: Track, t: number): LatLng {
  const legs = track.legs
  if (!legs.length || t <= 0) return track.start
  if (t >= legs[legs.length - 1].end) return legs[legs.length - 1].to
  // legs are in time order: find the first one that ends at or after t
  let lo = 0
  let hi = legs.length - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (legs[mid].end < t) lo = mid + 1
    else hi = mid
  }
  const leg = legs[lo]
  const f = leg.end > leg.start ? (t - leg.start) / (leg.end - leg.start) : 1
  return [leg.from[0] + (leg.to[0] - leg.from[0]) * f, leg.from[1] + (leg.to[1] - leg.from[1]) * f]
}
