import { useState } from 'react'
import { GameInfoDialog } from './components/GameInfoDialog'
import type { GameMenuItem } from './components/GameMenu'
import type { GameSummary } from './games'
import { saveGameInfo } from './gamesApi'

type Editable = Pick<GameSummary, 'gameMode' | 'matchResult' | 'matchResultSource' | 'title'>

/** `게임 정보 수정하기` 메뉴 항목·대화상자(제목·순위·TK/K/A). 두 탭의 목록·풀영상 화면이 같이 쓴다. */
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
    label: '게임 정보 수정하기',
    title: '제목과 순위·일반/랭크·TK/K/A 를 직접 고칩니다. 고친 순위·TK/K/A 는 다시 분석해도 유지됩니다',
    onSelect: () => setTarget({ key, game }),
  })

  const dialog = target && (
    <GameInfoDialog
      game={target.game}
      onCancel={() => setTarget(null)}
      onSave={(body) => {
        const key = target.key
        setTarget(null)
        if (Object.keys(body).length > 0) void run(() => saveGameInfo(key, body))
      }}
    />
  )

  return { menuItem, dialog, saveTitle: (key: string, title: string | null) => run(() => saveGameInfo(key, { title })) }
}
