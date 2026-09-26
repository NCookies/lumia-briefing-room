import { useEffect } from 'react'
import { updatedSummary } from '../update'

interface Props {
  from: string
  to: string
  onClose: () => void
  onShowNotes: () => void
}

/** 업데이트가 끝난 직후 한 번 보여, 사용자가 업데이트됐다는 사실을 알아보게 한다. */
export function UpdatedDialog({ from, to, onClose, onShowNotes }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === 'Enter') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[97] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex w-full max-w-sm flex-col items-center gap-4 rounded-lg border border-zinc-600 bg-zinc-800 p-6 text-center text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/20 text-2xl text-emerald-300">✓</div>
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-medium">업데이트가 완료되었습니다</h2>
          <p className="text-sm text-sky-300">{updatedSummary({ from, to })}</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded border border-zinc-600 px-4 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700"
            onClick={onShowNotes}
          >
            패치노트 보기
          </button>
          <button type="button" className="rounded bg-sky-600 px-4 py-1.5 text-sm text-white hover:bg-sky-500" onClick={onClose}>
            확인
          </button>
        </div>
      </div>
    </div>
  )
}
