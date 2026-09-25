import { useEffect } from 'react'
import { parseReleaseNotes } from '../patchNotes'
import type { ReleaseInfo } from '../update'
import { PatchNoteSections } from './PatchNoteBody'

interface Props {
  release: ReleaseInfo
  currentVersion: string
  busy: boolean
  onUpdate: () => void
  onClose: () => void
}

export function ReleaseNotesDialog({ release, currentVersion, busy, onUpdate, onClose }: Props) {
  const sections = parseReleaseNotes(release.notes)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[96] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[85vh] w-full max-w-xl flex-col rounded-lg border border-zinc-600 bg-zinc-800 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-zinc-700 px-5 py-4">
          <div>
            <h2 className="text-lg font-medium">새 버전 v{release.version}</h2>
            <p className="mt-0.5 text-xs text-zinc-400">
              {currentVersion ? `현재 버전 v${currentVersion} → v${release.version}` : `v${release.version}`}
            </p>
          </div>
          <button type="button" className="text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            닫기 ✕
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
          {sections.length > 0 ? (
            <PatchNoteSections sections={sections} />
          ) : (
            <p className="text-sm text-zinc-400">이 버전에 적힌 변경 내용이 없습니다.</p>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-zinc-700 px-5 py-3">
          <button type="button" className="rounded px-4 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700" onClick={onClose}>
            나중에
          </button>
          <button
            type="button"
            className="rounded bg-sky-600 px-4 py-1.5 text-sm text-white hover:bg-sky-500 disabled:opacity-50"
            disabled={busy}
            onClick={() => {
              onUpdate()
              onClose()
            }}
          >
            업데이트
          </button>
        </div>
      </div>
    </div>
  )
}
