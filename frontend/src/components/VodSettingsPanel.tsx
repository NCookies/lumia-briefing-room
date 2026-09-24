import { useCallback, useEffect, useState } from 'react'
import { getVodSettings, pickVideoFiles, saveVodSettings } from '../vodApi'
import { pickFolder } from '../exportApi'
import { ClipsDirSection } from './ClipsDirSection'

export function VodSettingsPanel({ onClipsDirChanged }: { onClipsDirChanged: () => void }) {
  const [sources, setSources] = useState<string[]>([])
  const [recursive, setRecursive] = useState(false)
  const [picking, setPicking] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  const load = useCallback(() => {
    getVodSettings()
      .then((s) => {
        setSources(s.sources)
        setRecursive(s.recursive)
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
    const chosen = await pickFolder('', '다시보기 영상이 든 폴더 선택')
    return chosen ? [chosen] : []
  }

  const toggleRecursive = async (value: boolean) => {
    setStatus(null)
    try {
      await saveVodSettings({ vod: { recursive: value } })
      setRecursive(value)
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-zinc-200">다시보기 영상 경로</h3>
        <p className="text-xs text-zinc-500">
          받아 둔 다시보기 영상 파일이나 그 영상들이 든 폴더를 추가합니다. 앱은 영상을 받지도 옮기거나 지우지도 않고 읽기만 합니다.
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

      <ClipsDirSection
        source="vod"
        title="다시보기 클립 저장 폴더"
        description="내 녹화 클립과 섞이지 않게 따로 저장합니다. 비워 두면 기본 위치(내 비디오 폴더의 LumiaBriefingRoom)를 씁니다."
        onChanged={onClipsDirChanged}
      />

      {status && <p className="text-xs text-zinc-400">{status}</p>}
    </div>
  )
}
