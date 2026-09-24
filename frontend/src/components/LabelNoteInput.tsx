import { useEffect, useState } from 'react'
import { LABEL_NOTE_MAX, clampLabelNote } from '../consent'

export function LabelNoteInput({
  clipId,
  value,
  onSave,
}: {
  clipId: string
  value: string | null | undefined
  onSave: (note: string | null) => void
}) {
  const [draft, setDraft] = useState(value ?? '')

  useEffect(() => setDraft(value ?? ''), [clipId, value])

  const commit = () => {
    const next = draft.trim() === '' ? null : draft.trim()
    if (next !== (value ?? null)) onSave(next)
  }

  return (
    <div className="flex flex-col gap-1">
      <textarea
        className="w-full resize-none rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
        rows={2}
        placeholder="라벨 메모 (선택) — 왜 이렇게 판단했는지 적어 주세요"
        value={draft}
        maxLength={LABEL_NOTE_MAX}
        onChange={(e) => setDraft(clampLabelNote(e.target.value))}
        onBlur={commit}
      />
      <p className="text-xs text-zinc-500">
        {draft.length}/{LABEL_NOTE_MAX}자 · 이 메모는 라벨과 함께 전송됩니다. 닉네임 등 개인정보는 적지 마세요.
      </p>
    </div>
  )
}
