import { useState } from 'react'
import { GameInfoDialog } from './components/GameInfoDialog'
import type { GameMenuItem } from './components/GameMenu'
import type { GameEditPatch } from './gameEdit'
import type { GameSummary } from './games'
import { setGameResult, setGameTitle, unlockGameResult } from './gamesApi'

type Editable = Pick<GameSummary, 'gameMode' | 'matchResult' | 'matchResultSource'>

/** `게임 정보 고치기` 메뉴 항목·대화상자와 행 제목 저장. 두 탭의 목록·풀영상 화면이 같이 쓴다. */
export function useGameEdit(options: { onDone: () => void; onError: (message: string) => void }) {
  const [target, setTarget] = useState<{ key: string; game: Editable } | null>(null)

  const run = async (action: () => Promise<unknown>) => {
    try {
      await action()
    } catch (e) {
      options.onError((e as Error).message)
    } finally {
      options.onDone()
    }
  }

  const menuItem = (key: string, game: Editable): GameMenuItem => ({
    label: '게임 정보 고치기',
    title: '순위·일반/랭크·TK/K/A 를 직접 고칩니다. 고친 값은 다시 분석해도 유지됩니다',
    onSelect: () => setTarget({ key, game }),
  })

  const dialog = target && (
    <GameInfoDialog
      game={target.game}
      onCancel={() => setTarget(null)}
      onSave={(patch: GameEditPatch) => {
        const key = target.key
        setTarget(null)
        void run(() => setGameResult(key, patch))
      }}
      onUnlock={() => {
        const key = target.key
        setTarget(null)
        void run(() => unlockGameResult(key))
      }}
    />
  )

  return { menuItem, dialog, saveTitle: (key: string, title: string | null) => run(() => setGameTitle(key, title)) }
}
