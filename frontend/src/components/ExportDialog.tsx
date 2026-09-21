import { useEffect, useState } from 'react'
import { exportClip, getExportDefault } from '../exportApi'
import type { Clip } from '../types'
import { FolderPicker } from './FolderPicker'

interface Props {
  clip: Clip
  onClose: () => void
}

export function ExportDialog({ clip, onClose }: Props) {
  const [dir, setDir] = useState('')
  const [ready, setReady] = useState(false)
  const [filename, setFilename] = useState(clip.title)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedPath, setSavedPath] = useState<string | null>(null)

  useEffect(() => {
    getExportDefault()
      .then(setDir)
      .catch(() => {})
      .finally(() => setReady(true))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const { path } = await exportClip(clip.id, dir, filename.trim() || clip.title)
      setSavedPath(path)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => {
        e.stopPropagation()
        onClose()
      }}
    >
      <div
        className="flex w-full max-w-lg flex-col gap-3 rounded-lg border border-zinc-600 bg-zinc-800 p-4 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-medium">영상 저장</h2>

        <label className="flex flex-col gap-1 text-sm text-zinc-300">
          파일 이름
          <input
            className="rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-zinc-100"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
          />
        </label>

        <div className="text-sm text-zinc-300">저장할 폴더</div>
        {ready && <FolderPicker value={dir} onChange={setDir} />}

        {error && <p className="text-sm text-rose-400">{error}</p>}
        {savedPath && <p className="break-all text-sm text-emerald-400">저장했습니다: {savedPath}</p>}

        <div className="flex justify-end gap-2">
          <button type="button" className="rounded px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700" onClick={onClose}>
            {savedPath ? '닫기' : '취소'}
          </button>
          <button
            type="button"
            className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40"
            disabled={busy || dir === ''}
            onClick={save}
          >
            {busy ? '저장 중...' : '이 폴더에 저장'}
          </button>
        </div>
      </div>
    </div>
  )
}
