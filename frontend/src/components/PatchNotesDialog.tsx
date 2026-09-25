import { useEffect, useState } from 'react'
import { useAppInfo } from '../appInfo'
import { formatReleaseDate, isCurrentRelease, type PatchNoteRelease } from '../patchNotes'
import { getPatchNotes } from '../patchNotesApi'
import { PatchNoteSections } from './PatchNoteBody'

export function PatchNotesDialog({ onClose }: { onClose: () => void }) {
  const info = useAppInfo()
  const [releases, setReleases] = useState<PatchNoteRelease[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getPatchNotes()
      .then(setReleases)
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="flex h-[min(36rem,90vh)] w-full max-w-xl flex-col rounded-lg border border-zinc-600 bg-zinc-800 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
          <h2 className="text-base font-medium">패치노트</h2>
          <button type="button" className="text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            닫기 ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
          {error && <p className="text-sm text-rose-300">{error}</p>}
          {!releases && !error && <p className="text-sm text-zinc-400">불러오는 중…</p>}
          {releases?.length === 0 && <p className="text-sm text-zinc-400">아직 적힌 패치노트가 없습니다.</p>}
          {releases?.map((release) => (
            <section key={release.version} className="flex flex-col gap-2">
              <h3 className="flex items-baseline gap-2 text-sm font-medium text-zinc-100">
                v{release.version}
                {isCurrentRelease(release, info.version) && (
                  <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[11px] text-sky-300">현재 버전</span>
                )}
                <span className="text-xs font-normal text-zinc-500">{formatReleaseDate(release.date)}</span>
              </h3>
              <PatchNoteSections sections={release.sections} />
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
