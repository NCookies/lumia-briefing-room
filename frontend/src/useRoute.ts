import { useCallback, useEffect, useRef, useState } from 'react'
import { formatRoute, initialRoute, listRoute, parseRoute, rememberRoute, shouldHistoryBack, type Route, type RouteMemo, type TabId } from './route'

interface NavState {
  route: Route
  /** 앱 안에서 만든 history 항목으로 들어왔는지(주소를 직접 열었거나 새로고침한 첫 항목이면 false). */
  inApp: boolean
}

const fromOf = (state: unknown): string | undefined => {
  const from = (state as { from?: unknown } | null)?.from
  return typeof from === 'string' ? from : undefined
}

/** 화면 주소(해시)와 화면 상태를 맞춘다. 탭·게임·카테고리를 바꿀 때마다 history 에 쌓아 브라우저 뒤로 가기가 앱 안에서 이동한다. */
export function useRoute(savedTab: TabId) {
  const [nav, setNav] = useState<NavState>(() => ({
    route: initialRoute(location.hash, savedTab),
    inApp: fromOf(history.state) !== undefined,
  }))
  const memo = useRef<RouteMemo>({})
  memo.current = rememberRoute(memo.current, nav.route)

  useEffect(() => {
    const hash = formatRoute(nav.route)
    if (location.hash !== hash) history.replaceState(history.state, '', hash)
  }, [])

  useEffect(() => {
    const onPop = () =>
      setNav((now) => ({ route: parseRoute(location.hash) ?? now.route, inApp: fromOf(history.state) !== undefined }))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((next: Route, replace = false) => {
    const hash = formatRoute(next)
    if (hash !== location.hash) {
      if (replace) history.replaceState(history.state, '', hash)
      else history.pushState({ from: location.hash }, '', hash)
    }
    setNav((now) => ({ route: next, inApp: replace ? now.inApp : true }))
  }, [])

  const back = useCallback(
    (route: Route) => {
      const target = listRoute(route)
      if (shouldHistoryBack(fromOf(history.state), target)) history.back()
      else navigate(target, true)
    },
    [navigate],
  )

  return { route: nav.route, inApp: nav.inApp, memo: memo.current, navigate, back }
}

/** 탭 하나가 받는 화면 이동 수단. 열린 게임은 주소가 정하고 목록 컴포넌트는 주소를 직접 만지지 않는다. */
export interface GameNav {
  openKey: string | null
  /** 앱 안에서 눌러 연 경우만 true - 직접 연 주소는 브라우저가 소리 있는 자동 재생을 막는다. */
  userOpened: boolean
  open: (key: string) => void
  /** `← 게임 목록` 과 브라우저 뒤로 가기가 같은 동작. */
  close: () => void
  /** 주소로 열었는데 게임이 없을 때 목록으로 바꿔 치운다(뒤로 가기에 남기지 않는다). */
  missing: () => void
}
