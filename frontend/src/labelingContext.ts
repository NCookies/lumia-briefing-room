import { createContext, useContext } from 'react'
import { useAppInfo } from './appInfo'
import { showLabelingUi } from './consent'

export interface LabelingState {
  sendLabels: boolean
  reload: () => void
}

export const LabelingContext = createContext<LabelingState>({ sendLabels: false, reload: () => {} })

export const useLabelingState = (): LabelingState => useContext(LabelingContext)

export function useLabelingUi(): boolean {
  const { mode } = useAppInfo()
  return showLabelingUi(mode, useLabelingState().sendLabels)
}
