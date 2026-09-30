import { useEffect, useRef } from 'react'
import { effectiveRange, formatClock, isDismissed, isSaved, type Candidate } from '../games'
import { rangeModified } from '../playerBar'

interface Props {
  cands: Candidate[]
  duration: number
  selectedId: string | null
  currentId: string | null
  checked: Set<string>
  showDismissed: boolean
  busy: boolean
  canSave: boolean
  onShowDismissed: (v: boolean) => void
  onToggleChecked: (id: string) => void
  onSelect: (c: Candidate) => void
  onSave: (id: string) => void
  onDismiss: (c: Candidate) => void
  onDelete: (id: string) => void
  onBatch: (mode: 'all' | 'certain' | 'ids') => void
}

export function ViewerCandidates(p: Props) {
  const list = useRef<HTMLUListElement>(null)
  const pending = p.cands.filter((c) => !isDismissed(c) && !isSaved(c)).length

  useEffect(() => {
    if (!p.currentId) return
    list.current?.querySelector(`[data-cand="${p.currentId}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [p.currentId])

  return (
    <aside data-testid="viewer-candidates" className="flex w-80 shrink-0 flex-col gap-2 overflow-hidden rounded border border-zinc-700 bg-zinc-800/60 p-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">후보 {pending}개 저장 대기</h3>
        <label className="flex items-center gap-1 text-xs text-zinc-400">
          <input type="checkbox" checked={p.showDismissed} onChange={(e) => p.onShowDismissed(e.target.checked)} />
          무시한 후보 보기
        </label>
      </div>
      <div className="flex flex-wrap gap-1 text-xs">
        <button type="button" disabled={p.busy || !p.canSave} className="rounded bg-sky-600 px-2 py-1 hover:bg-sky-500 disabled:opacity-40" onClick={() => p.onBatch('all')}>
          전부 저장
        </button>
        <button type="button" disabled={p.busy || !p.canSave} className="rounded bg-sky-700 px-2 py-1 hover:bg-sky-600 disabled:opacity-40" onClick={() => p.onBatch('certain')}>
          확실한 것만
        </button>
        <button
          type="button"
          disabled={p.busy || !p.canSave || p.checked.size === 0}
          className="rounded border border-sky-600 px-2 py-1 hover:bg-zinc-700 disabled:opacity-40"
          onClick={() => p.onBatch('ids')}
        >
          선택한 {p.checked.size}개
        </button>
      </div>
      <ul ref={list} className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {p.cands.length === 0 && <li className="text-xs text-zinc-500">교전 후보가 없습니다. 영상에서 원하는 곳으로 가서 "+ 여기서 구간 추가"를 누르세요.</li>}
        {p.cands.map((c) => {
          const [s, e] = effectiveRange(c, p.duration)
          const saved = isSaved(c)
          const dismissed = isDismissed(c)
          const modified = rangeModified(c, p.duration)
          const selected = p.selectedId === c.id
          return (
            <li
              key={c.id}
              data-cand={c.id}
              className={`flex flex-col gap-1 rounded border px-2 py-1.5 text-xs ${
                selected ? 'border-white bg-zinc-700' : p.currentId === c.id ? 'border-yellow-400/70 bg-yellow-400/10' : modified ? 'border-orange-400/70' : 'border-zinc-700'
              } ${dismissed ? 'opacity-50' : ''}`}
            >
              <div className="flex items-center gap-2">
                {!saved && !dismissed && (
                  <input
                    type="checkbox"
                    title="위의 '선택한 N개' 일괄 저장에 포함"
                    checked={p.checked.has(c.id)}
                    onChange={() => p.onToggleChecked(c.id)}
                  />
                )}
                <button type="button" className="min-w-0 flex-1 truncate text-left text-sm hover:underline" title={c.title} onClick={() => p.onSelect(c)}>
                  {c.title}
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-1 text-zinc-400">
                <span>
                  {formatClock(s)}~{formatClock(e)} ({Math.round(e - s)}초)
                </span>
                {modified && (
                  <span className="rounded bg-orange-500/25 px-1.5 text-orange-300">{saved ? '수정됨 · 저장 전' : '수정됨'}</span>
                )}
                {c.certain && <span className="rounded bg-yellow-500/20 px-1.5 text-yellow-300">확실</span>}
                {c.tags.map((t) => (
                  <span key={t} className="rounded bg-zinc-700 px-1.5 text-zinc-300">
                    {t}
                  </span>
                ))}
                <span className="ml-auto flex gap-1">
                  {saved && !modified ? (
                    <span className="rounded bg-emerald-600/30 px-2 py-0.5 text-emerald-200">저장됨</span>
                  ) : (
                    <button
                      type="button"
                      disabled={p.busy || !p.canSave || dismissed}
                      className="rounded bg-sky-600 px-2 py-0.5 text-zinc-100 hover:bg-sky-500 disabled:opacity-40"
                      onClick={() => p.onSave(c.id)}
                    >
                      {saved ? '다시 저장' : '저장'}
                    </button>
                  )}
                  {c.id.includes('_u') ? (
                    <button type="button" disabled={p.busy} className="rounded border border-zinc-600 px-2 py-0.5 hover:bg-zinc-600" onClick={() => p.onDelete(c.id)}>
                      삭제
                    </button>
                  ) : (
                    !saved && (
                      <button
                        type="button"
                        disabled={p.busy}
                        className="rounded border border-zinc-600 px-2 py-0.5 hover:bg-zinc-600"
                        title="이 후보를 목록에서 숨긴다(무시한 후보 보기로 다시 볼 수 있다)"
                        onClick={() => p.onDismiss(c)}
                      >
                        {dismissed ? '되살리기' : '무시'}
                      </button>
                    )
                  )}
                </span>
              </div>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
