import { useRef, type KeyboardEvent } from 'react'
import type { ThemePref } from '../theme'
import { Icon, type IconName } from './Icon'

const OPTIONS: { value: ThemePref; label: string; icon: IconName }[] = [
  { value: 'light', label: 'Light', icon: 'sun' },
  { value: 'dark', label: 'Dark', icon: 'moon' },
  { value: 'auto', label: 'Auto', icon: 'monitor' },
]

const STEP: Partial<Record<string, number>> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }

/** Light / Dark / Auto switch: a radio group, so arrow keys move and select, and Tab enters once. */
export function ThemeToggle({ value, onChange }: { value: ThemePref; onChange: (v: ThemePref) => void }) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([])
  const current = Math.max(0, OPTIONS.findIndex((o) => o.value === value))

  function onKeyDown(e: KeyboardEvent) {
    const last = OPTIONS.length - 1
    const step = STEP[e.key]
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? last : step === undefined ? null : (current + step + OPTIONS.length) % OPTIONS.length
    if (next === null) return
    e.preventDefault()
    onChange(OPTIONS[next].value)
    buttons.current[next]?.focus()
  }

  return (
    <div className="theme-toggle" role="radiogroup" aria-label="Theme" onKeyDown={onKeyDown}>
      {OPTIONS.map((o, i) => (
        <button
          key={o.value}
          ref={(el) => { buttons.current[i] = el }}
          type="button"
          role="radio"
          className="theme-option"
          aria-checked={value === o.value}
          aria-label={o.label}
          title={o.label}
          tabIndex={i === current ? 0 : -1}
          onClick={() => onChange(o.value)}
        >
          <Icon name={o.icon} size={14} />
        </button>
      ))}
    </div>
  )
}
