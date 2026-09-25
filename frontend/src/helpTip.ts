export type TooltipPlacement = 'below' | 'above'

interface Input {
  top: number
  bottom: number
  viewportHeight: number
  needed: number
}

export function tooltipPlacement(o: Input): TooltipPlacement {
  const below = o.viewportHeight - o.bottom
  const above = o.top
  if (below >= o.needed) return 'below'
  if (above >= o.needed) return 'above'
  return below >= above ? 'below' : 'above'
}
