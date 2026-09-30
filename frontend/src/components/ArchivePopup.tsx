import { useEffect, useRef, useState } from 'react'
import { popupRows } from '../archive'
import { createCategory, getCategories, type Category } from '../categoriesApi'

const WIDTH = 288

interface Props {
  anchor: DOMRect
  /** 지금 이 후보가 보관돼 있는 카테고리(보관 안 했으면 null). */
  current: string | null
  archived: boolean
  onPick: (category: string | undefined) => void
  onUnarchive?: () => void
  createLabel?: string
  onClose: () => void
  title?: string
}

/** 유튜브 "저장 위치"처럼 카테고리(= `clips\` 아래 폴더)를 골라 보관한다. 이미 보관한 후보면 카테고리 바꾸기·보관 해제. */
export function ArchivePopup({ anchor, current, archived, onPick, onUnarchive, onClose, title = '보관 위치', createLabel }: Props) {
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [enabled, setEnabled] = useState(true)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    getCategories()
      .then((list) => {
        setEnabled(list.enabled)
        setCategories(list.categories)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (creating) input.current?.focus()
  }, [creating])

  const submitNew = async () => {
    const text = name.trim()
    if (!text) return
    try {
      onPick(await createCategory(text))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const left = Math.max(8, Math.min(anchor.right - WIDTH, window.innerWidth - WIDTH - 8))
  const below = anchor.bottom + 360 < window.innerHeight
  const position = below ? { top: anchor.bottom + 4 } : { bottom: window.innerHeight - anchor.top + 4 }
  const rows = categories ? popupRows(categories, current) : []

  return (
    <div className="fixed inset-0 z-[90]" onClick={onClose}>
      <div
        role="dialog"
        aria-label={title}
        className="absolute flex max-h-[22rem] flex-col overflow-hidden rounded border border-zinc-600 bg-zinc-800 text-sm shadow-lg"
        style={{ ...position, left, width: WIDTH }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-zinc-700 px-3 py-2 text-xs text-zinc-400">{title}</div>
        <ul className="min-h-0 flex-1 overflow-y-auto py-1">
          {!categories && !error && <li className="px-3 py-2 text-xs text-zinc-500">불러오는 중…</li>}
          {categories && !enabled && (
            <li>
              <button
                type="button"
                disabled={archived}
                className="block w-full px-3 py-2 text-left hover:bg-zinc-700 disabled:opacity-50"
                onClick={() => onPick(undefined)}
              >
                {archived ? '보관됨' : '보관하기'}
              </button>
            </li>
          )}
          {rows.map((row) => (
            <li key={row.name}>
              <button
                type="button"
                disabled={!row.selectable}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-zinc-700 disabled:cursor-default disabled:opacity-60 disabled:hover:bg-transparent"
                onClick={() => row.name !== current && onPick(row.name)}
              >
                <span className="h-9 w-14 shrink-0 overflow-hidden rounded bg-zinc-900">
                  {row.thumbnailClipId && (
                    <img className="h-full w-full object-cover" src={`/api/clips/${row.thumbnailClipId}/thumbnail`} alt="" />
                  )}
                </span>
                <span className="min-w-0 flex-1 truncate">{row.name}</span>
                <span className="shrink-0 text-xs text-zinc-500">{row.clipCount}</span>
                <span className="w-4 shrink-0 text-emerald-300">{row.checked ? '✓' : ''}</span>
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="px-3 py-1 text-xs text-rose-300">{error}</p>}
        {enabled && (
          <div className="border-t border-zinc-700 p-2">
            {creating ? (
              <div className="flex gap-1">
                <input
                  ref={input}
                  aria-label="새 카테고리 이름"
                  maxLength={60}
                  className="min-w-0 flex-1 rounded border border-sky-500 bg-zinc-900 px-2 py-1 text-sm outline-none"
                  value={name}
                  placeholder="카테고리 이름"
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void submitNew()}
                />
                <button type="button" className="rounded bg-sky-600 px-2 py-1 text-xs hover:bg-sky-500" onClick={() => void submitNew()}>
                  {createLabel ?? (archived ? '만들고 옮기기' : '만들고 보관')}
                </button>
              </div>
            ) : (
              <button type="button" className="w-full rounded px-2 py-1 text-left text-sky-300 hover:bg-zinc-700" onClick={() => setCreating(true)}>
                + 새 카테고리
              </button>
            )}
          </div>
        )}
        {archived && onUnarchive && (
          <button
            type="button"
            className="border-t border-zinc-700 px-3 py-2 text-left text-rose-300 hover:bg-zinc-700"
            title="클립 영상을 지우고 이 후보는 무시한 후보로 옮깁니다"
            onClick={onUnarchive}
          >
            보관 해제
          </button>
        )}
      </div>
    </div>
  )
}
