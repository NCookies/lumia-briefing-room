import { useState } from 'react'
import { useAppInfo, videoFormatHelpText } from '../appInfo'
import { GUIDE_FOLDER_TREE, GUIDE_TABS, type GuideBlock } from '../guide'
import { GuideText } from './GuideText'
import { ShortcutTable } from './ShortcutTable'

function VideoFormats() {
  const text = videoFormatHelpText(useAppInfo().videoFormats)
  if (!text) return null
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-base font-semibold text-zinc-100">지원하는 영상 형식</h3>
      <p className="whitespace-pre-line leading-7 text-zinc-200">{text}</p>
    </section>
  )
}

function Block({ block }: { block: GuideBlock }) {
  switch (block.kind) {
    case 'steps':
      return (
        <ol className="flex flex-col gap-2.5">
          {block.items.map((item, i) => (
            <li key={item} className="flex items-start gap-3 rounded-lg border border-zinc-700/60 bg-zinc-900/40 px-3 py-2.5">
              <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sky-600 text-sm font-semibold text-white">{i + 1}</span>
              <p className="leading-7 text-zinc-100">
                <GuideText text={item} />
              </p>
            </li>
          ))}
        </ol>
      )
    case 'notes':
      return (
        <section className="flex flex-col gap-1.5">
          <h3 className="text-base font-semibold text-zinc-100">{block.title}</h3>
          <ul className="flex flex-col gap-2 pl-1">
            {block.items.map((item) => (
              <li key={item} className="flex gap-2 leading-7 text-zinc-200">
                <span aria-hidden="true" className="text-zinc-500">•</span>
                <p>
                  <GuideText text={item} />
                </p>
              </li>
            ))}
          </ul>
        </section>
      )
    case 'paras':
      return (
        <section className="flex flex-col gap-1.5">
          {block.title && <h3 className="text-base font-semibold text-zinc-100">{block.title}</h3>}
          {block.lines.map((line) => (
            <p key={line} className="leading-7 text-zinc-200">
              <GuideText text={line} />
            </p>
          ))}
        </section>
      )
    case 'callout':
      return (
        <section className="flex flex-col gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3.5 py-3">
          <h3 className="text-base font-semibold text-amber-200">{block.title}</h3>
          {block.lines.map((line) => (
            <p key={line} className="leading-7 text-zinc-200">
              <GuideText text={line} />
            </p>
          ))}
        </section>
      )
    case 'tree':
      return (
        <pre className="overflow-x-auto rounded-lg border border-zinc-700/60 bg-zinc-900 p-3 font-mono text-xs leading-relaxed text-zinc-300">{GUIDE_FOLDER_TREE}</pre>
      )
    case 'shortcuts':
      return <ShortcutTable />
    case 'videoFormats':
      return <VideoFormats />
  }
}

/** 시작하기·풀영상 화면·클립·폴더·단축키를 탭으로 나눈 안내. 첫 실행 화면과 `?` 모달이 같이 쓴다. 그림은 코드로 그린다. */
export function GuideContent() {
  const [tabId, setTabId] = useState(GUIDE_TABS[0].id)
  const tab = GUIDE_TABS.find((t) => t.id === tabId) ?? GUIDE_TABS[0]
  return (
    <div className="flex flex-col gap-4 text-[15px] text-zinc-200">
      <div role="tablist" aria-label="안내 구역" className="flex flex-wrap gap-1 rounded-full border border-zinc-700/60 bg-zinc-900/60 p-1">
        {GUIDE_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={t.id === tab.id}
            className={`rounded-full px-3.5 py-1 text-sm transition ${t.id === tab.id ? 'bg-zinc-700 font-medium text-white' : 'text-zinc-400 hover:text-zinc-100'}`}
            onClick={() => setTabId(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="flex flex-col gap-5">
        {tab.blocks.map((block, i) => (
          <Block key={i} block={block} />
        ))}
      </div>
    </div>
  )
}
