import { useCallback, useEffect, useState } from 'react'
import {
  ADMIN_PAGE_SIZE,
  barWidths,
  getAdminLabels,
  getAdminSummary,
  pageRange,
  type AdminLabelPage,
  type AdminMode,
  type AdminSummary,
} from '../../adminApi'

function Bars({ title, data }: { title: string; data: Record<string, number> }) {
  const rows = barWidths(data)
  return (
    <div className="rounded border border-zinc-700 bg-zinc-800 p-3">
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      {rows.length === 0 && <p className="text-xs text-zinc-500">없음</p>}
      {rows.map(([key, value, width]) => (
        <div key={key} className="my-1 flex items-center gap-2 text-xs">
          <span className="w-24 shrink-0 truncate">{key}</span>
          <span className="h-2 rounded bg-sky-500" style={{ width: `${width}px` }} />
          <span>{value}</span>
        </div>
      ))}
    </div>
  )
}

const inputClass = 'rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-sm text-zinc-100'

export function AdminLabels({ mode, active, refreshTick }: { mode: AdminMode; active: boolean; refreshTick: number }) {
  const [summary, setSummary] = useState<AdminSummary | null>(null)
  const [page, setPage] = useState<AdminLabelPage>({ total: 0, items: [] })
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('')
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setSummary(await getAdminSummary(mode, refreshTick > 0))
      setPage(await getAdminLabels(mode, query, kind, offset))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [mode, query, kind, offset, refreshTick])

  useEffect(() => {
    if (!active) return
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [active, load])

  useEffect(() => setOffset(0), [mode])

  return (
    <div className="flex flex-col gap-3">
      {loading && <p className="text-xs text-zinc-500">불러오는 중…</p>}
      {error && <p className="rounded border border-red-800 bg-red-950 p-2 text-sm text-red-300">{error}</p>}

      {summary && (
        <>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
            <div className="rounded border border-zinc-700 bg-zinc-800 p-3">
              <div className="text-xs text-zinc-400">라벨</div>
              <div className="text-2xl font-semibold">{summary.total}</div>
            </div>
            <div className="rounded border border-zinc-700 bg-zinc-800 p-3">
              <div className="text-xs text-zinc-400">설치</div>
              <div className="text-2xl font-semibold">{summary.installs}</div>
            </div>
            <div className="rounded border border-zinc-700 bg-zinc-800 p-3">
              <div className="text-xs text-zinc-400">마지막 수신</div>
              <div className="text-sm">{summary.lastReceivedAt ?? '-'}</div>
            </div>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
            <Bars title="라벨 종류" data={summary.byLabel} />
            <Bars title="앱 버전" data={summary.byVersion} />
            <Bars title="해상도" data={summary.byResolution} />
            <Bars title="수신 일자" data={summary.byDay} />
          </div>
          <div className="overflow-x-auto rounded border border-zinc-700 bg-zinc-800 p-3">
            <h3 className="mb-2 text-sm font-semibold">설치별</h3>
            <table className="w-full text-left text-xs">
              <thead className="text-zinc-400">
                <tr>
                  <th className="py-1 pr-3">installId</th>
                  <th className="pr-3">라벨</th>
                  <th className="pr-3">combat</th>
                  <th className="pr-3">other</th>
                  <th>마지막 수신</th>
                </tr>
              </thead>
              <tbody>
                {summary.perInstall.map((r) => (
                  <tr key={r.installId} className="border-t border-zinc-700">
                    <td className="py-1 pr-3 font-mono">{r.installId}</td>
                    <td className="pr-3">{r.count}</td>
                    <td className="pr-3">{r.combat}</td>
                    <td className="pr-3">{r.other}</td>
                    <td>{r.lastReceivedAt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="rounded border border-zinc-700 bg-zinc-800 p-3">
        <h3 className="mb-2 text-sm font-semibold">라벨 검색</h3>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <input
            className={`${inputClass} w-72`}
            placeholder="installId 앞부분 또는 clipKey"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setOffset(0)
            }}
          />
          <select
            className={inputClass}
            value={kind}
            onChange={(e) => {
              setKind(e.target.value)
              setOffset(0)
            }}
          >
            <option value="">전체</option>
            <option value="combat">combat</option>
            <option value="other">other</option>
          </select>
          <button
            type="button"
            className="rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - ADMIN_PAGE_SIZE))}
          >
            이전
          </button>
          <button
            type="button"
            className="rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40"
            disabled={offset + ADMIN_PAGE_SIZE >= page.total}
            onClick={() => setOffset(offset + ADMIN_PAGE_SIZE)}
          >
            다음
          </button>
          <span className="text-xs text-zinc-400">{pageRange(offset, page.total)}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-zinc-400">
              <tr>
                <th className="py-1 pr-3">수신</th>
                <th className="pr-3">installId</th>
                <th className="pr-3">clipKey</th>
                <th className="pr-3">종류</th>
                <th className="pr-3">버전</th>
                <th>해상도</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((it) => (
                <tr key={`${it.installId}-${it.label.clipKey}`} className="border-t border-zinc-700">
                  <td className="py-1 pr-3">{it.receivedAt}</td>
                  <td className="pr-3 font-mono">{it.installId}</td>
                  <td className="pr-3 font-mono">{it.label.clipKey}</td>
                  <td className="pr-3">{it.label.userLabel}</td>
                  <td className="pr-3">{it.appVersion}</td>
                  <td>
                    {it.label.sourceWidth}x{it.label.sourceHeight}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
