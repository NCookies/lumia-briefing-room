import { useState } from 'react'
import { draftOf, parseDraft, type GameEditDraft, type GameEditPatch } from '../gameEdit'
import type { GameSummary } from '../games'

interface Props {
  game: Pick<GameSummary, 'gameMode' | 'matchResult' | 'matchResultSource'>
  onSave: (patch: GameEditPatch) => void
  onUnlock: () => void
  onCancel: () => void
}

const INPUT = 'w-20 rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm text-zinc-100'

/** `게임 정보 고치기`: 판독이 틀린 순위·일반/랭크·TK/K/A(코발트는 승리/패배)를 고친다. 저장하면 잠긴다. */
export function GameInfoDialog({ game, onSave, onUnlock, onCancel }: Props) {
  const cobalt = game.gameMode === 'cobalt'
  const locked = game.matchResultSource === 'manual'
  const [draft, setDraft] = useState<GameEditDraft>(() => draftOf(game.matchResult))
  const [error, setError] = useState<string | null>(null)
  const set = (patch: Partial<GameEditDraft>) => {
    setDraft((d) => ({ ...d, ...patch }))
    setError(null)
  }

  const submit = () => {
    const parsed = parseDraft(draft, cobalt)
    if (!parsed.ok) return setError(parsed.error)
    onSave(parsed.patch)
  }

  const number = (field: 'placement' | 'tk' | 'kills' | 'assists', label: string) => (
    <label className="flex items-center justify-between gap-3 text-sm">
      {label}
      <input inputMode="numeric" className={INPUT} value={draft[field]} onChange={(e) => set({ [field]: e.target.value })} />
    </label>
  )

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4" onClick={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex w-full max-w-sm flex-col gap-3 rounded-lg border border-zinc-600 bg-zinc-800 p-5 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onCancel()
          if (e.key === 'Enter') submit()
        }}
      >
        <h2 className="text-base font-medium">게임 정보 고치기</h2>
        {cobalt ? (
          <label className="flex items-center justify-between gap-3 text-sm">
            결과
            <select className={INPUT} value={draft.outcome} onChange={(e) => set({ outcome: e.target.value })}>
              <option value="">미확인</option>
              <option value="승리">승리</option>
              <option value="패배">패배</option>
            </select>
          </label>
        ) : (
          <>
            {number('placement', '순위')}
            <label className="flex items-center justify-between gap-3 text-sm">
              종류
              <select
                className={INPUT}
                value={draft.matchType}
                onChange={(e) => set({ matchType: e.target.value as GameEditDraft['matchType'] })}
              >
                <option value="unknown">미확인</option>
                <option value="normal">일반</option>
                <option value="rank">랭크</option>
              </select>
            </label>
          </>
        )}
        {number('tk', 'TK')}
        {number('kills', 'K')}
        {number('assists', 'A')}
        <p className="text-xs leading-relaxed text-zinc-400">
          저장하면 이 값으로 잠깁니다. 다시 분석하거나 과거 결과 채우기를 해도 덮어쓰지 않고, 이 게임의 클립 결과도 같은 값으로 바뀝니다.
        </p>
        {error && <p className="text-sm text-rose-300">{error}</p>}
        <div className="flex items-center justify-end gap-2">
          {locked && (
            <button
              type="button"
              className="mr-auto rounded px-2 py-1.5 text-xs text-amber-300 hover:bg-zinc-700"
              title="값은 그대로 두고 잠금만 풉니다. 이후 다시 분석이 새로 읽은 값으로 바꿀 수 있습니다."
              onClick={onUnlock}
            >
              잠금 해제
            </button>
          )}
          <button type="button" className="rounded px-4 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700" onClick={onCancel}>
            취소
          </button>
          <button type="button" autoFocus className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500" onClick={submit}>
            저장
          </button>
        </div>
      </div>
    </div>
  )
}
