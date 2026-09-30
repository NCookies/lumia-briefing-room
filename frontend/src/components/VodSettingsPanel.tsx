import { useCallback, useEffect, useState } from 'react'
import { getVodSettings, pickVideoFiles, saveVodSettings } from '../vodApi'
import { needsAlwaysPermanentWarning, type DeleteSourceAfter, type DeleteSourceMode } from '../vodDeleteSource'
import { useConfirm } from '../confirmContext'
import { pickFolder } from '../exportApi'
import { VideoFormatHelp } from './VideoFormatHelp'

export function VodSettingsPanel({ onClipsDirChanged }: { onClipsDirChanged: () => void }) {
  const ask = useConfirm()
  const [sources, setSources] = useState<string[]>([])
  const [recursive, setRecursive] = useState(false)
  const [deleteSourceAfter, setDeleteSourceAfterState] = useState<DeleteSourceAfter>('ask')
  const [deleteSourceMode, setDeleteSourceModeState] = useState<DeleteSourceMode>('trash')
  const [picking, setPicking] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  const load = useCallback(() => {
    getVodSettings()
      .then((s) => {
        setSources(s.sources)
        setRecursive(s.recursive)
        setDeleteSourceAfterState(s.deleteSourceAfter)
        setDeleteSourceModeState(s.deleteSourceMode)
      })
      .catch((e: Error) => setStatus(e.message))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const saveSources = async (next: string[]) => {
    setStatus(null)
    try {
      await saveVodSettings({ vod: { sources: next } })
      setSources(next)
      onClipsDirChanged()
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  const addPaths = async (paths: string[]) => {
    const fresh = paths.filter((p) => !sources.includes(p))
    if (fresh.length === 0) return paths.length > 0 ? setStatus('이미 추가한 경로입니다') : undefined
    await saveSources([...sources, ...fresh])
  }

  const browse = async (pick: () => Promise<string[]>) => {
    setPicking(true)
    setStatus(null)
    try {
      await addPaths(await pick())
    } catch (e) {
      setStatus((e as Error).message)
    } finally {
      setPicking(false)
    }
  }

  const pickFolders = async () => {
    const chosen = await pickFolder('', '영상 파일이 든 폴더 선택')
    return chosen ? [chosen] : []
  }

  const toggleRecursive = async (value: boolean) => {
    setStatus(null)
    try {
      await saveVodSettings({ vod: { recursive: value } })
      setRecursive(value)
      onClipsDirChanged()
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  const confirmAlwaysPermanent = async (after: DeleteSourceAfter, mode: DeleteSourceMode) => {
    if (!needsAlwaysPermanentWarning(after, mode)) return true
    const result = await ask({
      message: '항상 삭제 + 즉시 완전 삭제를 함께 켜면, 분석이 끝난 원본 영상이 확인 없이 복구할 수 없게 지워집니다. 계속하시겠습니까?',
      confirmLabel: '계속',
      danger: true,
    })
    return result.ok
  }

  const changeDeleteSourceAfter = async (value: DeleteSourceAfter) => {
    setStatus(null)
    if (!(await confirmAlwaysPermanent(value, deleteSourceMode))) return
    try {
      await saveVodSettings({ vod: { deleteSourceAfter: value } })
      setDeleteSourceAfterState(value)
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  const changeDeleteSourceMode = async (value: DeleteSourceMode) => {
    setStatus(null)
    if (!(await confirmAlwaysPermanent(deleteSourceAfter, value))) return
    try {
      await saveVodSettings({ vod: { deleteSourceMode: value } })
      setDeleteSourceModeState(value)
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-200">
          영상 경로
          <VideoFormatHelp />
        </h3>
        <p className="text-xs text-zinc-500">
          OBS 등으로 녹화해 둔 영상 파일, 또는 그 영상들이 든 폴더를 추가합니다. 앱은 영상을 내려받거나 옮기지 않으며,
          아래에서 직접 켠 경우에만 분석이 끝난 원본을 지웁니다(기본은 읽기만 합니다).
        </p>
        <ul className="flex flex-col gap-1">
          {sources.length === 0 && <li className="text-sm text-zinc-500">추가한 경로가 없습니다</li>}
          {sources.map((path) => (
            <li key={path} className="flex items-center justify-between rounded bg-zinc-900 px-3 py-1.5 text-sm">
              <span className="truncate text-zinc-200" title={path}>
                {path}
              </span>
              <button
                type="button"
                className="ml-3 shrink-0 text-xs text-zinc-400 hover:text-rose-400"
                onClick={() => saveSources(sources.filter((p) => p !== path))}
              >
                목록에서 빼기
              </button>
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40"
            disabled={picking}
            onClick={() => void browse(() => pickVideoFiles())}
          >
            + 영상 파일 추가…
          </button>
          <button
            type="button"
            className="rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40"
            disabled={picking}
            onClick={() => void browse(pickFolders)}
          >
            + 폴더 추가…
          </button>
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input type="checkbox" checked={recursive} onChange={(e) => toggleRecursive(e.target.checked)} />
          폴더 경로는 하위 폴더까지 찾기
        </label>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-zinc-200">분석 후 원본 영상 삭제</h3>
        <p className="text-xs text-zinc-500">
          클립 추출이 끝난 원본 영상 파일을 지울지 정합니다. 분석에 성공해 클립이 1개 이상 나온 영상만 대상이고,
          취소·실패했거나 클립이 하나도 안 나온 영상은 지우지 않습니다.
        </p>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <select
            className="rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
            value={deleteSourceAfter}
            onChange={(e) => changeDeleteSourceAfter(e.target.value as DeleteSourceAfter)}
          >
            <option value="ask">분석 시작할 때마다 묻기</option>
            <option value="always">항상 삭제</option>
            <option value="never">삭제 안 함</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          삭제 방식
          <select
            className="rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
            value={deleteSourceMode}
            onChange={(e) => changeDeleteSourceMode(e.target.value as DeleteSourceMode)}
          >
            <option value="trash">Windows 휴지통으로 이동 (기본)</option>
            <option value="permanent">즉시 완전 삭제</option>
          </select>
        </label>
      </section>

      <section className="flex flex-col gap-1">
        <h3 className="text-sm font-medium text-zinc-200">영상 파일 클립 저장 위치</h3>
        <p className="text-xs text-zinc-500">
          일반 탭의 저장 폴더 안 클립 폴더(영상 파일)에 저장됩니다. 저장 폴더를 바꾸려면 일반 탭에서 바꾸세요.
        </p>
      </section>

      {status && <p className="text-xs text-zinc-400">{status}</p>}
    </div>
  )
}
