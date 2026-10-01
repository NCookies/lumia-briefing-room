import { useRef, useState } from 'react'
import { tooltipPlacement, type TooltipPlacement } from '../helpTip'

interface Props {
  text: string
  label: string
  centered?: boolean
  wide?: boolean
  /** 눌러서 여닫는 대신 마우스를 올리거나 포커스하면 연다. */
  hover?: boolean
  /** 말풍선을 버튼 오른쪽 끝에 맞춘다(화면 오른쪽 가장자리용). */
  alignRight?: boolean
}

const NEEDED_PX = 300

export function HelpTip({ text, label, centered = false, wide = false, hover = false, alignRight = false }: Props) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<TooltipPlacement>('below')
  const button = useRef<HTMLButtonElement | null>(null)
  if (!text) return null

  const show = (next: boolean) => {
    if (next && button.current) {
      const rect = button.current.getBoundingClientRect()
      setPlacement(tooltipPlacement({ top: rect.top, bottom: rect.bottom, viewportHeight: window.innerHeight, needed: NEEDED_PX }))
    }
    setOpen(next)
  }
  const toggle = () => show(!open)

  return (
    <span className="relative inline-block" onMouseEnter={hover ? () => show(true) : undefined} onMouseLeave={hover ? () => setOpen(false) : undefined}>
      <button
        ref={button}
        type="button"
        className="rounded-full border border-zinc-600/70 px-1.5 text-xs leading-4 text-zinc-400 hover:border-sky-500 hover:text-sky-300"
        aria-label={label}
        aria-expanded={open}
        title={hover ? undefined : text}
        onClick={(e) => {
          e.stopPropagation()
          toggle()
        }}
        onFocus={hover ? () => show(true) : undefined}
        onBlur={() => setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className={`absolute z-20 max-h-[60vh] overflow-y-auto whitespace-pre-line rounded-lg border border-zinc-600/70 bg-zinc-800 p-2 text-left text-xs leading-relaxed text-zinc-200 shadow-lg ${
            placement === 'below' ? 'top-full mt-1' : 'bottom-full mb-1'
          } ${wide ? 'w-96' : 'w-72'} ${centered ? 'left-1/2 -translate-x-1/2' : alignRight ? 'right-0' : 'left-0'}`}
        >
          {text}
        </span>
      )}
    </span>
  )
}
