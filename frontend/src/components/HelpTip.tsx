import { useState } from 'react'

interface Props {
  text: string
  label: string
  centered?: boolean
  wide?: boolean
}

export function HelpTip({ text, label, centered = false, wide = false }: Props) {
  const [open, setOpen] = useState(false)
  if (!text) return null

  return (
    <span className="relative inline-block">
      <button
        type="button"
        className="rounded-full border border-zinc-600 px-1.5 text-xs leading-4 text-zinc-400 hover:border-sky-500 hover:text-sky-300"
        aria-label={label}
        aria-expanded={open}
        title={text}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        onBlur={() => setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className={`absolute top-full z-20 mt-1 whitespace-pre-line rounded border border-zinc-600 bg-zinc-800 p-2 text-left text-xs leading-relaxed text-zinc-200 shadow-lg ${
            wide ? 'w-96' : 'w-72'
          } ${centered ? 'left-1/2 -translate-x-1/2' : 'left-0'}`}
        >
          {text}
        </span>
      )}
    </span>
  )
}
