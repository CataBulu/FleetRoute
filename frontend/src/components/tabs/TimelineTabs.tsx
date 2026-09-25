import { clock, routeColor } from '../../format'
import type { StepType, TimelineSegment, VehicleTimeline } from '../../types'
import { Icon, type IconName } from '../Icon'
import { Banner } from '../ui'

const DISPATCH_HOUR = 8
const spansDays = (timeline: VehicleTimeline[]) => Math.max(0, ...timeline.map((v) => v.end)) + DISPATCH_HOUR > 24

const STOP_STYLE: Record<StepType, { icon: IconName; color: string; label: (order: string | null) => string; note: string }> = {
  depart: { icon: 'home', color: '#2B7DE9', label: () => 'Leave the depot', note: 'Start' },
  home_depart: { icon: 'truck', color: '#06B6D4', label: () => 'Leave current location', note: 'Start' },
  arrive_depot: { icon: 'home', color: '#2B7DE9', label: () => 'Reach the depot', note: 'Ready' },
  pickup: { icon: 'box', color: '#F97316', label: (o) => `Pick up order #${o}`, note: 'Loading 2 h' },
  delivery: { icon: 'flag', color: '#16A34A', label: (o) => `Deliver order #${o}`, note: 'Unloading 2 h' },
  return: { icon: 'restart', color: '#64748B', label: () => 'Back at the depot', note: 'Done' },
  transit: { icon: 'route', color: '#94A3B8', label: () => 'Transit', note: '' },
}

export function JourneyTab({ timeline }: { timeline: VehicleTimeline[] }) {
  const multiDay = spansDays(timeline)
  return (
    <div className="journeys">
      {timeline.map((v) => (
        <article className="journey" key={v.index}>
          <div className="journey-head" style={{ background: `${routeColor(v.index)}14` }}>
            <span className="veh-dot" style={{ background: routeColor(v.index), width: 12, height: 12 }} />
            <b>{v.vehicle}</b>
            <span className="grow" />
            <span className="badge">{clock(v.end, multiDay)} finish</span>
          </div>
          <ol>
            {v.stops.map((s, i) => {
              const style = STOP_STYLE[s.type]
              return (
                <li key={i}>
                  <span className="dot" style={{ background: style.color }}><Icon name={style.icon} size={12} /></span>
                  <div>
                    <div className="what">{style.label(s.order)}</div>
                    <div className="where">{s.city}{style.note && ` · ${style.note}`}</div>
                  </div>
                  <time>{clock(s.t, multiDay)}</time>
                </li>
              )
            })}
          </ol>
        </article>
      ))}
    </div>
  )
}

const SEGMENT_COLORS: Record<TimelineSegment['type'], string> = {
  transit: '#93C5FD', pickup: '#FB923C', delivery: '#4ADE80', return: '#CBD5E1',
  home_depart: '#67E8F9', arrive_depot: '#60A5FA', depart: '#60A5FA', service: '#1E3A5F',
}
const SEGMENT_LEGEND: [string, string][] = [
  ['Driving', SEGMENT_COLORS.transit], ['Arriving at a pickup', SEGMENT_COLORS.pickup],
  ['Arriving at a delivery', SEGMENT_COLORS.delivery], ['Loading / unloading', SEGMENT_COLORS.service],
  ['Going to the depot', SEGMENT_COLORS.arrive_depot], ['Returning', SEGMENT_COLORS.return],
]

export function GanttTab({ timeline }: { timeline: VehicleTimeline[] }) {
  const end = Math.max(1, ...timeline.map((v) => v.end))
  const multiDay = spansDays(timeline)
  const stepH = end > 72 ? 12 : end > 36 ? 6 : end > 12 ? 3 : 1
  const ticks = Array.from({ length: Math.floor(end / stepH) + 1 }, (_, i) => i * stepH)
  const pct = (h: number) => `${(h / end) * 100}%`

  return (
    <>
      <div className="gantt-legend">
        {SEGMENT_LEGEND.map(([label, color]) => <span key={label}><i style={{ background: color }} />{label}</span>)}
      </div>
      <div className="gantt-scroll">
        <div className="gantt">
          {timeline.map((v) => (
            <div className="gantt-row" key={v.index}>
              <div className="gantt-label"><span className="veh-dot" style={{ background: routeColor(v.index) }} />{v.vehicle}</div>
              <div className="gantt-track">
                {ticks.map((t) => <div key={t} className="gantt-grid" style={{ left: pct(t) }} />)}
                {v.segments.map((s, i) => (
                  <div key={i} className="gantt-seg"
                    style={{ left: pct(s.start), width: pct(s.end - s.start), background: SEGMENT_COLORS[s.type] }}
                    title={`${s.detail ?? 'Drive'} · ${s.city} · ${clock(s.start, multiDay)} → ${clock(s.end, multiDay)}`} />
                ))}
              </div>
            </div>
          ))}
          <div className="gantt-row">
            <div />
            <div className="gantt-axis">
              {ticks.map((t) => <span key={t} style={{ left: pct(t) }}>{clock(t, multiDay).replace('Day ', 'D')}</span>)}
            </div>
          </div>
        </div>
      </div>
      <p className="hint">Dispatch at 08:00 today. Hover a bar for details. EU breaks and rests are listed in the routing table.</p>
    </>
  )
}

export function NotificationsTab({ timeline }: { timeline: VehicleTimeline[] }) {
  const multiDay = spansDays(timeline)
  const notes = timeline
    .flatMap((v) => v.stops.filter((s) => s.type === 'delivery').map((s) => ({ ...s, vehicle: v.vehicle })))
    .sort((a, b) => a.t - b.t)

  if (!notes.length) return <Banner tone="info" title="No deliveries in this plan yet." />
  return (
    <>
      <p className="hint">Messages a customer would receive when their load arrives. Nothing is actually sent.</p>
      <div className="notes">
        {notes.map((n, i) => (
          <div className="note" key={i}>
            <span className="note-icon"><Icon name="message" size={16} /></span>
            <div className="grow">
              <div><b>Customer #{n.order}</b>: your order has arrived in {n.city}.</div>
              <div className="note-meta">SMS · delivered by {n.vehicle}</div>
            </div>
            <span className="badge blue">{clock(n.t, multiDay)}</span>
          </div>
        ))}
      </div>
    </>
  )
}
