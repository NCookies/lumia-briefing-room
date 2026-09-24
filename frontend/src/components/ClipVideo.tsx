import { useCallback, useEffect, useRef, useState } from 'react'
import { getProxyStatus, prefetchProxy, proxyVideoUrl, startProxy, videoUrl, type ProxyStatus } from '../api'
import {
  browserCanPlayHevc,
  CODEC_FREE_STORE_URL,
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
            <p className="max-w-lg px-4 text-center text-xs text-zinc-500">
              Windows 에 HEVC 비디오 확장을 설치하면 이 대기 없이 바로 재생됩니다(선택 사항, 자동으로 설치하지 않습니다).{' '}
              <a className="text-sky-400 hover:underline" href={CODEC_STORE_URL} target="_blank" rel="noopener noreferrer">
                스토어 (유료)
              </a>
              {' · '}
              <a className="text-sky-400 hover:underline" href={CODEC_FREE_STORE_URL} target="_blank" rel="noopener noreferrer">
                제조사 제공 (무료)
              </a>
              {' '}— 무료판은 PC 제조사에 따라 없을 수 있습니다. 설치 후에는 앱을 다시 열어 주세요.
            </p>
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
