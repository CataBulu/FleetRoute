import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Fragment, memo, useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { clock, routeColor, vehicleLabel } from '../format'
import { buildTrack, positionAt } from '../simulation'
import type { City, LatLng, PlanResult } from '../types'
import { Icon } from './Icon'

const ROMANIA_CENTER: LatLng = [45.94, 24.97]
const PLAYBACK_RATES = [0.25, 0.5, 1, 2, 4] // simulated hours per real second

type Role = 'depot' | 'pickup' | 'delivery' | 'home'

const PIN_ICONS = Object.fromEntries(
  (['depot', 'pickup', 'delivery', 'home'] as Role[]).map((role) => [
    role,
    L.divIcon({ className: '', html: `<div class="pin pin-${role}"></div>`, iconSize: [22, 22], iconAnchor: [11, 11] }),
  ]),
) as Record<Role, L.DivIcon>

const ROLE_LABEL: Record<Role, string> = {
  depot: 'Depot', pickup: 'Pickup', delivery: 'Delivery', home: 'Truck starting point',
}

function truckIcon(color: string, n: number) {
  return L.divIcon({
    className: '',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    html: `<div class="truck" style="background:${color}">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h11v9H3zM14 9h4l3 3v3h-7"/><circle cx="6.5" cy="17.5" r="1.6"/><circle cx="17.5" cy="17.5" r="1.6"/></svg>
      <span>${n}</span></div>`,
  })
}

/** Which marker each city gets. Depot wins, then pickup, then delivery. */
function cityRoles(result: PlanResult | null, depot: string | null) {
  const roles = new Map<string, Role>()
  for (const route of result?.routes ?? []) {
    for (const s of route.steps) {
      const cur = roles.get(s.city)
      if (s.type === 'pickup') roles.set(s.city, 'pickup')
      else if (s.type === 'delivery' && cur !== 'pickup') roles.set(s.city, 'delivery')
      else if (s.type === 'home_depart' && !cur) roles.set(s.city, 'home')
    }
  }
  if (depot) roles.set(depot, 'depot')
  return roles
}

function FitToRoutes({ points, depot }: { points: LatLng[]; depot: LatLng | null }) {
  const map = useMap()
  useEffect(() => {
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [40, 40] })
    else if (depot) map.setView(depot, 7)
  }, [map, points, depot])
  return null
}

export function RouteMap({ cities, depot, result, simulate, onExitSimulation }: {
  cities: City[]
  depot: string | null
  result: PlanResult | null
  simulate: boolean
  onExitSimulation: () => void
}) {
  const roles = useMemo(() => cityRoles(result, depot), [result, depot])
  const cityByName = useMemo(() => new Map(cities.map((c) => [c.name, c])), [cities])
  const depotCity = depot ? cityByName.get(depot) : undefined
  const depotPos = useMemo<LatLng | null>(() => (depotCity ? [depotCity.lat, depotCity.lon] : null), [depotCity])
  const allPoints = useMemo(
    () => (result?.polylines ?? []).flatMap((p) => [...p.pre, ...p.outbound, ...p.return_leg]),
    [result],
  )
  const tracks = useMemo(() => (result?.routes ?? []).map(buildTrack), [result])
  const truckIcons = useMemo(() => tracks.map((_, i) => truckIcon(routeColor(i), i + 1)), [tracks])
  const simEnd = Math.max(0, ...tracks.map((t) => t.end))

  // ----- simulation clock -----
  const [simH, setSimH] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [rate, setRate] = useState(1)
  const last = useRef<number | null>(null)

  // restart playback whenever it is switched on or a new plan arrives
  const [playbackFor, setPlaybackFor] = useState({ simulate, result })
  if (playbackFor.simulate !== simulate || playbackFor.result !== result) {
    setPlaybackFor({ simulate, result })
    setSimH(0)
    setPlaying(simulate)
  }

  useEffect(() => {
    if (!playing) return
    let frame = 0
    const tick = (now: number) => {
      const dt = last.current == null ? 0 : (now - last.current) / 1000
      last.current = now
      setSimH((h) => {
        const next = h + dt * rate
        if (next >= simEnd) {
          setPlaying(false)
          return simEnd
        }
        return next
      })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frame)
      last.current = null
    }
  }, [playing, rate, simEnd])

  const multiDay = simEnd + 8 > 24

  return (
    <div className="card map-card">
      <div className="card-head">
        <h3><Icon name={simulate ? 'film' : 'route'} /> {simulate ? 'Route playback' : 'Route map'}</h3>
        <p>
          {simulate
            ? 'Trucks move on the planned schedule, stopping 2 h at every pickup and delivery.'
            : 'Lines follow the road network between cities. Map data © OpenStreetMap contributors.'}
        </p>
      </div>
      <div className="map-wrap">
        <MapContainer center={ROMANIA_CENTER} zoom={7} scrollWheelZoom>
          <TileLayer
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            maxZoom={18}
          />
          <FitToRoutes points={allPoints} depot={depotPos} />

          <StaticLayers cities={cities} cityByName={cityByName} roles={roles} result={result} simulate={simulate} />

          {simulate && tracks.map((track, i) => (
            <Marker key={`truck-${i}`} position={positionAt(track, simH)} icon={truckIcons[i]} zIndexOffset={2000}>
              <Tooltip direction="top" offset={[0, -14]}>{vehicleLabel(result!.routes[i].vehicle)}</Tooltip>
            </Marker>
          ))}
        </MapContainer>

        <div className="legend">
          {result?.routes.map((r, i) => (
            <div className="legend-row" key={i}>
              <span className="legend-swatch" style={{ background: routeColor(i) }} />
              <span className="legend-name">{i + 1}. {vehicleLabel(r.vehicle)}</span>
            </div>
          ))}
          {(['depot', 'pickup', 'delivery', 'home'] as Role[])
            .filter((r) => r === 'depot' ? depot : [...roles.values()].includes(r))
            .map((r) => (
              <div className="legend-row" key={r}>
                <span className={`legend-dot pin-${r}`} style={{ width: 10, height: 10 }} />
                {ROLE_LABEL[r]}
              </div>
            ))}
        </div>
      </div>

      {simulate && (
        <div className="sim-bar">
          <button className="btn btn-primary btn-sm" onClick={() => {
            if (simH >= simEnd) setSimH(0)
            setPlaying(!playing)
          }}>
            <Icon name={playing ? 'pause' : 'play'} size={14} /> {playing ? 'Pause' : 'Play'}
          </button>
          <button className="icon-btn" title="Restart" aria-label="Restart" onClick={() => setSimH(0)}>
            <Icon name="restart" size={16} />
          </button>
          <span className="sim-clock">{clock(simH, multiDay)}</span>
          <input type="range" className="grow" min={0} max={simEnd} step={0.01} value={simH}
            aria-label="Playback position" onChange={(e) => setSimH(Number(e.target.value))} />
          <label className="check">
            Speed
            <select className="select" style={{ width: 110, height: 30 }} value={rate} onChange={(e) => setRate(Number(e.target.value))}>
              {PLAYBACK_RATES.map((r) => (
                <option key={r} value={r}>{r < 1 ? `${r * 60} min/s` : `${r} h/s`}</option>
              ))}
            </select>
          </label>
          <button className="btn btn-ghost btn-sm" onClick={onExitSimulation}>
            <Icon name="x" size={14} /> Exit playback
          </button>
        </div>
      )}
    </div>
  )
}

