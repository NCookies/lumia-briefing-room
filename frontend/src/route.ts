export type TabId = 'steam' | 'vod' | 'library' | 'admin'

export interface Route {
  tab: TabId
  game?: string
  /** 풀영상 화면을 그 후보가 선택된 채로 연다(클립 탭 `풀영상 보기·범위 고치기`). */
  cand?: string
  category?: string
  /** 클립 탭의 재생 화면. 카테고리와 같이 있어야 한다. */
  clip?: string
}

const PATH_OF: Record<TabId, string> = { steam: 'steam', vod: 'vod', library: 'clips', admin: 'admin' }
const TAB_OF: Record<string, TabId> = { steam: 'steam', vod: 'vod', clips: 'library', admin: 'admin' }

export function formatRoute(route: Route): string {
  const base = `#/${PATH_OF[route.tab]}`
  if (route.game && (route.tab === 'steam' || route.tab === 'vod')) {
    const game = `${base}/game/${encodeURIComponent(route.game)}`
    return route.cand ? `${game}/cand/${encodeURIComponent(route.cand)}` : game
  }
  if (route.category && route.tab === 'library') {
    const list = `${base}/${encodeURIComponent(route.category)}`
    return route.clip ? `${list}/clip/${encodeURIComponent(route.clip)}` : list
  }
  return base
}

export function parseRoute(hash: string): Route | null {
  if (!hash.startsWith('#/')) return null
  const [head, ...tail] = hash.slice(2).split('/')
  const tab = TAB_OF[head]
  if (!tab) return null
  try {
    if (tab === 'library') {
      if (tail.length >= 3 && tail[tail.length - 2] === 'clip' && tail[tail.length - 1]) {
        const category = tail.slice(0, -2).join('/')
        if (category) return { tab, category: decodeURIComponent(category), clip: decodeURIComponent(tail[tail.length - 1]) }
      }
      return tail.length > 0 && tail.join('/') ? { tab, category: decodeURIComponent(tail.join('/')) } : { tab }
    }
    if ((tab === 'steam' || tab === 'vod') && tail[0] === 'game' && tail[1]) {
      const game = decodeURIComponent(tail[1])
      return tail[2] === 'cand' && tail[3] ? { tab, game, cand: decodeURIComponent(tail[3]) } : { tab, game }
    }
  } catch {
    return null
  }
  return { tab }
}

/** 주소가 있으면 주소가 우선, 없거나 알 수 없으면(첫 접속) 기억한 탭. */
export function initialRoute(hash: string, savedTab: TabId): Route {
  return parseRoute(hash) ?? { tab: savedTab }
}

export function listRoute(route: Route): Route {
  if (route.game) return { tab: route.tab }
  if (route.clip) return { tab: route.tab, category: route.category }
  return route
}

/** `← 게임 목록` 이 history.back() 과 같게 되는 경우: 바로 앞 항목이 돌아갈 목록 주소일 때만. */
export function shouldHistoryBack(previousHash: string | undefined, target: Route): boolean {
  return previousHash === formatRoute(target)
}

export type RouteMemo = Partial<Record<TabId, Route>>

export function rememberRoute(memo: RouteMemo, route: Route): RouteMemo {
  return { ...memo, [route.tab]: route }
}
