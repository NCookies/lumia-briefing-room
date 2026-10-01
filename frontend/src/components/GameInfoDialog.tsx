import { useState } from 'react'
import { buildSave, draftOf, TITLE_MAX, type GameEditDraft, type GameEditPatch } from '../gameEdit'
import type { GameSummary } from '../games'

interface Props {
  game: Pick<GameSummary, 'gameMode' | 'matchResult' | 'matchResultSource' | 'title'>
  onSave: (body: { matchResult?: GameEditPatch; title?: string | null }) => void
  onCancel: () => void
}

const INPUT = 'w-20 rounded-md border border-zinc-600/70 bg-zinc-900 px-2 py-1 text-sm text-zinc-100'

/** `게임 정보 수정하기`: 제목과, 판독이 틀린 순위·일반/랭크·TK/K/A(코발트는 승리/패배)를 고친다. 저장하면 잠긴다. */
export function GameInfoDialog({ game, onSave, onCancel }: Props) {
  const cobalt = game.gameMode === 'cobalt'
  const [draft, setDraft] = useState<GameEditDraft>(() => draftOf(game.matchResult))
  const [title, setTitle] = useState(game.title ?? '')
  const [error, setError] = useState<string | null>(null)
  const set = (patch: Partial<GameEditDraft>) => {
    setDraft((d) => ({ ...d, ...patch }))
    setError(null)
  }

  const submit = () => {
    const plan = buildSave(draftOf(game.matchResult), draft, game.title, title, cobalt)
    if (!plan.ok) return setError(plan.error)
    onSave({
      ...(plan.result !== undefined && { matchResult: plan.result }),
      ...(plan.title !== undefined && { title: plan.title }),
    })
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
        className="flex w-full max-w-sm flex-col gap-3 rounded-xl border border-zinc-600/70 bg-zinc-800 shadow-xl p-5 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onCancel()
          if (e.key === 'Enter') submit()
        }}
      >
        <h2 className="text-base font-medium">게임 정보 수정하기</h2>
        <label className="flex flex-col gap-1 text-sm">
          제목
          <input
            className="rounded-md border border-zinc-600/70 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
            value={title}
            maxLength={TITLE_MAX}
            placeholder="제목 없음"
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
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
          순위·TK/K/A 를 고쳐 저장하면 그 값으로 고정됩니다. 다시 분석하거나 과거 결과 채우기를 해도 덮어쓰지 않고, 이 게임의 클립 결과도 같은 값으로 바뀝니다.
        </p>
        {error && <p className="text-sm text-rose-300">{error}</p>}
        <div className="flex items-center justify-end gap-2">
          <button type="button" className="rounded-md px-4 py-1.5 text-sm text-zinc-300 transition hover:bg-zinc-700" onClick={onCancel}>
            취소
          </button>
          <button type="button" autoFocus className="rounded-md bg-sky-600 px-4 py-1.5 text-sm transition hover:bg-sky-500" onClick={submit}>
            저장
          </button>
        </div>
      </div>
    </div>
  )
}
