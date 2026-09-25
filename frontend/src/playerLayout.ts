const BASE_REM = 8.5
const LABELING_REM = 7.5
const TRIMMING_REM = 8

export function playerWidthCss(o: { labeling: boolean; trimming: boolean }): string {
  const reserve = BASE_REM + (o.labeling ? LABELING_REM : 0) + (o.trimming ? TRIMMING_REM : 0)
  return `min(97vw, calc((100vh - ${reserve}rem) * 1.7778))`
}

export const shouldAutoAdvance = (o: { tuning: boolean }): boolean => o.tuning

export const showEvidence = (o: { tuning: boolean; labeling: boolean }): boolean => o.tuning || o.labeling
