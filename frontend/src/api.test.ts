import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import type { PlanRequest } from './types'

const plan: PlanRequest = { depot: 'Brasov', vehicles: [], orders: [], mode: 'economic', return_to_depot: true, allow_split: false }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api', () => {
  it('unwraps the city list', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ cities: [{ name: 'Arad', lat: 46.2, lon: 21.3 }] })))
    await expect(api.cities()).resolves.toEqual([{ name: 'Arad', lat: 46.2, lon: 21.3 }])
  })

  it('posts the plan request as JSON', async () => {
    const fetch = vi.fn(async (_path: string, _init?: RequestInit) => json({ routes: [] }))
    vi.stubGlobal('fetch', fetch)
    await api.plan(plan)
    const [path, init] = fetch.mock.calls[0]
    expect(path).toBe('/api/plan')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual(plan)
  })

  it("shows the API's own message when it rejects the input", async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ error: 'Unknown depot: Atlantis' }, 400)))
    await expect(api.plan(plan)).rejects.toThrow('Unknown depot: Atlantis')
  })

  it('falls back to the status code when the error is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Bad gateway', { status: 502 })))
    await expect(api.plan(plan)).rejects.toThrow('Request failed (502)')
  })

  it('explains when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(api.cities()).rejects.toThrow('Cannot reach the FleetRoute server')
  })
})
