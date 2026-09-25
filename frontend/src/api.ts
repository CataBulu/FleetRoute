import type { City, CompareRow, Order, PlanRequest, PlanResult, Route, Vehicle } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new Error('Cannot reach the FleetRoute server. Is the backend running?')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.error ?? `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

const post = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  cities: () => request<{ cities: City[] }>('/api/cities').then((r) => r.cities),
  demo: () => request<{ depot: string; vehicles: Vehicle[]; orders: Order[] }>('/api/demo'),
  plan: (body: PlanRequest) => request<PlanResult>('/api/plan', post(body)),
  compare: (body: PlanRequest) => request<{ results: CompareRow[] }>('/api/compare', post(body)).then((r) => r.results),

  async exportReport(format: 'xlsx' | 'pdf', routes: Route[], fuelPrice: number) {
    const res = await fetch(`/api/export/${format}`, post({ routes, fuel_price: fuelPrice }))
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw new Error(body?.error ?? 'Export failed')
    }
    downloadBlob(await res.blob(), `fleetroute-report.${format}`)
  },
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadJson(data: unknown, filename: string) {
  downloadBlob(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), filename)
}
