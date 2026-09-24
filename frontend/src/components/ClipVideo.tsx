import { useCallback, useEffect, useRef, useState } from 'react'
import { getProxyStatus, prefetchProxy, proxyVideoUrl, startProxy, videoUrl, type ProxyStatus } from '../api'
import {
  browserCanPlayHevc,
  CODEC_STORE_URL,
  initialMode,
  needsProxy,
  prefetchTarget,
  proxyProgressText,
  rememberProxyMode,
  rememberedMode,
  type PlaybackMode,
} from '../playback'

const POLL_MS = 700

interface Props {
  clipId: string
  nextClipId: string | null
  version: number
  videoRef: (el: HTMLVideoElement | null) => void
  onVolumeChange: (el: HTMLVideoElement) => void
}

export function ClipVideo({ clipId, nextClipId, version, videoRef, onVolumeChange }: Props) {
  const [mode, setMode] = useState<PlaybackMode>(() => initialMode(browserCanPlayHevc(), rememberedMode()))
  const [status, setStatus] = useState<ProxyStatus | null>(null)
  const [attempt, setAttempt] = useState(0)
  const errored = useRef(false)

  useEffect(() => {
    if (mode !== 'proxy') return
    let cancelled = false
    let timer: number | undefined
    setStatus({ state: 'running', progress: 0 })

    const poll = async () => {
      try {
        const next = await getProxyStatus(clipId)
        if (cancelled) return
        setStatus(next)
        if (next.state === 'running' || next.state === 'none') timer = window.setTimeout(poll, POLL_MS)
      } catch (e) {
        if (!cancelled) setStatus({ state: 'failed', progress: 0, message: (e as Error).message })
      }
    }

    startProxy(clipId)
      .then((first) => {
        if (cancelled) return
        setStatus(first)
        if (first.state !== 'ready') timer = window.setTimeout(poll, POLL_MS)
      })
      .catch((e: Error) => {
        if (!cancelled) setStatus({ state: 'failed', progress: 0, message: e.message })
      })

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [mode, clipId, attempt])

  const proxyReady = status?.state === 'ready'
  useEffect(() => {
    const target = prefetchTarget(nextClipId ? [clipId, nextClipId] : [clipId], 0, mode, proxyReady)
    if (target) prefetchProxy(target).catch(() => {})
  }, [mode, proxyReady, clipId, nextClipId])

  const fallBack = useCallback(() => {
    rememberProxyMode()
    setMode('proxy')
  }, [])

  const check = (el: HTMLVideoElement) => {
    if (mode === 'native' && needsProxy({ errored: errored.current, videoWidth: el.videoWidth })) fallBack()
  }

  if (mode === 'proxy' && status?.state !== 'ready') {
    return (
      <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded bg-black text-sm text-zinc-300">
        {status?.state === 'failed' ? (
          <>
            <p className="text-rose-300">재생용 영상을 만들지 못했습니다{status.message ? `: ${status.message}` : ''}</p>
            <button
              type="button"
              className="rounded border border-zinc-500 px-3 py-1 hover:bg-zinc-700"
              onClick={() => setAttempt((n) => n + 1)}
            >
              다시 시도
            </button>
          </>
        ) : (
          <>
            <p>{proxyProgressText(status?.progress ?? 0)}</p>
            <p className="text-xs text-zinc-500">이 PC 에서 원본(HEVC)을 바로 재생할 수 없어 H.264 사본을 만듭니다. 한 번만 만들어 둡니다.</p>
            <div className="mt-2 flex max-w-xl flex-col gap-1 px-4 text-left text-sm text-zinc-400">
              <p className="font-medium text-zinc-300">바로 재생하려면 (선택 사항)</p>
              <p className="text-xs text-zinc-500">Windows 에 HEVC 비디오 확장을 설치하면 이 대기 없이 재생됩니다. 자동으로 설치하지는 않습니다.</p>
              <ul className="flex list-disc flex-col gap-1 pl-5">
                <li>
                  <a className="text-sky-400 hover:underline" href={CODEC_STORE_URL} target="_blank" rel="noopener noreferrer">
                    스토어에서 구매
                  </a>{' '}
                  — 약 1,200원 (지역·시점에 따라 다름)
                </li>
                <li>
                  무료: 스토어에서 <span className="text-zinc-200">HEVC Video Extensions from Device Manufacturer</span> (제조사 제공 HEVC 비디오 확장)를
                  검색해 설치 — PC 제조사에 따라 없을 수 있음
                </li>
              </ul>
              <p className="text-xs text-zinc-500">설치한 뒤 재생이 되지 않으면 앱을 다시 열어 보세요.</p>
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <video
      key={`${clipId}-${version}-${mode}`}
      ref={videoRef}
      onVolumeChange={(e) => onVolumeChange(e.currentTarget)}
      onLoadedMetadata={(e) => check(e.currentTarget)}
      onError={(e) => {
        errored.current = true
        check(e.currentTarget)
      }}
      src={mode === 'proxy' ? proxyVideoUrl(clipId, version) : videoUrl(clipId, version)}
      controls
      autoPlay
      className="aspect-video w-full rounded bg-black object-contain"
    />
  )
}
