import { useRef, useState } from 'react'
import { Icon } from './Icon'

/** Opens a JSON file and passes the parsed content on; shows parse errors inline. */
export function ImportButton({ label, onData }: { label: string; onData: (data: unknown) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)

  async function load(file: File) {
    try {
      onData(JSON.parse(await file.text()))
      setError(null)
    } catch (e) {
      setError(e instanceof SyntaxError ? 'That file is not valid JSON.' : (e as Error).message)
    }
  }

  return (
    <>
      <button className="btn btn-ghost btn-sm" onClick={() => input.current?.click()}>
        <Icon name="upload" size={14} /> {label}
      </button>
      <input
        ref={input}
        type="file"
        accept="application/json,.json"
        className="visually-hidden"
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) void load(file)
          e.target.value = ''
        }}
      />
      {error && <div className="form-error" style={{ width: '100%' }}>{error}</div>}
    </>
  )
}
