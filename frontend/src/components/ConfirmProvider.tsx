import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ConfirmContext, type Ask, type ConfirmOptions, type ConfirmResult } from '../confirmContext'

interface Pending {
  options: ConfirmOptions
  resolve: (result: ConfirmResult) => void
}

function ConfirmDialog({ pending, onDone }: { pending: Pending; onDone: (result: ConfirmResult) => void }) {
  const { options } = pending
  const [skip, setSkip] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Tab') return
      e.stopImmediatePropagation()
      if (e.key === 'Escape') onDone({ ok: false, skipNext: false })
      if (e.key === 'Enter') onDone({ ok: true, skipNext: skip })
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onDone, skip])

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => {
        e.stopPropagation()
        onDone({ ok: false, skipNext: false })
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="flex w-full max-w-md flex-col gap-4 rounded-lg border border-zinc-600 bg-zinc-800 p-5 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="whitespace-pre-line text-sm leading-relaxed">{options.message}</p>
        {options.allowSkip && (
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} />
            다시 확인하지 않기
          </label>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded px-4 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700"
            onClick={() => onDone({ ok: false, skipNext: false })}
          >
            취소
          </button>
          <button
            type="button"
            autoFocus
            className={`rounded px-4 py-1.5 text-sm ${
              options.danger ? 'bg-rose-600 hover:bg-rose-500' : 'bg-sky-600 hover:bg-sky-500'
            }`}
            onClick={() => onDone({ ok: true, skipNext: skip })}
          >
            {options.confirmLabel ?? '확인'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null)

  const ask: Ask = useCallback(
    (options) => new Promise<ConfirmResult>((resolve) => setPending({ options, resolve })),
    [],
  )

  const done = useCallback(
    (result: ConfirmResult) => {
      pending?.resolve(result)
      setPending(null)
    },
    [pending],
  )

  return (
    <ConfirmContext.Provider value={ask}>
      {children}
      {pending && <ConfirmDialog pending={pending} onDone={done} />}
    </ConfirmContext.Provider>
  )
}
