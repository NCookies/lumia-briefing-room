import { useState } from 'react'
import { DeleteConfirmDialog } from './components/DeleteConfirmDialog'
import type { DeleteMode } from './deleteConfirm'
import type { GameMenuItem } from './components/GameMenu'
import { deleteMenuItems, deleteWarning, mustAskBeforeDelete, type DeletableGame, type DeleteTarget } from './gameDelete'
import { deleteGameFiles } from './gamesApi'
import { setDeleteMode } from './exportApi'

export interface GameDeleteOptions {
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
  deleteMode: DeleteMode
  onDeleteModeChange: (value: DeleteMode) => void
  onDone: () => void
  onError: (message: string) => void
}

interface Pending {
  key: string
  game: DeletableGame
  target: DeleteTarget
}

/** 게임 행 `⋯` 메뉴의 삭제 동작. 두 탭이 같이 쓴다. 고정한 게임은 "다시 묻지 않기"를 켰어도 묻는다. */
export function useGameDelete(options: GameDeleteOptions) {
  const [pending, setPending] = useState<Pending | null>(null)

  const run = async (request: Pending, mode: DeleteMode) => {
    try {
      if (mode !== options.deleteMode) {
        await setDeleteMode(mode)
        options.onDeleteModeChange(mode)
      }
      await deleteGameFiles(request.key, request.target)
    } catch (e) {
      options.onError((e as Error).message)
    } finally {
      options.onDone()
    }
  }

  const request = (key: string, game: DeletableGame, target: DeleteTarget) => {
    const next = { key, game, target }
    if (!mustAskBeforeDelete(game, options.confirmDelete)) void run(next, options.deleteMode)
    else setPending(next)
  }

  /** 행 `⋯` 메뉴 항목. `extra` 는 삭제 위에 붙는 다른 동작(다시 분석 등). */
  const menuFor = (key: string, game: DeletableGame, extra: GameMenuItem[] = []): GameMenuItem[] => [
    ...extra,
    ...deleteMenuItems(game).map((item) => ({
      label: item.label,
      disabled: item.disabled,
      danger: true,
      onSelect: () => request(key, game, item.target),
    })),
  ]

  const dialog = pending && (
    <DeleteConfirmDialog
      label={deleteWarning(pending.game, pending.target)}
      deleteMode={options.deleteMode}
      onCancel={() => setPending(null)}
      onConfirm={({ mode, skipNext }) => {
        const current = pending
        setPending(null)
        if (skipNext) options.onConfirmDeleteChange(false)
        void run(current, mode)
      }}
    />
  )

  return { menuFor, dialog }
}
