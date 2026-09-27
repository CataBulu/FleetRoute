import { describe, expect, it } from 'vitest'
import indexHtml from '../index.html?raw'
import { resolveTheme } from './theme'

describe('resolveTheme', () => {
  it.each([
    ['light', true, 'light'],
    ['light', false, 'light'],
    ['dark', true, 'dark'],
    ['dark', false, 'dark'],
    ['auto', true, 'dark'],
    ['auto', false, 'light'],
    [null, true, 'dark'],
    ['something else', false, 'light'],
  ])('%s with an OS in dark mode = %s shows %s', (pref, osDark, expected) => {
    expect(resolveTheme(pref, osDark)).toBe(expected)
  })
})

// The inline script in index.html sets the theme before React loads, so a reload never flashes
// the wrong one. It cannot import resolveTheme, so check that the two agree.
describe('the no-flash script in index.html', () => {
  const script = indexHtml.match(/<script>([\s\S]*?)<\/script>/)?.[1] ?? ''

  function run(stored: string | null, osDark: boolean) {
    const root = { dataset: {} as Record<string, string> }
    new Function('localStorage', 'window', 'document', script)(
      { getItem: () => stored },
      { matchMedia: () => ({ matches: osDark }) },
      { documentElement: root },
    )
    return root.dataset.theme
  }

  it('is the first script in the page', () => {
    expect(script).toContain('fleetroute.theme')
    expect(indexHtml.indexOf('<script>')).toBeLessThan(indexHtml.indexOf('<script type="module"'))
  })

  it.each([
    ['"light"', 'light'],
    ['"dark"', 'dark'],
    ['"auto"', 'auto'],
    [null, 'auto'],
    ['not json', 'auto'],
    ['"sepia"', 'sepia'],
  ])('agrees with resolveTheme when the stored value is %s', (stored, pref) => {
    for (const osDark of [true, false]) expect(run(stored, osDark)).toBe(resolveTheme(pref, osDark))
  })
})
