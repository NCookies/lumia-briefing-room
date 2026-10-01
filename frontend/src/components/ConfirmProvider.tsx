import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { ConfirmContext, type Ask, type ConfirmOptions, type ConfirmResult } from '../confirmContext'
import { confirmKeyAction, type ConfirmFocus } from '../confirmKeys'

interface Pending {
  options: ConfirmOptions
  resolve: (result: ConfirmResult) => void
}

function ConfirmDialog({ pending, onDone }: { pending: Pending; onDone: (result: ConfirmResult) => void }) {
  const { options } = pending
  const [skip, setSkip] = useState(false)
  const cancelButton = useRef<HTMLButtonElement>(null)
  const confirmButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const at = document.activeElement
      const focus: ConfirmFocus = at === cancelButton.current ? 'cancel' : at === confirmButton.current ? 'confirm' : 'other'
      const result = confirmKeyAction(e.key, focus, e.repeat)
      if (result.kind === 'pass') return
      e.stopImmediatePropagation()
      if (result.kind === 'native') return
      e.preventDefault()
      if (result.kind === 'cancel') onDone({ ok: false, skipNext: false })
      else if (result.kind === 'confirm') onDone({ ok: true, skipNext: skip })
      else if (result.kind === 'focus') (result.to === 'cancel' ? cancelButton : confirmButton).current?.focus()
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
        className="flex w-full max-w-md flex-col gap-4 rounded-xl border border-zinc-600/70 bg-zinc-800 shadow-xl p-5 text-zinc-100"
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
            ref={cancelButton}
            type="button"
            className="rounded-md px-4 py-1.5 text-sm text-zinc-300 transition hover:bg-zinc-700"
            onClick={() => onDone({ ok: false, skipNext: false })}
          >
            {options.cancelLabel ?? '취소'}
          </button>
          <button
            ref={confirmButton}
            type="button"
            autoFocus
            className={`rounded-md px-4 py-1.5 text-sm ${
              options.danger ? 'bg-rose-600 transition hover:bg-rose-500' : 'bg-sky-600 hover:bg-sky-500'
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
