import { useEffect, useState } from 'react'
import { LABEL_NOTE_MAX, clampLabelNote } from '../consent'

export function LabelNoteInput({
  clipId,
  value,
  disabled = false,
  onSave,
}: {
  clipId: string
  value: string | null | undefined
  disabled?: boolean
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
        className="w-full resize-none rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        rows={2}
        disabled={disabled}
        placeholder={
          disabled
            ? '라벨(교전 / 그 외)을 먼저 고르면 메모를 남길 수 있습니다'
            : '어떤 장면인지 자세히 적어 주시면 성능 개선에 큰 도움이 됩니다 (선택) — 예: 교전이 아니라 사냥하며 이동하는 장면'
        }
        value={draft}
        maxLength={LABEL_NOTE_MAX}
        onChange={(e) => setDraft(clampLabelNote(e.target.value))}
        onBlur={commit}
      />
      <p className="text-xs text-zinc-500">
        {draft.length}/{LABEL_NOTE_MAX}자 · 이 메모는 라벨과 함께 개발자에게 전송됩니다. 닉네임 같은 개인정보는 빼고 적어 주세요.
      </p>
    </div>
  )
}
