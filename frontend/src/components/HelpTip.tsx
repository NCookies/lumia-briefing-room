import { useRef, useState } from 'react'
import { tooltipPlacement, type TooltipPlacement } from '../helpTip'

interface Props {
  text: string
  label: string
  centered?: boolean
  wide?: boolean
}

const NEEDED_PX = 300

export function HelpTip({ text, label, centered = false, wide = false }: Props) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<TooltipPlacement>('below')
  const button = useRef<HTMLButtonElement | null>(null)
  if (!text) return null

  const toggle = () => {
    if (!open && button.current) {
      const rect = button.current.getBoundingClientRect()
      setPlacement(tooltipPlacement({ top: rect.top, bottom: rect.bottom, viewportHeight: window.innerHeight, needed: NEEDED_PX }))
    }
    setOpen((v) => !v)
  }

  return (
    <span className="relative inline-block">
      <button
        ref={button}
        type="button"
        className="rounded-full border border-zinc-600 px-1.5 text-xs leading-4 text-zinc-400 hover:border-sky-500 hover:text-sky-300"
        aria-label={label}
        aria-expanded={open}
        title={text}
        onClick={(e) => {
          e.stopPropagation()
          toggle()
        }}
        onBlur={() => setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className={`absolute z-20 max-h-[60vh] overflow-y-auto whitespace-pre-line rounded border border-zinc-600 bg-zinc-800 p-2 text-left text-xs leading-relaxed text-zinc-200 shadow-lg ${
            placement === 'below' ? 'top-full mt-1' : 'bottom-full mb-1'
          } ${wide ? 'w-96' : 'w-72'} ${centered ? 'left-1/2 -translate-x-1/2' : 'left-0'}`}
        >
          {text}
        </span>
      )}
    </span>
  )
}
