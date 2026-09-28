import { useState } from 'react'
import { deleteConfirmMessage, needsPermanentSkipWarning, resolveDeleteChoice, type DeleteMode } from '../deleteConfirm'

interface Props {
  label: string
  deleteMode: DeleteMode
  onCancel: () => void
  onConfirm: (result: { mode: DeleteMode; skipNext: boolean }) => void
}

export function DeleteConfirmDialog({ label, deleteMode, onCancel, onConfirm }: Props) {
  const [skipNext, setSkipNext] = useState(false)
  const [permanent, setPermanent] = useState(deleteMode === 'permanent')
  const [confirmingPermanentSkip, setConfirmingPermanentSkip] = useState(false)

  const proceed = () => {
    const choice = { skipNext, permanent }
    if (needsPermanentSkipWarning(choice)) {
      setConfirmingPermanentSkip(true)
      return
    }
    onConfirm(resolveDeleteChoice(choice))
  }

  if (confirmingPermanentSkip) {
    return (
      <div className="fixed inset-0 z-[101] flex items-center justify-center bg-black/70 p-4">
        <div
          role="dialog"
          aria-modal="true"
          className="flex w-full max-w-md flex-col gap-4 rounded-lg border border-rose-500/60 bg-zinc-800 p-5 text-zinc-100"
        >
          <p className="text-sm leading-relaxed">
            영구 삭제 + 다시 묻지 않기를 함께 선택하면, 앞으로 삭제할 때 확인도 복구도 없이 즉시 완전히
            지워집니다. 계속하시겠습니까?
          </p>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="rounded px-4 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700"
              onClick={() => setConfirmingPermanentSkip(false)}
            >
              취소
            </button>
            <button
              type="button"
              autoFocus
              className="rounded bg-rose-600 px-4 py-1.5 text-sm hover:bg-rose-500"
              onClick={() => onConfirm(resolveDeleteChoice({ skipNext, permanent }))}
            >
              계속
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4" onClick={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex w-full max-w-md flex-col gap-4 rounded-lg border border-zinc-600 bg-zinc-800 p-5 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-medium">정말 삭제하시겠습니까?</h2>
        <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-300">
          {label}
          {'\n'}
          {deleteConfirmMessage(permanent ? 'permanent' : 'recycle')}
        </p>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input type="checkbox" checked={skipNext} onChange={(e) => setSkipNext(e.target.checked)} />
          다시 묻지 않기
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input type="checkbox" checked={permanent} onChange={(e) => setPermanent(e.target.checked)} />
          휴지통으로 보내지 않고 영구 삭제하기
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className="rounded px-4 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700" onClick={onCancel}>
            취소
          </button>
          <button
            type="button"
            autoFocus
            className="rounded bg-rose-600 px-4 py-1.5 text-sm hover:bg-rose-500"
            onClick={proceed}
          >
            삭제
          </button>
        </div>
      </div>
    </div>
  )
}
