import { SHORTCUT_GROUPS } from '../viewerShortcuts'

/** 풀영상 화면 단축키 안내 표. 화면의 `⌨` 패널과 사용 안내 가이드가 같이 쓴다. */
export function ShortcutTable() {
  return (
    <div className="flex flex-col gap-2 text-xs text-zinc-200">
      {SHORTCUT_GROUPS.map((group) => (
        <section key={group.title}>
          <h4 className="mb-0.5 font-medium text-zinc-400">{group.title}</h4>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5">
            {group.rows.map((row) => (
              <div key={row.keys} className="contents">
                <dt>
                  <kbd className="rounded border border-zinc-600 bg-zinc-900 px-1.5 py-0.5 font-mono text-[11px] text-zinc-100">{row.keys}</kbd>
                </dt>
                <dd className="text-zinc-300">{row.desc}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  )
}
