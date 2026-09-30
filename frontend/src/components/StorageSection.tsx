import { useCallback, useEffect, useState } from 'react'
import { getStorage, migrateStorage, undoStorage, type StorageInfo } from '../storageApi'
import { recordingDiskWarning, samePath, structureLines, suggestedRootFromLegacy } from '../storage'
import { FolderPicker } from './FolderPicker'

interface Props {
  variant?: 'options' | 'firstRun'
  onChanged?: () => void
}

type Mode = 'view' | 'pickRoot' | 'confirmRoot' | 'pickFull' | 'confirmFull' | 'confirmUndo'

const BTN = 'rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40'
const PRIMARY = 'rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40'

export function StorageSection({ variant = 'options', onChanged }: Props) {
  const [info, setInfo] = useState<StorageInfo | null>(null)
  const [mode, setMode] = useState<Mode>('view')
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [fraction, setFraction] = useState(0)
  const [status, setStatus] = useState<string | null>(null)

  const load = useCallback(() => {
    getStorage()
      .then(setInfo)
      .catch((e: Error) => setStatus(e.message))
  }, [])

  useEffect(load, [load])

  if (!info) return <p className="text-sm text-zinc-500">{status ?? '저장 위치를 불러오는 중…'}</p>

  const isNew = info.layout === 'new'
  const root = info.root ?? ''
  const percent = Math.round(fraction * 100)
  const diskWarning = recordingDiskWarning(info.recordingSameDisk)

  const run = async (newRoot: string, fullVideos: string | null, done: string) => {
    setBusy(true)
    setFraction(0)
    setStatus(null)
    try {
      const { moved } = await migrateStorage(newRoot, fullVideos, setFraction)
      setStatus(`${done}${moved > 0 ? ` (파일 ${moved}개)` : ''}`)
      setMode('view')
      load()
      onChanged?.()
    } catch (e) {
      setStatus((e as Error).message)
      setMode('view')
    } finally {
      setBusy(false)
    }
  }

  const undo = async () => {
    setBusy(true)
    setStatus(null)
    try {
      setStatus((await undoStorage()) ? '이전 위치로 되돌렸습니다.' : '되돌릴 기록이 없습니다.')
      setMode('view')
      load()
      onChanged?.()
    } catch (e) {
      setStatus((e as Error).message)
      setMode('view')
    } finally {
      setBusy(false)
    }
  }

  const progress = busy && (
    <div className="h-2 overflow-hidden rounded bg-zinc-700" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full bg-sky-500 transition-[width]" style={{ width: `${percent}%` }} />
    </div>
  )

  const startPickRoot = () => {
    setDraft(isNew ? root : (info.suggestedRoot ?? suggestedRootFromLegacy(info.legacy.clips)))
    setStatus(null)
    setMode('pickRoot')
  }

  const startPickFull = () => {
    setDraft(info.fullVideos ?? '')
    setStatus(null)
    setMode('pickFull')
  }

  return (
    <section className="flex flex-col gap-2" data-testid="storage-section">
      <h3 className={variant === 'firstRun' ? 'text-base font-medium' : 'text-sm font-medium text-zinc-200'}>저장 폴더</h3>

      {isNew ? (
        <>
          <p className="text-xs text-zinc-500">
            폴더 하나만 고르면 그 안에 클립과 풀영상이 나뉘어 저장됩니다. 클립 정보(제목·태그 등)는 앱 데이터 폴더에 따로 있습니다.
          </p>
          <div className="flex items-center gap-2">
            <div className="flex-1 truncate rounded bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200" title={root}>
              {root}
            </div>
            {mode === 'view' && (
              <button type="button" className={BTN} onClick={startPickRoot}>
                바꾸기
              </button>
            )}
          </div>
          <ul className="flex flex-col gap-1 rounded border border-zinc-700 bg-zinc-900/60 p-2 text-xs text-zinc-400">
            {structureLines(root, info.fullVideos).map((line) => (
              <li key={line.path}>
                <span className="font-mono text-zinc-300">{line.path}</span>
                <span className="block">{line.note}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <p className="text-xs text-zinc-500">
            이전 버전에서 쓰던 폴더를 그대로 쓰는 중입니다. 저장 폴더 하나로 정리하면 클립과 풀영상이 그 안의 폴더로 나뉩니다. 옮기기는 원할 때만
            하면 되고, 옮기지 않아도 모든 기능이 그대로 동작합니다.
          </p>
          <ul className="flex flex-col gap-1 rounded border border-zinc-700 bg-zinc-900/60 p-2 text-xs text-zinc-400">
            <li>스팀 녹화 클립: <span className="font-mono text-zinc-300">{info.legacy.clips}</span></li>
            <li>영상 파일 클립: <span className="font-mono text-zinc-300">{info.legacy.vodClips}</span></li>
            <li>풀영상: <span className="font-mono text-zinc-300">{info.legacy.games}</span></li>
          </ul>
          {mode === 'view' && (
            <div>
              <button type="button" className={BTN} onClick={startPickRoot}>
                새 구조로 옮기기…
              </button>
            </div>
          )}
        </>
      )}

      {diskWarning && mode === 'view' && (
        <p className="rounded border border-amber-600/60 bg-amber-950/30 px-3 py-2 text-xs text-amber-300" data-testid="recording-disk-warning">
          {diskWarning}
        </p>
      )}

      {mode === 'pickRoot' && (
        <div className="flex flex-col gap-2 rounded border border-zinc-600 bg-zinc-900/60 p-3">
          <p className="text-xs text-zinc-400">
            {isNew ? '새 저장 폴더를 고르세요.' : '클립과 풀영상을 모아 둘 폴더를 고르세요. 이 폴더 안에 clips·full_video 폴더가 만들어집니다.'}
          </p>
          <FolderPicker value={draft} onChange={setDraft} />
          <div className="flex justify-end gap-2">
            <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={() => setMode('view')}>
              취소
            </button>
            <button
              type="button"
              className={PRIMARY}
              disabled={draft === '' || (isNew && samePath(draft, root))}
              onClick={() => setMode('confirmRoot')}
            >
              이 폴더로 지정
            </button>
          </div>
        </div>
      )}

      {mode === 'confirmRoot' && (
        <div className="flex flex-col gap-2 rounded border border-amber-600/60 bg-zinc-900/60 p-3">
          <p className="truncate text-xs text-zinc-400" title={draft}>
            새 저장 폴더: {draft}
          </p>
          <p className="text-sm text-zinc-100">기존 클립과 풀영상을 이 폴더로 옮깁니다.</p>
          <p className="text-xs text-amber-300">
            영상 용량에 따라 몇 분 걸릴 수 있고, 옮기는 동안 다른 작업(게임 분석 등)은 할 수 없습니다. 새 폴더에 같은 이름의 파일이 있으면 아무것도
            옮기지 않고 멈춥니다. 끝난 뒤에도 이 화면에서 이전 위치로 되돌릴 수 있습니다.
          </p>
          {progress}
          <div className="flex justify-end gap-2">
            <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100 disabled:opacity-40" disabled={busy} onClick={() => setMode('pickRoot')}>
              취소
            </button>
            <button
              type="button"
              className={PRIMARY}
              disabled={busy}
              onClick={() => void run(draft, isNew ? info.fullVideos : null, '새 저장 폴더로 옮겼습니다.')}
            >
              {busy ? `옮기는 중… ${percent}%` : '옮기기'}
            </button>
          </div>
        </div>
      )}

      {isNew && mode !== 'pickRoot' && mode !== 'confirmRoot' && (
        <details className="rounded border border-zinc-700 bg-zinc-900/40 px-3 py-2 text-sm" open={info.fullVideos !== null}>
          <summary className="cursor-pointer text-zinc-300">고급: 풀영상 위치만 따로 두기</summary>
          <p className="mt-2 text-xs text-zinc-500">
            풀영상은 한 판에 수 GB 라 큰 하드디스크로 빼고 싶을 때만 쓰세요. 기본은 저장 폴더 아래 full_video 폴더입니다. 저장 공간 경고는 풀영상이 있는
            드라이브 기준입니다.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <div className="flex-1 truncate rounded bg-zinc-900 px-3 py-1.5 text-xs text-zinc-200" title={info.resolved.fullVideos}>
              {info.resolved.fullVideos}
            </div>
            {mode === 'view' && (
              <>
                <button type="button" className={BTN} onClick={startPickFull}>
                  바꾸기
                </button>
                {info.fullVideos !== null && (
                  <button type="button" className={BTN} onClick={() => void run(root, null, '풀영상을 기본 위치로 옮겼습니다.')} disabled={busy}>
                    기본 위치로
                  </button>
                )}
              </>
            )}
          </div>
          {mode === 'pickFull' && (
            <div className="mt-2 flex flex-col gap-2">
              <FolderPicker value={draft} onChange={setDraft} />
              <div className="flex justify-end gap-2">
                <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={() => setMode('view')}>
                  취소
                </button>
                <button type="button" className={PRIMARY} disabled={draft === '' || samePath(draft, info.resolved.fullVideos)} onClick={() => setMode('confirmFull')}>
                  이 폴더로 지정
                </button>
              </div>
            </div>
          )}
          {mode === 'confirmFull' && (
            <div className="mt-2 flex flex-col gap-2">
              <p className="truncate text-xs text-zinc-400" title={draft}>
                새 풀영상 폴더: {draft}
              </p>
              <p className="text-xs text-amber-300">기존 풀영상을 이 폴더로 옮깁니다. 용량에 따라 오래 걸릴 수 있습니다.</p>
              {progress}
              <div className="flex justify-end gap-2">
                <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100 disabled:opacity-40" disabled={busy} onClick={() => setMode('pickFull')}>
                  취소
                </button>
                <button type="button" className={PRIMARY} disabled={busy} onClick={() => void run(root, draft, '풀영상을 새 위치로 옮겼습니다.')}>
                  {busy ? `옮기는 중… ${percent}%` : '옮기기'}
                </button>
              </div>
            </div>
          )}
        </details>
      )}

      {info.canUndo && mode === 'view' && (
        <div>
          <button type="button" className="text-xs text-zinc-400 underline hover:text-zinc-100" onClick={() => setMode('confirmUndo')}>
            직전에 옮긴 것을 이전 위치로 되돌리기
          </button>
        </div>
      )}
      {mode === 'confirmUndo' && (
        <div className="flex flex-col gap-2 rounded border border-amber-600/60 bg-zinc-900/60 p-3">
          <p className="text-sm text-zinc-100">직전에 옮긴 영상을 원래 위치로 되돌리고 이전 설정으로 돌아갑니다.</p>
          <p className="text-xs text-amber-300">그 뒤 원래 위치에 같은 이름의 파일이 새로 생겼다면 아무것도 옮기지 않고 멈춥니다.</p>
          <div className="flex justify-end gap-2">
            <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100 disabled:opacity-40" disabled={busy} onClick={() => setMode('view')}>
              취소
            </button>
            <button type="button" className={PRIMARY} disabled={busy} onClick={() => void undo()}>
              {busy ? '되돌리는 중…' : '되돌리기'}
            </button>
          </div>
        </div>
      )}

      {status && <p className="text-xs text-zinc-400">{status}</p>}
    </section>
  )
}
