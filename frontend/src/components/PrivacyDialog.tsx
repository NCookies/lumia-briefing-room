import { useEffect, useState } from 'react'
import { getPrivacyText } from '../telemetryApi'
import { parseInlineBold, parsePrivacy, type PrivacyBlock } from '../telemetry'

function Inline({ text }: { text: string }) {
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

function Block({ block }: { block: PrivacyBlock }) {
  switch (block.type) {
    case 'h1':
      return <h2 className="text-lg font-medium text-zinc-100">{block.text}</h2>
    case 'h2':
      return <h3 className="mt-2 text-sm font-medium text-zinc-100">{block.text}</h3>
    case 'note':
      return (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
          <Inline text={block.text} />
        </p>
      )
    case 'list':
      return (
        <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-300">
          {block.items.map((item, i) => (
            <li key={i}>
              <Inline text={item} />
            </li>
          ))}
        </ul>
      )
    case 'table':
      return (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs text-zinc-300">
            <thead>
              <tr>
                {block.header.map((cell, i) => (
                  <th key={i} className="border border-zinc-700 bg-zinc-900 px-2 py-1 font-medium">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c} className="border border-zinc-700 px-2 py-1 align-top">
                      <Inline text={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    default:
      return (
        <p className="text-sm text-zinc-300">
          <Inline text={block.text} />
        </p>
      )
  }
}

export function PrivacyDialog({ onClose }: { onClose: () => void }) {
  const [blocks, setBlocks] = useState<PrivacyBlock[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getPrivacyText()
      .then((text) => setBlocks(parsePrivacy(text)))
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="flex h-[min(40rem,90vh)] w-full max-w-2xl flex-col rounded-lg border border-zinc-600 bg-zinc-800 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
          <h2 className="text-base font-medium">개인정보 처리 안내</h2>
          <button type="button" className="text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            닫기 ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          {error && <p className="text-sm text-rose-300">{error}</p>}
          {!blocks && !error && <p className="text-sm text-zinc-400">불러오는 중…</p>}
          {blocks?.map((block, i) => <Block key={i} block={block} />)}
        </div>
      </div>
    </div>
  )
}
