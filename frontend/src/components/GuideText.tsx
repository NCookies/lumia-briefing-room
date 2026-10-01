import { GUIDE_CHIPS, parseGuideText, type ChipKind } from '../guide'
import { BookmarkFilledIcon, BookmarkIcon } from './ViewerIcons'

/** 칩 색은 실제 버튼(`ViewerCandidates`·`GameRow`)과 같은 계열이다. */
const CHIP_CLASS: Record<ChipKind, string> = {
  primary: 'bg-sky-600 text-white',
  archived: 'bg-emerald-600/30 text-emerald-200',
  secondary: 'border border-zinc-600/70 bg-zinc-800/60 text-zinc-200',
  danger: 'border border-rose-500/50 bg-rose-500/5 text-rose-300',
  pin: 'border border-zinc-600/70 text-zinc-200',
  category: 'border border-zinc-700/60 bg-zinc-900 text-zinc-300',
}

function GuideChip({ name }: { name: string }) {
  const kind = GUIDE_CHIPS[name]
  return (
    <span className={`mx-0.5 inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-[13px] font-medium leading-5 ${CHIP_CLASS[kind]}`}>
      {name === '보관' && <BookmarkIcon />}
      {name === '보관됨' && <BookmarkFilledIcon />}
      {name}
    </span>
  )
}

/** 가이드 문장. `용어` 는 실제 버튼 모양 칩으로, {키} 는 `<kbd>` 로 그린다. */
export function GuideText({ text }: { text: string }) {
  return (
    <>
      {parseGuideText(text).map((seg, i) => {
        if (seg.type === 'chip') return <GuideChip key={i} name={seg.value} />
        if (seg.type === 'kbd')
          return (
            <kbd key={i} className="mx-0.5 rounded-md border border-zinc-600/70 bg-zinc-900 px-1.5 py-0.5 font-mono text-[12px] text-zinc-100">
              {seg.value}
            </kbd>
          )
        return <span key={i}>{seg.value}</span>
      })}
    </>
  )
}
