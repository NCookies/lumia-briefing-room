import { useEffect } from 'react'
import { GuideContent } from './GuideContent'

export function GuideDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="사용 안내"
        className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-3 overflow-y-auto rounded-xl border border-zinc-600/70 bg-zinc-800 shadow-xl p-5 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">사용 안내</h2>
          <button type="button" className="rounded-md px-2 py-1 text-sm text-zinc-300 transition hover:bg-zinc-700" onClick={onClose}>
            닫기
          </button>
        </div>
        <GuideContent />
      </div>
    </div>
  )
}
