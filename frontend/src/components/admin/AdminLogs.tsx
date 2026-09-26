import { useState } from 'react'
import { ADMIN_PAGE_SIZE, getLogGroups, getLogs, pageRange, type AdminMode } from '../../adminApi'
import { useAdminData } from './useAdminData'

const inputClass = 'rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-sm text-zinc-100'
const buttonClass = 'rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40'
const levelClass = (level: string | null) => (level === 'ERROR' || level === 'CRITICAL' ? 'text-red-300' : 'text-amber-300')

export function AdminLogs({ mode, active, tick }: { mode: AdminMode; active: boolean; tick: number }) {
  const [query, setQuery] = useState('')
  const [level, setLevel] = useState('')
  const [offset, setOffset] = useState(0)
  const groups = useAdminData(() => getLogGroups(mode), [mode], active, tick)
  const logs = useAdminData(() => getLogs(mode, query, level, offset), [mode, query, level, offset], active, tick)
  const total = logs.data?.total ?? 0
  const error = groups.error ?? logs.error

  return (
    <div className="flex flex-col gap-3">
      {error && <p className="rounded border border-red-800 bg-red-950 p-2 text-sm text-red-300">{error}</p>}
      <div className="overflow-x-auto rounded border border-zinc-700 bg-zinc-800 p-3">
        <h3 className="mb-2 text-sm font-semibold">같은 오류 묶음 (많은 순)</h3>
        <table className="w-full text-left text-xs">
          <thead className="text-zinc-400">
            <tr>
              <th className="py-1 pr-3">횟수</th>
              <th className="pr-3">설치</th>
              <th className="pr-3">수준</th>
              <th className="pr-3">예외</th>
              <th className="pr-3">대표 메시지</th>
              <th className="pr-3">처음</th>
              <th>마지막</th>
            </tr>
          </thead>
          <tbody>
            {(groups.data ?? []).map((g, i) => (
              <tr key={g.fingerprint ?? `${i}-${g.message}`} className="border-t border-zinc-700 align-top">
                <td className="py-1 pr-3 font-semibold">{g.count}</td>
                <td className="pr-3">{g.installs}</td>
                <td className={`pr-3 ${levelClass(g.level)}`}>{g.level}</td>
                <td className="pr-3">{g.exceptionType}</td>
                <td className="pr-3">{g.message}</td>
                <td className="pr-3 whitespace-nowrap">{g.firstSeen}</td>
                <td className="whitespace-nowrap">{g.lastSeen}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {groups.data && groups.data.length === 0 && <p className="py-2 text-xs text-zinc-500">받은 오류 로그가 없습니다.</p>}
      </div>

      <div className="rounded border border-zinc-700 bg-zinc-800 p-3">
        <h3 className="mb-2 text-sm font-semibold">오류 로그 (최신순)</h3>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <input
            className={`${inputClass} w-72`}
            placeholder="메시지·예외 검색"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setOffset(0)
            }}
          />
          <select
            className={inputClass}
            value={level}
            onChange={(e) => {
              setLevel(e.target.value)
              setOffset(0)
            }}
          >
            <option value="">모든 수준</option>
            <option value="ERROR">ERROR</option>
            <option value="WARNING">WARNING</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <button type="button" className={buttonClass} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - ADMIN_PAGE_SIZE))}>
            이전
          </button>
          <button type="button" className={buttonClass} disabled={offset + ADMIN_PAGE_SIZE >= total} onClick={() => setOffset(offset + ADMIN_PAGE_SIZE)}>
            다음
          </button>
          <span className="text-xs text-zinc-400">{logs.loading ? '불러오는 중…' : pageRange(offset, total)}</span>
        </div>
        <div className="max-h-[32rem] overflow-auto">
          {(logs.data?.items ?? []).map((e, i) => (
            <div key={i} className="border-t border-zinc-700 py-1 text-xs">
              <span className={levelClass(e.level)}>{e.level}</span> <span className="text-zinc-500">{e.ts}</span>{' '}
              <span className="font-mono text-zinc-500">{e.installId.slice(0, 8)}</span> <span className="text-zinc-500">v{e.appVersion}</span>{' '}
              {e.exceptionType && <b>{e.exceptionType} </b>}
              {e.message}
              {e.stack && <pre className="mt-1 overflow-auto rounded bg-zinc-900 p-2 text-[11px]">{e.stack}</pre>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
