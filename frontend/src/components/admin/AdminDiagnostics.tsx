import { useState } from 'react'
import {
  ADMIN_PAGE_SIZE,
  getDiagnostic,
  getDiagnostics,
  pageRange,
  type AdminMode,
  type DiagnosticDetail,
} from '../../adminApi'
import { useAdminData } from './useAdminData'

const inputClass = 'rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-sm text-zinc-100'
const buttonClass = 'rounded border border-zinc-600 px-2 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40'

function Detail({ mode, receiptId, onClose }: { mode: AdminMode; receiptId: string; onClose: () => void }) {
  const { data, error } = useAdminData<DiagnosticDetail>(() => getDiagnostic(mode, receiptId), [mode, receiptId], true, 0)
  return (
    <div className="rounded border border-sky-700 bg-zinc-800 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          {receiptId} {data?.displayId && <span className="ml-2 font-normal text-zinc-400">{data.displayId}</span>}
        </h3>
        <button type="button" className={buttonClass} onClick={onClose}>
          닫기
        </button>
      </div>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {data && (
        <>
          <p className="mb-2 text-xs text-zinc-400">
            installId <span className="font-mono">{data.installId}</span> · 수신 {data.receivedAt}
          </p>
          <pre className="mb-2 max-h-48 overflow-auto rounded bg-zinc-900 p-2 text-xs">{JSON.stringify(data.env, null, 2)}</pre>
          <div className="max-h-96 overflow-auto">
            {data.entries.map((entry, i) => (
              <div key={i} className="border-t border-zinc-700 py-1 text-xs">
                <span className={entry.level === 'ERROR' || entry.level === 'CRITICAL' ? 'text-red-300' : 'text-amber-300'}>
                  {entry.level}
                </span>{' '}
                <span className="text-zinc-500">{entry.ts}</span> {entry.exceptionType && <b>{entry.exceptionType} </b>}
                {entry.message}
                {entry.stack && <pre className="mt-1 overflow-auto rounded bg-zinc-900 p-2 text-[11px]">{entry.stack}</pre>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export function AdminDiagnostics({ mode, active, tick }: { mode: AdminMode; active: boolean; tick: number }) {
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [open, setOpen] = useState<string | null>(null)
  const { data, error, loading } = useAdminData(() => getDiagnostics(mode, query, offset), [mode, query, offset], active, tick)
  const total = data?.total ?? 0

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          className={`${inputClass} w-80`}
          placeholder="접수 번호 · LUMIA-XXXX-XXXX · installId 앞부분"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOffset(0)
          }}
        />
        <button type="button" className={buttonClass} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - ADMIN_PAGE_SIZE))}>
          이전
        </button>
        <button type="button" className={buttonClass} disabled={offset + ADMIN_PAGE_SIZE >= total} onClick={() => setOffset(offset + ADMIN_PAGE_SIZE)}>
          다음
        </button>
        <span className="text-xs text-zinc-400">{loading ? '불러오는 중…' : pageRange(offset, total)}</span>
      </div>
      {error && <p className="rounded border border-red-800 bg-red-950 p-2 text-sm text-red-300">{error}</p>}
      {open && <Detail mode={mode} receiptId={open} onClose={() => setOpen(null)} />}
      <div className="overflow-x-auto rounded border border-zinc-700 bg-zinc-800 p-3">
        <table className="w-full text-left text-xs">
          <thead className="text-zinc-400">
            <tr>
              <th className="py-1 pr-3">접수 번호</th>
              <th className="pr-3">표시용 ID</th>
              <th className="pr-3">수신</th>
              <th className="pr-3">버전</th>
              <th className="pr-3">OS</th>
              <th className="pr-3">항목</th>
              <th className="pr-3">오류</th>
              <th>installId</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((d) => (
              <tr key={d.receiptId} className="cursor-pointer border-t border-zinc-700 hover:bg-zinc-700" onClick={() => setOpen(d.receiptId)}>
                <td className="py-1 pr-3 font-mono">{d.receiptId}</td>
                <td className="pr-3 font-mono">{d.displayId}</td>
                <td className="pr-3">{d.receivedAt}</td>
                <td className="pr-3">{d.appVersion}</td>
                <td className="pr-3">{d.os}</td>
                <td className="pr-3">{d.entryCount}</td>
                <td className={`pr-3 ${d.errorCount ? 'text-red-300' : ''}`}>{d.errorCount}</td>
                <td className="font-mono">{d.installId}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <p className="py-2 text-xs text-zinc-500">받은 진단 번들이 없습니다.</p>}
      </div>
    </div>
  )
}
