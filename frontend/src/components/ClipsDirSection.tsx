import { useEffect, useState } from 'react'
import { getClipsDir, moveClipsDir, setClipsDirOnly, type ClipsSource } from '../clipsDirApi'
import { FolderPicker } from './FolderPicker'

interface Props {
  source: ClipsSource
  title: string
  description: string
  onChanged?: () => void
}

type Mode = 'view' | 'pick' | 'ask'

export function ClipsDirSection({ source, title, description, onChanged }: Props) {
  const [current, setCurrent] = useState('')
  const [draft, setDraft] = useState('')
  const [mode, setMode] = useState<Mode>('view')
  const [busy, setBusy] = useState(false)
  const [fraction, setFraction] = useState(0)
  const [moving, setMoving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    getClipsDir(source)
      .then(setCurrent)
      .catch((e: Error) => setStatus(e.message))
  }, [source])

  const apply = async (move: boolean) => {
    setBusy(true)
    setMoving(move)
    setFraction(0)
    setStatus(null)
    try {
      if (move) {
        const { moved, oldPath } = await moveClipsDir(source, draft, setFraction)
        setStatus(
          moved > 0
            ? `클립 ${moved}개를 새 폴더로 옮겼습니다.`
            : `이전 폴더(${oldPath})에 옮길 클립이 없어 폴더만 바꿨습니다. 새 폴더에 이미 있는 클립은 그대로 보입니다.`,
        )
      } else {
        await setClipsDirOnly(source, draft)
        setStatus('폴더만 바꿨습니다. 기존 클립은 이전 폴더에 그대로 있고 목록에는 보이지 않습니다. 이전 폴더로 되돌리면 다시 보입니다.')
      }
      setCurrent(draft)
      setMode('view')
      onChanged?.()
    } catch (e) {
      setStatus((e as Error).message)
      setMode('pick')
    } finally {
      setBusy(false)
    }
  }

  const percent = Math.round(fraction * 100)

  const choose = () => {
    if (draft === current) return setMode('view')
    setMode('ask')
  }

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-200">{title}</h3>
      <p className="text-xs text-zinc-500">{description}</p>
      {mode === 'view' && (
        <div className="flex items-center gap-2">
          <div className="flex-1 truncate rounded bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200" title={current}>
            {current || '기본 위치'}
          </div>
          <button
            type="button"
            className="rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700"
            onClick={() => {
              setDraft(current)
              setStatus(null)
              setMode('pick')
            }}
          >
            바꾸기
          </button>
        </div>
      )}
      {mode === 'pick' && (
        <>
          <FolderPicker value={draft} onChange={setDraft} />
          <div className="flex justify-end gap-2">
            <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={() => setMode('view')}>
              취소
            </button>
            <button
              type="button"
              className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40"
              disabled={draft === ''}
              onClick={choose}
            >
              이 폴더로 지정
            </button>
          </div>
        </>
      )}
      {mode === 'ask' && (
        <div className="flex flex-col gap-2 rounded border border-amber-600/60 bg-zinc-900/60 p-3">
          <p className="truncate text-xs text-zinc-400" title={draft}>
            새 폴더: {draft}
          </p>
          <p className="text-sm text-zinc-100">기존 클립도 새 폴더로 옮길까요?</p>
          <p className="text-xs text-amber-300">
            옮기지 않으면 기존 클립은 이전 폴더에 남고, 새 폴더를 쓰는 동안 목록에 보이지 않습니다.
          </p>
          {busy && moving && (
            <div className="h-2 overflow-hidden rounded bg-zinc-700" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full bg-sky-500 transition-[width]" style={{ width: `${percent}%` }} />
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="text-sm text-zinc-400 hover:text-zinc-100 disabled:opacity-40"
              disabled={busy}
              onClick={() => setMode('pick')}
            >
              취소
            </button>
            <button
              type="button"
              className="rounded border border-zinc-600 px-3 py-1.5 text-sm hover:bg-zinc-700 disabled:opacity-40"
              disabled={busy}
              onClick={() => void apply(false)}
            >
              아니오, 폴더만 바꾸기
            </button>
            <button
              type="button"
              className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40"
              disabled={busy}
              onClick={() => void apply(true)}
            >
              {busy && moving ? `옮기는 중… ${percent}%` : '예, 옮기기'}
            </button>
          </div>
        </div>
      )}
      {status && <p className="text-xs text-zinc-400">{status}</p>}
    </section>
  )
}
