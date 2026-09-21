import { createContext, useContext } from 'react'

export interface ConfirmOptions {
  message: string
  confirmLabel?: string
  danger?: boolean
  allowSkip?: boolean
}

export interface ConfirmResult {
  ok: boolean
  skipNext: boolean
}

export type Ask = (options: ConfirmOptions) => Promise<ConfirmResult>

export const ConfirmContext = createContext<Ask>(async () => ({ ok: false, skipNext: false }))

export const useConfirm = (): Ask => useContext(ConfirmContext)
