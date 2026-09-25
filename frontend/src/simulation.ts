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

/** Turn a route into timed legs (hours after dispatch), including the 2 h stops
 *  at every pickup and delivery. Same timing as the Gantt and journey views. */
export function buildTrack(route: Route): Track {
  const legs: Leg[] = []
  let t = 0
  const steps = route.steps
  for (let i = 1; i < steps.length; i++) {
    const prev = steps[i - 1].coords
    const s = steps[i]
    if (s.duration_h > 0) {
      legs.push({ from: prev, to: s.coords, start: t, end: t + s.duration_h })
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
  if (!track.legs.length || t <= 0) return track.start
  for (const leg of track.legs) {
    if (t <= leg.end) {
      const f = leg.end > leg.start ? (t - leg.start) / (leg.end - leg.start) : 1
      return [leg.from[0] + (leg.to[0] - leg.from[0]) * f, leg.from[1] + (leg.to[1] - leg.from[1]) * f]
    }
  }
  return track.legs[track.legs.length - 1].to
}
