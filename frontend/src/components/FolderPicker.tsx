import { useEffect, useState } from 'react'
import { listDirs, makeDir, type DirListing } from '../exportApi'

interface Props {
  value: string
  onChange: (path: string) => void
}

function join(base: string, name: string): string {
  return base === '' || /[\\/]$/.test(base) ? `${base}${name}` : `${base}\\${name}`
}

export function FolderPicker({ value, onChange }: Props) {
  const [listing, setListing] = useState<DirListing | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')

  useEffect(() => {
    let cancelled = false
    listDirs(value)
      .then((l) => {
        if (cancelled) return
        setListing(l)
        setError(null)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setError(e.message)
        if (value !== '') onChange('')
      })
    return () => {
      cancelled = true
    }
  }, [value, onChange])

  const createFolder = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      const { path } = await makeDir(value, name)
      setCreating(false)
      setNewName('')
      onChange(path)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-30"
          disabled={!listing || value === ''}
          onClick={() => onChange(listing?.parent ?? '')}
          title="상위 폴더"
        >
          ↑
        </button>
        <div className="flex-1 truncate rounded bg-zinc-900 px-2 py-1 text-sm text-zinc-200" title={value}>
          {value || '내 컴퓨터 (드라이브 선택)'}
        </div>
        <button
          type="button"
          className="rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-30"
          disabled={value === ''}
          onClick={() => setCreating((c) => !c)}
        >
          새 폴더
        </button>
      </div>

      {creating && (
        <div className="flex gap-2">
          <input
            className="flex-1 rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
            placeholder="새 폴더 이름"
            value={newName}
            autoFocus
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && createFolder()}
          />
          <button type="button" className="rounded bg-sky-600 px-3 py-1 text-sm hover:bg-sky-500" onClick={createFolder}>
            만들기
          </button>
        </div>
      )}

      {error && <p className="text-xs text-rose-400">{error}</p>}

      <ul className="h-56 overflow-y-auto rounded border border-zinc-700 bg-zinc-900/60">
        {listing?.dirs.length === 0 && <li className="px-3 py-2 text-sm text-zinc-500">하위 폴더 없음</li>}
        {listing?.dirs.map((name) => (
          <li key={name}>
            <button
              type="button"
              className="w-full px-3 py-1.5 text-left text-sm text-zinc-200 hover:bg-zinc-700"
              onClick={() => onChange(join(listing.path, name))}
            >
              📁 {name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
