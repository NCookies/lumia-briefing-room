import { useEffect, useRef, useState } from 'react'
import { clampMemo, CLIP_MEMO_MAX, memoToSave } from '../clipMemo'

interface Props {
  clipId: string
  value: string | null | undefined
  onSave: (memo: string | null) => void
  rows?: number
  compact?: boolean
  autoFocus?: boolean
  /** 주면 Ctrl+Enter 로 저장하고 이 함수를 불러 닫는다. */
  onClose?: () => void
}

/** 클립 메모: 좋았던 점·아쉬웠던 점을 적는 나만의 메모. 서버로 보내지 않는다(라벨 메모와 별개). 포커스를 잃으면 저장한다. */
export function ClipMemoInput({ clipId, value, onSave, rows = 3, compact = false, autoFocus = false, onClose }: Props) {
  const [draft, setDraft] = useState(value ?? '')
  const area = useRef<HTMLTextAreaElement>(null)

  useEffect(() => setDraft(value ?? ''), [clipId, value])

  const commit = () => {
    const next = memoToSave(draft, value)
    if (next !== undefined) onSave(next)
  }

  const saveAndClose = () => {
    area.current?.blur()
    onClose?.()
  }

  return (
    <div className="flex flex-col gap-1">
      <textarea
        ref={area}
        aria-label="클립 메모"
        className="w-full resize-y rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
        rows={rows}
        maxLength={CLIP_MEMO_MAX}
        placeholder="원하시는 내용을 작성해 주세요"
        value={draft}
        onChange={(e) => setDraft(clampMemo(e.target.value))}
        autoFocus={autoFocus}
        onBlur={commit}
        onKeyDown={(e) => {
          if (onClose && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault()
            saveAndClose()
          }
        }}
      />
      {onClose && (
        <div className="flex justify-end">
          <button
            type="button"
            className="rounded bg-sky-600 px-2 py-0.5 text-xs text-zinc-100 hover:bg-sky-500"
            title="메모를 저장하고 닫습니다 (Ctrl+Enter)"
            onMouseDown={(e) => e.preventDefault()}
            onClick={saveAndClose}
          >
            저장
          </button>
        </div>
      )}
      {!compact && <p className="text-xs text-zinc-500">나만 보는 메모입니다. 서버로 보내지 않습니다.</p>}
    </div>
  )
}
