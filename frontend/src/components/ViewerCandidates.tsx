import { useEffect, useRef, useState } from 'react'
import { candidateTitle, effectiveRange, formatClock, isDismissed, isSaved, type Candidate } from '../games'
import { rowState } from '../archive'
import { rangeModified } from '../playerBar'
import { ClipMemoInput } from './ClipMemoInput'
import { BookmarkFilledIcon, BookmarkIcon, EditIcon } from './ViewerIcons'

interface Props {
  cands: Candidate[]
  duration: number
  selectedId: string | null
  currentId: string | null
  modifiedCount: number
  busy: boolean
  /** 클립 저장(다시 저장·범위 저장)이 진행 중이다 — 저장 버튼 글자를 `저장 중…` 으로 바꿔 멈춘 게 아님을 알린다. */
  saving: boolean
  canSave: boolean
  onSelect: (c: Candidate) => void
  showDismissed: boolean
  onToggleDismissed: (value: boolean) => void
  /** 보관 위치 팝업을 연다(보관 안 한 후보는 보관, 보관한 후보는 카테고리 바꾸기·보관 해제). */
  onArchive: (id: string, anchor: DOMRect) => void
  /** 보관한 클립에 고친 범위를 반영한다(다시 저장). */
  onResave: (id: string) => void
  /** 이 후보로 만든 클립 파일을 지운다(보관됨 여부와 상관없이). 후보는 목록에 남는다. */
  onDeleteClip: (id: string) => void
  /** 보관한 클립의 메모(로컬 전용)를 저장한다. */
  onMemo: (id: string, memo: string | null) => void
  onDismiss: (c: Candidate) => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  onSaveModified: () => void
  /** 메모 칸이 열린 후보. 위(`GameViewer`)가 들고 있어 `M` 키로도 열고 닫는다. */
  memoOpenId: string | null
  onMemoOpenChange: (id: string | null) => void
}

