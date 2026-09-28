import { useState } from 'react'
import { migrateLegacyTrash } from '../legacyTrashApi'

interface Props {
  count: number
  onDone: () => void
  onLater: () => void
}

export function LegacyTrashDialog({ count, onDone, onLater }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (action: 'restore' | 'recycle') => {
    setBusy(true)
    setError(null)
    try {
      await migrateLegacyTrash(action)
      onDone()
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/70 p-4">
      <div
        role="dialog"
        aria-modal="true"
        className="flex w-full max-w-md flex-col gap-4 rounded-lg border border-zinc-600 bg-zinc-800 p-5 text-zinc-100"
      >
        <h2 className="text-base font-medium">이전 버전의 휴지통에 클립 {count}개가 있습니다</h2>
        <p className="text-sm text-zinc-300">
          이 앱은 더 이상 자체 휴지통을 쓰지 않습니다. 예전에 삭제한 클립을 클립 목록으로 되돌리거나,
          Windows 휴지통으로 보내 정리할 수 있습니다.
        </p>
        {error && <p className="text-sm text-rose-400">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="rounded px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            disabled={busy}
            onClick={onLater}
          >
            나중에
          </button>
          <button
            type="button"
            className="rounded border border-zinc-600 px-3 py-1.5 text-sm hover:bg-zinc-700 disabled:opacity-50"
            disabled={busy}
            onClick={() => run('recycle')}
          >
            Windows 휴지통으로 보내기
          </button>
          <button
            type="button"
            className="rounded bg-sky-600 px-3 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-50"
            disabled={busy}
            onClick={() => run('restore')}
          >
            클립 목록으로 복구
          </button>
        </div>
      </div>
    </div>
  )
}
