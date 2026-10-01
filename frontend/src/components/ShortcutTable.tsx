import { SHORTCUT_GROUPS } from '../viewerShortcuts'

/** 풀영상 화면 단축키 안내 표. 화면의 `⌨ 단축키` 패널과 사용 안내 가이드가 같이 쓴다. */
export function ShortcutTable() {
  return (
    <div className="flex flex-col gap-2 text-xs text-zinc-200">
      {SHORTCUT_GROUPS.map((group) => (
        <section key={group.title}>
          <h4 className="mb-0.5 font-medium text-zinc-400">{group.title}</h4>
          <ul className="flex flex-col gap-0.5">
            {group.rows.map((row) => (
              <li key={row.keys}>
                <kbd className="rounded-md border border-zinc-600/70 bg-zinc-900 px-1.5 py-0.5 font-mono text-[11px] text-zinc-100">{row.keys}</kbd>
                <span className="text-zinc-300"> : {row.desc}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
