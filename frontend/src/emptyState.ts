export type EmptyStateKind = 'none' | 'trash' | 'filter' | 'steam' | 'vod-no-sources' | 'vod-no-clips'

interface Input {
  source: 'steam' | 'vod'
  loading: boolean
  error: boolean
  empty: boolean
  trashed: boolean
  filtered: boolean
  vodTotal: number
}

export function emptyStateKind(o: Input): EmptyStateKind {
  if (o.loading || o.error || !o.empty) return 'none'
  if (o.trashed) return 'trash'
  if (o.filtered) return 'filter'
  if (o.source === 'steam') return 'steam'
  return o.vodTotal === 0 ? 'vod-no-sources' : 'vod-no-clips'
}
