import { useEffect, useState } from 'react'
import { clampMemo, CLIP_MEMO_MAX, memoToSave } from '../clipMemo'

interface Props {
  clipId: string
  value: string | null | undefined
  onSave: (memo: string | null) => void
  rows?: number
  compact?: boolean
}

/** 클립 메모: 좋았던 점·아쉬웠던 점을 적는 나만의 메모. 서버로 보내지 않는다(라벨 메모와 별개). 포커스를 잃으면 저장한다. */
export function ClipMemoInput({ clipId, value, onSave, rows = 3, compact = false }: Props) {
  const [draft, setDraft] = useState(value ?? '')

  useEffect(() => setDraft(value ?? ''), [clipId, value])

  const commit = () => {
    const next = memoToSave(draft, value)
    if (next !== undefined) onSave(next)
  }

  return (
    <div className="flex flex-col gap-1">
      <textarea
        aria-label="클립 메모"
        className="w-full resize-y rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
        rows={rows}
        maxLength={CLIP_MEMO_MAX}
        placeholder="원하시는 내용을 작성해 주세요"
        value={draft}
        onChange={(e) => setDraft(clampMemo(e.target.value))}
        onBlur={commit}
      />
      {!compact && <p className="text-xs text-zinc-500">나만 보는 메모입니다. 서버로 보내지 않습니다.</p>}
    </div>
  )
}
