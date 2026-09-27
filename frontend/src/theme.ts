import { useEffect } from 'react'

export type ThemePref = 'light' | 'dark' | 'auto'

const DARK_QUERY = '(prefers-color-scheme: dark)'

/** The theme to show. Anything but an explicit 'light' or 'dark' (including a corrupt stored
 *  value) means auto. The inline script in index.html applies the same rule. */
export function resolveTheme(pref: unknown, osDark: boolean): 'light' | 'dark' {
  if (pref === 'light' || pref === 'dark') return pref
  return osDark ? 'dark' : 'light'
}

/**
 * Sets `<html data-theme>` to the resolved theme. In auto mode it follows the OS setting live.
 * The inline script in index.html does the same before the first paint, so there is no flash.
 */
export function useApplyTheme(pref: ThemePref) {
  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY)
    const apply = () => {
      const root = document.documentElement
      const next = resolveTheme(pref, media.matches)
      if (root.dataset.theme === next) return
      // Swap all colours at once: without this, elements with hover transitions fade while the rest snap.
      root.classList.add('theme-switching')
      root.dataset.theme = next
      void root.offsetWidth // apply the new colours before transitions come back
      requestAnimationFrame(() => root.classList.remove('theme-switching'))
    }
    apply()
    if (pref === 'light' || pref === 'dark') return
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [pref])
}