/** Cities, route lines and stop markers. Memoised so the 60 fps playback clock
 *  only re-renders the moving trucks. */
const StaticLayers = memo(function StaticLayers({ cities, cityByName, roles, result, simulate }: {
  cities: City[]
  cityByName: Map<string, City>
  roles: Map<string, Role>
  result: PlanResult | null
  simulate: boolean
}) {
  return (
    <>
      {cities.filter((c) => !roles.has(c.name)).map((c) => (
        <CircleMarker key={c.name} center={[c.lat, c.lon]} radius={4}
          pathOptions={{ color: '#6b8bb3', weight: 1, fillColor: '#ffffff', fillOpacity: 0.9 }}>
          <Tooltip direction="top">{c.name}</Tooltip>
        </CircleMarker>
      ))}

      {result?.polylines.map((p, i) => {
        const color = routeColor(i)
        const name = vehicleLabel(result.routes[i].vehicle)
        return (
          <Fragment key={i}>
            {p.pre.length > 1 && (
              <Polyline positions={p.pre} pathOptions={{ color: '#64748b', weight: 3, dashArray: '6 8', opacity: 0.8 }}>
                <Tooltip sticky>{name}: to the depot</Tooltip>
              </Polyline>
            )}
            {p.outbound.length > 1 && (
              <>
                <Polyline positions={p.outbound} pathOptions={{ color: '#ffffff', weight: 9, opacity: 0.9 }} />
                <Polyline positions={p.outbound} pathOptions={{ color, weight: 5, opacity: 0.95 }}>
                  <Tooltip sticky>{name}: deliveries</Tooltip>
                </Polyline>
                {!simulate && (
                  <Polyline positions={p.outbound} interactive={false}
                    pathOptions={{ color: '#ffffff', weight: 2.5, opacity: 0.95, className: 'route-flow' }} />
                )}
              </>
            )}
            {p.return_leg.length > 1 && (
              <Polyline positions={p.return_leg} pathOptions={{ color, weight: 4, dashArray: '2 9', opacity: 0.75 }}>
                <Tooltip sticky>{name}: return to depot</Tooltip>
              </Polyline>
            )}
          </Fragment>
        )
      })}

      {[...roles].map(([city, role]) => {
        const c = cityByName.get(city)
        if (!c) return null
        return (
          <Marker key={city} position={[c.lat, c.lon]} icon={PIN_ICONS[role]} zIndexOffset={role === 'depot' ? 1000 : 500}>
            <Tooltip direction="top" offset={[0, -8]}><b>{city}</b> · {ROLE_LABEL[role]}</Tooltip>
          </Marker>
        )
      })}
    </>
  )
})
