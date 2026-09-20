import { videoUrl } from '../api'
import type { Clip } from '../types'

export function PlayerModal({ clip, onClose }: { clip: Clip; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-full max-w-4xl flex-col gap-2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between text-zinc-100">
          <h2 className="text-lg font-medium">{clip.title}</h2>
          <button
            type="button"
            className="rounded px-2 py-1 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100"
            onClick={onClose}
          >
            닫기 ✕
          </button>
        </div>
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video
          src={videoUrl(clip.id)}
          controls
          autoPlay
          className="max-h-[80vh] w-full rounded bg-black"
        />
      </div>
    </div>
  )
}
