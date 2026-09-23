import { useCallback, useEffect, useState } from 'react'
import { formatBytes } from '../retention'
import { getVodSettings, listVideos, saveVodSettings, type VideoListing } from '../vodApi'
import { ClipsDirSection } from './ClipsDirSection'

function join(base: string, name: string): string {
  return base === '' || /[\\/]$/.test(base) ? `${base}${name}` : `${base}\\${name}`
}

function VideoPathPicker({ onAdd, onClose }: { onAdd: (path: string) => void; onClose: () => void }) {
  const [path, setPath] = useState('')
  const [listing, setListing] = useState<VideoListing | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listVideos(path)
      .then((l) => {
        if (cancelled) return
        setListing(l)
        setError(null)
      })
      .catch((e: Error) => {
        if (cancelled) return
        setError(e.message)
        if (path !== '') setPath('')
      })
    return () => {
      cancelled = true
    }
  }, [path])

  return (
    <div className="flex flex-col gap-2 rounded border border-zinc-600 bg-zinc-900/60 p-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-30"
          disabled={!listing || path === ''}
          onClick={() => setPath(listing?.parent ?? '')}
          title="상위 폴더"
        >
          ↑
        </button>
        <div className="flex-1 truncate rounded bg-zinc-900 px-2 py-1 text-sm text-zinc-200" title={path}>
          {path || '내 컴퓨터 (드라이브를 선택하세요)'}
        </div>
        <button
          type="button"
          className="rounded bg-sky-600 px-3 py-1 text-sm hover:bg-sky-500 disabled:opacity-40"
          disabled={path === ''}
          onClick={() => onAdd(path)}
          title="이 폴더 안의 영상을 모두 목록에 추가합니다"
        >
          이 폴더 추가
        </button>
        <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={onClose}>
          닫기
        </button>
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      <ul className="h-56 overflow-y-auto rounded border border-zinc-700">
        {listing?.dirs.map((name) => (
          <li key={`d-${name}`}>
            <button
              type="button"
              className="w-full px-3 py-1.5 text-left text-sm text-zinc-200 hover:bg-zinc-700"
              onClick={() => setPath(join(listing.path, name))}
            >
              📁 {name}
            </button>
          </li>
        ))}
        {listing?.files.map((file) => (
          <li key={`f-${file.name}`} className="flex items-center justify-between px-3 py-1.5 hover:bg-zinc-700/50">
            <span className="truncate text-sm text-zinc-100">🎞 {file.name}</span>
            <span className="ml-3 flex shrink-0 items-center gap-3 text-xs text-zinc-400">
              {formatBytes(file.sizeBytes)}
              <button
                type="button"
                className="text-sky-400 hover:underline"
                onClick={() => onAdd(join(listing.path, file.name))}
              >
                추가
              </button>
            </span>
          </li>
        ))}
        {listing && listing.dirs.length === 0 && listing.files.length === 0 && (
          <li className="px-3 py-2 text-sm text-zinc-500">폴더나 영상 파일이 없습니다</li>
        )}
      </ul>
    </div>
  )
}

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

  const add = (path: string) => {
    if (sources.includes(path)) return setStatus('이미 추가한 경로입니다')
    saveSources([...sources, path])
    setPicking(false)
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
        {picking ? (
          <VideoPathPicker onAdd={add} onClose={() => setPicking(false)} />
        ) : (
          <button
            type="button"
            className="self-start rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700"
            onClick={() => setPicking(true)}
          >
            + 영상 또는 폴더 추가
          </button>
        )}
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
