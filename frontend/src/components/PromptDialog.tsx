import { useEffect, useRef, useState } from 'react'

interface Props {
  title: string
  initial?: string
  confirmLabel: string
  hint?: string
  onSubmit: (value: string) => Promise<void> | void
  onCancel: () => void
}

/** 이름 하나를 입력받는 작은 창(새 폴더·이름 바꾸기). 실패하면 창을 닫지 않고 이유를 보여 준다. */
export function PromptDialog({ title, initial = '', confirmLabel, hint, onSubmit, onCancel }: Props) {
  const [value, setValue] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    input.current?.focus()
    input.current?.select()
  }, [])

  const submit = async () => {
    if (value.trim() === '' || busy) return
    setBusy(true)
    setError(null)
    try {
      await onSubmit(value.trim())
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4" role="presentation">
      <div role="dialog" aria-modal="true" className="flex w-full max-w-sm flex-col gap-3 rounded-lg border border-zinc-600 bg-zinc-800 p-5">
        <h3 className="text-sm font-medium text-zinc-100">{title}</h3>
        <input
          ref={input}
          className="rounded border border-zinc-600 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            e.stopPropagation()
            if (e.key === 'Enter') void submit()
            if (e.key === 'Escape') onCancel()
          }}
        />
        {hint && <p className="text-xs text-zinc-500">{hint}</p>}
        {error && <p className="text-xs text-rose-300">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={onCancel}>
            취소
          </button>
          <button
            type="button"
            className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40"
            disabled={value.trim() === '' || busy}
            onClick={() => void submit()}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
