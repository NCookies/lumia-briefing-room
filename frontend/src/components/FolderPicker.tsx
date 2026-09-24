import { useState } from 'react'
import { pickFolder } from '../exportApi'

interface Props {
  value: string
  onChange: (path: string) => void
  title?: string
}

export function FolderPicker({ value, onChange, title }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const browse = async () => {
    setBusy(true)
    setError(null)
    try {
      const chosen = await pickFolder(value, title)
      if (chosen) onChange(chosen)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <div className="flex-1 truncate rounded bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200" title={value}>
          {value || <span className="text-zinc-500">선택한 폴더가 없습니다</span>}
        </div>
        <button
          type="button"
          className="shrink-0 rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40"
          disabled={busy}
          onClick={() => void browse()}
        >
          {busy ? '선택 중…' : '폴더 선택…'}
        </button>
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
    </div>
  )
}
