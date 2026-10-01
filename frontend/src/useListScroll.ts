import { useLayoutEffect, useRef } from 'react'

/** 게임을 열면 맨 위로, 목록으로 돌아오면 열기 직전 스크롤 위치로. 반환 함수는 열기 직전에 불러 위치를 적어 둔다. */
export function useListScroll(open: string | null, active: boolean) {
  const saved = useRef(0)
  const wasOpen = useRef(open !== null)

  useLayoutEffect(() => {
    const isOpen = open !== null
    if (isOpen === wasOpen.current) return
    wasOpen.current = isOpen
    if (!active) return
    window.scrollTo(0, isOpen ? 0 : saved.current)
  }, [open, active])

  return () => {
    saved.current = window.scrollY
  }
}
