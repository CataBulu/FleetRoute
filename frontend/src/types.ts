// Mirrors the JSON returned by the Starlette API (backend/fleetroute/app.py).

export type Mode = 'economic' | 'fast' | 'balanced'
export type LatLng = [number, number]

export interface City {
  name: string
  lat: number
  lon: number
}

export interface Vehicle {
  name: string
  driver: string
  capacity_kg: number
  fuel_l100km: number
  crew: boolean
  count: number
  home_city: string | null
}

export interface Order {
  pickup: string
  delivery: string
  demand_kg: number
  deadline_h: number
  earliest_pickup_h: number
  priority: boolean
}

export interface PlannedOrder extends Order {
  id: number
  part: number | null
}

export type StepType = 'depart' | 'transit' | 'pickup' | 'delivery' | 'return' | 'home_depart' | 'arrive_depot'

export interface Step {
  type: StepType
  city: string
  coords: LatLng
  distance_km: number
  duration_h: number
  order_id?: number
  part?: number | null
  deadline_h?: number
}

export interface Route {
  vehicle: Vehicle
  depot: string
  steps: Step[]
}

export interface Polyline {
  pre: LatLng[]
  outbound: LatLng[]
  return_leg: LatLng[]
}

export interface Kpis {
  vehicles_used: number
  orders_delivered: number
  orders_total: number
  total_km: number
  avg_km_per_vehicle: number
}

export interface VehicleStat {
  index: number
  vehicle: string
  crew: boolean
  distance_km: number
  drive_h: number
  fuel_l: number
  co2_kg: number
  trees: number
  work_days: number
  trip_limit_h: number
  workload_share: number
}

export interface Alert {
  severity: 'high' | 'medium'
  vehicle: string | null
  type: string
  detail: string
}

export interface TimelineSegment {
  type: StepType | 'service'
  city: string
  start: number
  end: number
  detail?: string
}

export interface TimelineStop {
  type: StepType
  city: string
  t: number
  order: string | null
}

export interface VehicleTimeline {
  index: number
  vehicle: string
  segments: TimelineSegment[]
  stops: TimelineStop[]
  end: number
}

export type RowKind = 'depart' | 'arrive' | 'transit' | 'service' | 'break' | 'daily_rest' | 'weekly_rest'

export interface ScheduleRow {
  step: number
  vehicle: string
  vehicle_index: number
  kind: RowKind
  description: string
  city: string
  distance_km: number | null
  speed_kmh: number | null
  elapsed_h: number
  drive_h: number
  breaks: number
  tacho_remaining_h: number | null
  fuel_l: number
  time_left_h: number | null
  on_time: boolean | null
}

export interface Schedule {
  rows: ScheduleRow[]
  late: { vehicle: string; order: string; delay_h: number }[]
  biweekly_violations: { vehicle: string; drive_h: number; limit_h: number }[]
  speed_violations: { step: number; vehicle: string; city: string; speed_kmh: number; limit_kmh: number }[]
  fuel: { vehicle: string; distance_km: number; fuel_l100km: number; fuel_l: number }[]
}

export interface PlanResult {
  routes: Route[]
  polylines: Polyline[]
  dropped: PlannedOrder[]
  kpis: Kpis
  vehicle_stats: VehicleStat[]
  alerts: Alert[]
  timeline: VehicleTimeline[]
  schedule: Schedule
}

export interface CompareRow {
  algorithm: string
  vehicles_used: number
  total_km: number
  orders_dropped: number
  solve_time_s: number
}

export interface PlanRequest {
  depot: string
  vehicles: Vehicle[]
  orders: Order[]
  mode: Mode
  return_to_depot: boolean
  allow_split: boolean
}
