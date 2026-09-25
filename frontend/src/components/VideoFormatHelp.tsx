import { useState } from 'react'
import { useAppInfo, videoFormatHelpText } from '../appInfo'

export function VideoFormatHelp() {
  const text = videoFormatHelpText(useAppInfo().videoFormats)
  const [open, setOpen] = useState(false)
  if (!text) return null

  return (
    <span className="relative inline-block">
      <button
        type="button"
        className="rounded-full border border-zinc-600 px-1.5 text-xs leading-4 text-zinc-400 hover:border-sky-500 hover:text-sky-300"
        aria-label="지원하는 영상 형식"
        aria-expanded={open}
        title={text}
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-full z-20 mt-1 w-72 whitespace-pre-line rounded border border-zinc-600 bg-zinc-800 p-2 text-left text-xs text-zinc-200 shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  )
}