export function ViewerCandidates(p: Props) {
  const list = useRef<HTMLUListElement>(null)
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null)
  const memoOpen = p.memoOpenId

  const commitRename = () => {
    if (!editing) return
    const target = p.cands.find((c) => c.id === editing.id)
    setEditing(null)
    if (target && editing.text.trim() !== candidateTitle(target)) p.onRename(editing.id, editing.text)
  }
  const active = p.cands.filter((c) => !isDismissed(c)).length

  useEffect(() => {
    if (!p.currentId) return
    list.current?.querySelector(`[data-cand="${p.currentId}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [p.currentId])

  return (
    <aside
      data-testid="viewer-candidates"
      className="flex w-96 shrink-0 flex-col gap-2.5 overflow-hidden rounded-lg border border-zinc-700/60 bg-zinc-800/60 p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-base font-semibold">
          후보 {active}개
          {p.modifiedCount > 0 && <span className="ml-1 text-xs font-normal text-orange-300">· {p.modifiedCount}개 저장 대기</span>}
        </h3>
        <button
          type="button"
          disabled={p.busy || !p.canSave || p.modifiedCount === 0}
          className="rounded-md bg-sky-600 px-3 py-1 text-xs font-medium text-white transition hover:bg-sky-500 active:scale-95 disabled:opacity-40"
          title="범위를 고친 보관 클립에 새 범위를 전부 반영합니다"
          onClick={p.onSaveModified}
        >
          {p.saving ? '저장 중…' : `전부 저장${p.modifiedCount > 0 ? ` (${p.modifiedCount})` : ''}`}
        </button>
      </div>
      <label className="flex items-center gap-1.5 text-xs text-zinc-400">
        <input type="checkbox" checked={p.showDismissed} onChange={(e) => p.onToggleDismissed(e.target.checked)} />
        삭제한 후보도 보기
      </label>
      <ul ref={list} className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-0.5">
        {p.cands.length === 0 && (
          <li className="text-xs text-zinc-500">
            교전 후보가 없습니다. 영상에서 원하는 곳으로 가서 "+ 여기서 구간 추가"를 누르세요.
          </li>
        )}
        {p.cands.map((c) => {
          const [s, e] = effectiveRange(c, p.duration)
          const saved = isSaved(c)
          const dismissed = isDismissed(c)
          const modified = rangeModified(c, p.duration)
          const state = rowState(saved, c.user.archived === true, modified)
          const selected = p.selectedId === c.id
          return (
            <li
              key={c.id}
              data-cand={c.id}
              className={`flex flex-col gap-1.5 rounded-lg border px-3 py-2.5 text-xs transition-colors ${
                selected
                  ? 'border-sky-400/80 bg-sky-500/10 shadow-sm'
                  : p.currentId === c.id
                    ? 'border-yellow-400/60 bg-yellow-400/10'
                    : modified
                      ? 'border-orange-400/60 bg-zinc-800/40'
                      : 'border-zinc-700/60 bg-zinc-800/40 hover:bg-zinc-700/40'
              } ${dismissed ? 'opacity-50' : ''}`}
            >
              <div className="flex items-center gap-2">
                {editing?.id === c.id ? (
                  <input
                    autoFocus
                    maxLength={100}
                    aria-label="클립 이름"
                    className="min-w-0 flex-1 rounded border border-sky-500 bg-zinc-900 px-1 py-0.5 text-sm text-white outline-none"
                    value={editing.text}
                    onChange={(e) => setEditing({ id: c.id, text: e.target.value })}
                    onBlur={commitRename}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitRename()
                      else if (e.key === 'Escape') setEditing(null)
                    }}
                  />
                ) : (
                  <>
                    <button
                      type="button"
                      className="min-w-0 flex-1 truncate text-left text-sm font-medium text-zinc-100 hover:text-white"
                      title={candidateTitle(c)}
                      onClick={() => p.onSelect(c)}
                    >
                      {candidateTitle(c)}
                    </button>
                    <button
                      type="button"
                      disabled={p.busy}
                      className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-700 hover:text-white disabled:opacity-40"
                      title="이름 바꾸기"
                      aria-label="이름 바꾸기"
                      onClick={() => setEditing({ id: c.id, text: candidateTitle(c) })}
                    >
                      <EditIcon />
                    </button>
                  </>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-zinc-400">
                <span>
                  {formatClock(s)}~{formatClock(e)} ({Math.round(e - s)}초)
                </span>
                {modified && (
                  <span className="rounded bg-orange-500/25 px-1.5 text-orange-300">{saved ? '수정됨 · 저장 대기' : '수정됨'}</span>
                )}
                <span className="ml-auto flex gap-1.5">
                  {saved && (
                    <button
                      type="button"
                      className={`rounded-md border px-2.5 py-1 transition hover:bg-zinc-600 active:scale-95 ${c.user.savedMemo ? 'border-amber-500/60 text-amber-300' : 'border-zinc-600/70 bg-zinc-800/60 text-zinc-200 hover:text-white'}`}
                      title="이 클립에 대한 나만의 메모(서버로 보내지 않음)"
                      aria-expanded={memoOpen === c.id}
                      onClick={() => p.onMemoOpenChange(memoOpen === c.id ? null : c.id)}
                    >
                      {c.user.savedMemo ? '메모 ●' : '메모'}
                    </button>
                  )}
                  {state.resave && (
                    <button
                      type="button"
                      disabled={p.busy || !p.canSave}
                      className="rounded-md bg-sky-600 px-2.5 py-1 text-white transition hover:bg-sky-500 active:scale-95 disabled:opacity-40"
                      title="고친 범위를 보관한 클립에 반영합니다"
                      onClick={() => p.onResave(c.id)}
                    >
                      {p.saving ? '저장 중…' : '다시 저장'}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={p.busy || (!saved && (!p.canSave || dismissed))}
                    aria-pressed={state.bookmark === 'archived'}
                    className={`flex items-center gap-1 rounded-md px-2.5 py-1 font-medium transition active:scale-95 disabled:opacity-40 ${
                      state.bookmark === 'none'
                        ? 'bg-sky-600 text-zinc-100 hover:bg-sky-500'
                        : 'bg-emerald-600/30 text-emerald-200 hover:bg-emerald-600/40'
                    }`}
                    title={state.bookmark === 'none' ? (saved ? '카테고리를 골라 보관합니다(클립을 그 카테고리로 옮깁니다)' : '클립으로 만들어 카테고리에 보관합니다') : `보관됨(${c.user.savedCategory ?? '카테고리 없음'}) — 눌러서 카테고리 바꾸기`}
                    data-archive-btn
                    onClick={(e) => p.onArchive(c.id, e.currentTarget.getBoundingClientRect())}
                  >
                    {state.bookmark === 'none' ? <BookmarkIcon /> : <BookmarkFilledIcon />}
                    {state.bookmark === 'none' ? '보관' : '보관됨'}
                  </button>
                  {state.deletable && (
                    <button
                      type="button"
                      disabled={p.busy}
                      className="rounded-md border border-rose-500/50 bg-rose-500/5 px-2.5 py-1 text-rose-300 transition hover:bg-rose-500/20 active:scale-95 disabled:opacity-40"
                      title="이 후보로 만든 클립 영상과 이 구간을 삭제합니다(되돌릴 수 없습니다)"
                      onClick={() => p.onDeleteClip(c.id)}
                    >
                      클립 삭제
                    </button>
                  )}
                  {c.id.includes('_u') ? (
                    <button
                      type="button"
                      disabled={p.busy}
                      className="rounded-md border border-zinc-600/70 bg-zinc-800/60 px-2.5 py-1 text-zinc-200 transition hover:bg-zinc-700 hover:text-white active:scale-95 disabled:opacity-40"
                      title="직접 추가한 구간을 지웁니다"
                      onClick={() => p.onDelete(c.id)}
                    >
                      구간 삭제
                    </button>
                  ) : (
                    !saved && (
                      <button
                        type="button"
                        disabled={p.busy}
                        className="rounded-md border border-zinc-600/70 bg-zinc-800/60 px-2.5 py-1 text-zinc-200 transition hover:bg-zinc-700 hover:text-white active:scale-95 disabled:opacity-40"
                        title="이 후보를 목록에서 삭제합니다"
                        onClick={() => p.onDismiss(c)}
                      >
                        {dismissed ? '되살리기' : '삭제'}
                      </button>
                    )
                  )}
                </span>
              </div>
              {saved && memoOpen === c.id && (
                <ClipMemoInput
                  clipId={c.id}
                  value={c.user.savedMemo}
                  rows={3}
                  compact
                  autoFocus
                  onSave={(memo) => p.onMemo(c.id, memo)}
                  onClose={() => p.onMemoOpenChange(null)}
                />
              )}
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
