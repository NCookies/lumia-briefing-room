import { createContext, useContext } from 'react'
import type { InstallStatus, ReleaseInfo } from './update'

export interface UpdateState {
  release: ReleaseInfo | null
  install: InstallStatus
  start: () => void
  refresh: () => void
  openNotes: (release: ReleaseInfo) => void
}

export const IDLE_INSTALL: InstallStatus = { state: 'idle', downloaded: 0, total: 0, error: '' }

export const UpdateContext = createContext<UpdateState>({
  release: null,
  install: IDLE_INSTALL,
  start: () => {},
  refresh: () => {},
  openNotes: () => {},
})

export const useUpdate = (): UpdateState => useContext(UpdateContext)
