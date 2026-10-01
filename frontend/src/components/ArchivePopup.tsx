import { useEffect, useRef, useState } from 'react'
import { initialHighlight, popupEntries, popupRows, stepHighlight } from '../archive'
import { createCategory, getCategories, type Category } from '../categoriesApi'

const WIDTH = 288

interface Props {
  anchor: DOMRect
  /** 지금 이 후보가 보관돼 있는 카테고리(보관 안 했으면 null). */
  current: string | null
  archived: boolean
  onPick: (category: string | undefined) => void
  createLabel?: string
  onClose: () => void
  title?: string
}

/** 유튜브 "저장 위치"처럼 카테고리(= `clips\` 아래 폴더)를 골라 보관한다. 이미 보관한 후보면 카테고리 바꾸기·보관 해제. */
export function ArchivePopup({ anchor, current, archived, onPick, onClose, title = '보관 위치', createLabel }: Props) {
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [enabled, setEnabled] = useState(true)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const list = useRef<HTMLUListElement>(null)

  useEffect(() => {
    ;(document.activeElement as HTMLElement | null)?.blur()
  }, [])

  useEffect(() => {
    getCategories()
      .then((list) => {
        setEnabled(list.enabled)
        setCategories(list.categories)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

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
  const entries = categories ? popupEntries(rows, enabled) : []
  const entryAt = (kind: 'plain' | 'new' | 'row', name?: string) =>
    entries.findIndex((en) => en.kind === kind && (kind !== 'row' || (en.kind === 'row' && en.name === name)))

  useEffect(() => {
    if (categories) setActive(initialHighlight(popupEntries(popupRows(categories, current), enabled), current))
  }, [categories, enabled, current])

  useEffect(() => {
    list.current?.querySelector(`[data-entry="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active])

  const choose = (index: number) => {
    const entry = entries[index]
    if (!entry) return
    if (entry.kind === 'new') setCreating(true)
    else if (entry.kind === 'plain') !archived && onPick(undefined)
    else if (entry.name !== current) onPick(entry.name)
  }

  const keyRef = useRef({ onClose, choose, active, count: entries.length, creating })
  keyRef.current = { onClose, choose, active, count: entries.length, creating }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = keyRef.current
      const handled = (fn: () => void) => {
        e.preventDefault()
        e.stopPropagation()
        fn()
      }
      if (e.key === 'Escape') return handled(k.onClose)
      if (k.creating) return
      if (e.key === 'ArrowDown') handled(() => setActive((i) => stepHighlight(i, k.count, 1)))
      else if (e.key === 'ArrowUp') handled(() => setActive((i) => stepHighlight(i, k.count, -1)))
      else if (e.key === 'Enter') handled(() => !e.repeat && k.choose(k.active))
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [])

  return (
    <div className="fixed inset-0 z-[90]" onClick={onClose}>
      <div
        role="dialog"
        aria-label={title}
        className="absolute flex max-h-[22rem] flex-col overflow-hidden rounded-md border border-zinc-600/70 bg-zinc-800 text-sm shadow-lg"
        style={{ ...position, left, width: WIDTH }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-zinc-700 px-3 py-2 text-xs text-zinc-400">{title}</div>
        <ul ref={list} className="min-h-0 flex-1 overflow-y-auto py-1">
          {!categories && !error && <li className="px-3 py-2 text-xs text-zinc-500">불러오는 중…</li>}
          {categories && !enabled && (
            <li>
              <button
                type="button"
                disabled={archived}
                data-entry={entryAt('plain')}
                className={`block w-full px-3 py-2 text-left hover:bg-zinc-700 disabled:opacity-50 ${active === entryAt('plain') ? 'bg-zinc-700' : ''}`}
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
                data-entry={entryAt('row', row.name)}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-zinc-700 disabled:cursor-default disabled:hover:bg-transparent ${row.dim ? 'opacity-60' : ''} ${active === entryAt('row', row.name) ? 'bg-zinc-700' : ''}`}
                onClick={() => row.name !== current && onPick(row.name)}
              >
                <span className="h-9 w-14 shrink-0 overflow-hidden rounded-md bg-zinc-900">
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
                  className="min-w-0 flex-1 rounded-md border border-sky-500 bg-zinc-900 px-2 py-1 text-sm outline-none"
                  value={name}
                  placeholder="카테고리 이름"
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void submitNew()}
                />
                <button type="button" className="rounded-md bg-sky-600 px-2 py-1 text-xs transition hover:bg-sky-500" onClick={() => void submitNew()}>
                  {createLabel ?? (archived ? '만들고 옮기기' : '만들고 보관')}
                </button>
              </div>
            ) : (
              <button
                type="button"
                data-entry={entryAt('new')}
                className={`w-full rounded-md px-2 py-1 text-left text-sky-300 transition hover:bg-zinc-700 ${active === entryAt('new') ? 'bg-zinc-700' : ''}`}
                onClick={() => setCreating(true)}
              >
                + 새 카테고리
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
