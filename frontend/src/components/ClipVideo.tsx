import { useCallback, useEffect, useRef, useState } from 'react'
import { getProxyStatus, proxyVideoUrl, startProxy, videoUrl, type ProxyStatus } from '../api'
import {
  browserCanPlayHevc,
  initialMode,
  needsProxy,
  proxyProgressText,
  rememberProxyMode,
  rememberedMode,
  type PlaybackMode,
} from '../playback'

const POLL_MS = 700

interface Props {
  clipId: string
  version: number
  videoRef: (el: HTMLVideoElement | null) => void
  onVolumeChange: (el: HTMLVideoElement) => void
}

export function ClipVideo({ clipId, version, videoRef, onVolumeChange }: Props) {
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
