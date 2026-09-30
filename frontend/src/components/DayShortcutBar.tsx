import type { DayShortcut } from '../dayFold'

/** 날짜 바로가기: 거르지 않고 그 날짜 머리줄로 이동한다(접혀 있으면 펼친다). 날짜가 많으면 가로로 스크롤. */
export function DayShortcutBar({ shortcuts, onGo }: { shortcuts: DayShortcut[]; onGo: (shortcut: DayShortcut) => void }) {
  if (shortcuts.length === 0) return null
  return (
    <div className="flex items-center gap-2" role="group" aria-label="날짜 바로가기">
      <span className="shrink-0 text-xs text-zinc-500">날짜로 이동</span>
      <div className="flex min-w-0 gap-1 overflow-x-auto pb-1">
        {shortcuts.map((s) => (
          <button
            key={s.anchor}
            type="button"
            className="shrink-0 rounded border border-zinc-600 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-400 hover:bg-zinc-700"
            onClick={() => onGo(s)}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )
}
