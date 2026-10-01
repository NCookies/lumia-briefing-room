import { useEffect, useRef, useState } from 'react'

export interface GameMenuItem {
  label: string
  disabled?: boolean
  danger?: boolean
  title?: string
  onSelect: () => void
}

const MENU_WIDTH = 240

/** 게임 행 오른쪽 `⋯` 메뉴. 행이 `overflow-hidden` 이라 메뉴는 화면 기준(`fixed`)으로 띄운다. */
export function GameMenu({ items }: { items: GameMenuItem[] }) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const button = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!pos) return
    const close = () => setPos(null)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [pos])

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (pos) return setPos(null)
    const rect = button.current!.getBoundingClientRect()
    const height = items.length * 36 + 8
    const top = rect.bottom + height > window.innerHeight ? rect.top - height : rect.bottom + 4
    setPos({ top, left: Math.max(8, Math.min(rect.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - 8)) })
  }

  return (
    <>
      <button
        ref={button}
        type="button"
        aria-label="게임 메뉴"
        aria-haspopup="menu"
        aria-expanded={pos !== null}
        className="inline-flex h-7 w-8 items-center justify-center rounded-md border border-zinc-600/70 bg-zinc-800/60 text-xs leading-none text-zinc-200 transition hover:bg-zinc-700 hover:text-white active:scale-95"
        onClick={toggle}
      >
        ⋯
      </button>
      {pos && (
        <div className="fixed inset-0 z-[90]" onClick={(e) => { e.stopPropagation(); setPos(null) }}>
          <ul
            role="menu"
            className="absolute flex flex-col overflow-hidden rounded border border-zinc-600 bg-zinc-800 py-1 shadow-lg"
            style={{ top: pos.top, left: pos.left, width: MENU_WIDTH }}
          >
            {items.map((item) => (
              <li key={item.label} role="none">
                <button
                  type="button"
                  role="menuitem"
                  disabled={item.disabled}
                  title={item.title}
                  className={`block w-full whitespace-nowrap px-3 py-2 text-left text-sm hover:bg-zinc-700 disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent ${
                    item.danger ? 'text-rose-300' : 'text-zinc-200'
                  }`}
                  onClick={(e) => {
                    e.stopPropagation()
                    setPos(null)
                    item.onSelect()
                  }}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}
