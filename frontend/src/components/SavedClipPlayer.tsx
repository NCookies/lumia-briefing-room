import { useRef } from 'react'
import { loadVolume, saveVolume } from '../volume'
import { ClipVideo } from './ClipVideo'

interface Props {
  notice: string
  clipId: string | null
  title: string | null
}

/** 풀영상이 없는 게임(자동 정리·삭제)에서도 이미 만든 클립은 그대로 볼 수 있게 한다 - 클립은 풀영상과 별개 파일이다. */
export function SavedClipPlayer({ notice, clipId, title }: Props) {
  const volume = useRef(loadVolume())

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-2" data-testid="saved-clip-player">
      <p className="rounded-lg border border-amber-500/60 bg-amber-500/10 p-3 text-sm text-amber-200">{notice}</p>
      {clipId ? (
        <div className="flex min-h-0 flex-1 flex-col gap-1">
          <div className="min-h-0 flex-1 [&_video]:max-h-full">
            <ClipVideo
              key={clipId}
              clipId={clipId}
              nextClipId={null}
              version={0}
              videoRef={(el) => {
                if (!el) return
                el.volume = volume.current.volume
                el.muted = volume.current.muted
              }}
              onVolumeChange={(v) => {
                volume.current = { volume: v.volume, muted: v.muted }
                saveVolume(volume.current)
              }}
            />
          </div>
          {title && <span className="text-sm text-zinc-300">{title}</span>}
        </div>
      ) : (
        <p className="text-sm text-zinc-500">이 게임에는 재생할 클립이 없습니다. 오른쪽 목록에서 클립이 있는 후보를 누르면 그 클립을 볼 수 있습니다.</p>
      )}
    </div>
  )
}
