import { useEffect, useState } from 'react'
import type { CleanupPreviewMap } from './cleanupPreview'
import { getCleanupPreview } from './cleanupPreviewApi'

const POLL_MS = 10000

/** 자동 정리 삭제 예정 목록을 주기적으로 읽는다(스팀 녹화 탭에서만 켠다 — 영상 파일은 자동 정리 대상이 아니다, SPEC §7.10). */
export function useCleanupPreview(enabled: boolean): CleanupPreviewMap {
  const [preview, setPreview] = useState<CleanupPreviewMap>({})

  useEffect(() => {
    if (!enabled) {
      setPreview({})
      return
    }
    let cancelled = false
    const poll = async () => {
      try {
        const current = await getCleanupPreview()
        if (!cancelled) setPreview(current)
      } catch {
        // 서버가 잠깐 응답하지 못해도 화면은 이전 값을 그대로 보여준다
      }
    }
    void poll()
    const timer = window.setInterval(poll, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [enabled])

  return preview
}
