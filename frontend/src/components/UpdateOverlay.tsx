import { useEffect, useState } from 'react'
import { restartHint, restartProbe } from '../update'

/** 설치기가 뜬 뒤 앱이 종료·재시작되는 동안 화면이 멈춘 것처럼 보이지 않게 하고, 새 버전이 뜨면 스스로 새로고침한다. */
export function UpdateOverlay({ version }: { version: string }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    let sawDown = false
    let cancelled = false
    const probe = async () => {
      let reachable = false
      try {
        const res = await fetch('/api/app-info', { cache: 'no-store' })
        reachable = res.ok
      } catch {
        reachable = false
      }
      if (cancelled) return
      const next = restartProbe({ sawDown, reachable })
      sawDown = next.sawDown
      if (next.reload) window.location.reload()
    }
    const timer = window.setInterval(probe, 2000)
    const clock = window.setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      window.clearInterval(clock)
    }
  }, [])

  const hint = restartHint(elapsed)

  return (
    <div className="fixed inset-0 z-[300] flex flex-col items-center justify-center gap-6 bg-zinc-950 px-6 text-center text-zinc-100" role="alert">
      <div className="h-14 w-14 animate-spin rounded-full border-4 border-zinc-700 border-t-sky-400" />
      <div className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold">루미아 브리핑룸</h1>
        <p className="text-base text-zinc-200">{version ? `v${version} 으로 ` : ''}업데이트하는 중입니다</p>
      </div>
      <p className="max-w-sm text-sm text-zinc-400">
        화면에 뜬 <b className="font-medium text-zinc-200">설치 진행 창</b>에서 진행 상황을 볼 수 있습니다. 끝나면 앱이 다시 시작되고 이 화면도 자동으로 새로고침됩니다.
      </p>
      {hint && <p className="max-w-sm text-xs text-zinc-500">{hint}</p>}
    </div>
  )
}
