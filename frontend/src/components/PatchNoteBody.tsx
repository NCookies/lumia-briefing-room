import type { PatchNoteSection } from '../patchNotes'
import { parseInlineBold } from '../telemetry'

export function Inline({ text }: { text: string }) {
  return (
    <>
      {parseInlineBold(text).map((part, i) =>
        part.bold ? (
          <strong key={i} className="font-semibold text-zinc-100">
            {part.text}
          </strong>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  )
}

export function PatchNoteSections({ sections }: { sections: PatchNoteSection[] }) {
  return (
    <>
      {sections.map((section, i) => (
        <div key={i} className="flex flex-col gap-1">
          {section.title && <h4 className="text-xs font-medium text-zinc-400">{section.title}</h4>}
          <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-zinc-300">
            {section.items.map((item, j) => (
              <li key={j}>
                <Inline text={item} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  )
}
