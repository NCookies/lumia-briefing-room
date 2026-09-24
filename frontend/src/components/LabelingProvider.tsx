import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getConsentChoices } from '../consentApi'
import { LabelingContext } from '../labelingContext'

export function LabelingProvider({ children }: { children: ReactNode }) {
  const [sendLabels, setSendLabels] = useState(false)

  const reload = useCallback(() => {
    getConsentChoices()
      .then((c) => setSendLabels(c.labels))
      .catch(() => {})
  }, [])

  useEffect(reload, [reload])

  const value = useMemo(() => ({ sendLabels, reload }), [sendLabels, reload])
  return <LabelingContext.Provider value={value}>{children}</LabelingContext.Provider>
}
