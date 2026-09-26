import { useEffect, useState } from 'react'
import type { AdminMode } from '../adminApi'
import { AdminDiagnostics } from './admin/AdminDiagnostics'
import { AdminLabels } from './admin/AdminLabels'
import { AdminLogs } from './admin/AdminLogs'
import { AdminStatus } from './admin/AdminStatus'

type Section = 'status' | 'diagnostics' | 'logs' | 'labels'

const SECTIONS: { id: Section; label: string }[] = [
  { id: 'status', label: '서버 상태' },
  { id: 'diagnostics', label: '진단 번들' },
  { id: 'logs', label: '오류 로그' },
  { id: 'labels', label: '라벨' },
]
const AUTO_REFRESH_MS = 5000
const inputClass = 'rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-sm text-zinc-100'

export function AdminPanel({ active }: { active: boolean }) {
  const [section, setSection] = useState<Section>('status')
  const [mode, setMode] = useState<AdminMode>('release')
  const [manualTick, setManualTick] = useState(0)
  const [autoTick, setAutoTick] = useState(0)
  const [auto, setAuto] = useState(false)

  useEffect(() => {
    if (!active || !auto || section === 'labels') return
    const timer = window.setInterval(() => setAutoTick((n) => n + 1), AUTO_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [active, auto, section])

  const tick = manualTick + autoTick

  return (
    <div className="flex flex-1 flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <nav className="flex gap-1" role="tablist">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={section === s.id}
              className={`rounded border px-3 py-1 text-sm ${
                section === s.id ? 'border-sky-500 bg-zinc-800 font-semibold' : 'border-zinc-700 text-zinc-400 hover:text-zinc-200'
              }`}
              onClick={() => setSection(s.id)}
            >
              {s.label}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          {section !== 'labels' && (
            <label className="flex items-center gap-1 text-xs text-zinc-300">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
              5초마다 자동 새로고침
            </label>
          )}
          {section !== 'status' && (
            <select className={inputClass} value={mode} onChange={(e) => setMode(e.target.value as AdminMode)}>
              <option value="release">release</option>
              <option value="dev">dev</option>
            </select>
          )}
          <button
            type="button"
            className="rounded border border-zinc-600 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
            onClick={() => setManualTick((n) => n + 1)}
          >
            새로고침
          </button>
        </div>
      </div>
      <p className="text-xs text-zinc-500">
        서버에 쌓인 데이터(개발 모드 전용). 관리자 토큰은 저장소 루트 .env 의 LUMIA_ADMIN_TOKEN 을 씁니다.
      </p>

      {section === 'status' && <AdminStatus active={active} tick={tick} />}
      {section === 'diagnostics' && <AdminDiagnostics mode={mode} active={active} tick={tick} />}
      {section === 'logs' && <AdminLogs mode={mode} active={active} tick={tick} />}
      {section === 'labels' && <AdminLabels mode={mode} active={active} refreshTick={manualTick} />}
    </div>
  )
}
