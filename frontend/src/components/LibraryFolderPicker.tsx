import { useEffect, useState } from 'react'
import { getLibrary, type LibraryListing } from '../libraryApi'
import { canDropOn } from '../library'
import { FolderIcon } from './LibraryIcons'

interface Props {
  items: string[]
  startPath: string
  onPick: (dest: string) => Promise<void> | void
  onCancel: () => void
}

/** 클립 폴더 안에서 옮길 폴더를 고르는 창. 자기 안쪽 폴더와 가상 최상위는 고를 수 없다. */
export function LibraryFolderPicker({ items, startPath, onPick, onCancel }: Props) {
  const [path, setPath] = useState(startPath)
  const [listing, setListing] = useState<LibraryListing | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getLibrary(path)
      .then((l) => {
        setListing(l)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [path])

  const movable = listing !== null && !listing.virtualTop && canDropOn(items, path)

  const pick = async () => {
    setBusy(true)
    try {
      await onPick(path)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4" role="presentation">
      <div role="dialog" aria-modal="true" className="flex max-h-[80vh] w-full max-w-md flex-col gap-3 rounded-lg border border-zinc-600/70 bg-zinc-800 p-5">
        <h3 className="text-sm font-medium text-zinc-100">옮길 폴더 고르기</h3>
        <nav className="flex flex-wrap items-center gap-1 text-xs text-zinc-400">
          {listing?.crumbs.map((c, i) => (
            <span key={c.rel} className="flex items-center gap-1">
              {i > 0 && <span>/</span>}
              <button type="button" className="hover:text-zinc-100" onClick={() => setPath(c.rel)}>
                {c.name}
              </button>
            </span>
          ))}
        </nav>
        <ul className="min-h-[8rem] flex-1 overflow-y-auto rounded-md border border-zinc-700 bg-zinc-900/60 text-sm">
          {listing?.folders.length === 0 && <li className="px-3 py-2 text-xs text-zinc-500">하위 폴더가 없습니다</li>}
          {listing?.folders.map((f) => {
            const blocked = items.some((it) => f.rel === it || f.rel.startsWith(`${it}/`))
            return (
              <li key={f.rel}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-3 py-1.5 text-left hover:bg-zinc-700 disabled:opacity-40"
                  disabled={blocked}
                  onClick={() => setPath(f.rel)}
                >
                  <span className="flex items-center gap-2">
                    <FolderIcon className="h-4 w-4 text-amber-400" />
                    {f.name}
                  </span>
                  <span className="text-xs text-zinc-500">{f.clipCount}</span>
                </button>
              </li>
            )
          })}
        </ul>
        {listing?.virtualTop && <p className="text-xs text-zinc-500">스팀 녹화나 영상 파일 폴더를 고른 뒤 그 안으로 들어가세요.</p>}
        {error && <p className="text-xs text-rose-300">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={onCancel}>
            취소
          </button>
          <button
            type="button"
            className="rounded-md bg-sky-600 px-4 py-1.5 text-sm transition hover:bg-sky-500 disabled:opacity-40"
            disabled={!movable || busy}
            onClick={() => void pick()}
          >
            {busy ? '옮기는 중…' : '여기로 옮기기'}
          </button>
        </div>
      </div>
    </div>
  )
}
