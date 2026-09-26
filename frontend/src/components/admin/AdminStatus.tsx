import { agoLabel, formatBytes, getServerStatus, type ModeStatus } from '../../adminApi'
import { useAdminData } from './useAdminData'

const KIND_LABELS: [keyof ModeStatus['lastReceived'], string][] = [
  ['labels', '라벨'],
  ['logs', '오류 로그'],
  ['diagnostics', '진단 번들'],
]

function ModeCard({ title, status }: { title: string; status: ModeStatus }) {
  return (
    <div className="rounded border border-zinc-700 bg-zinc-800 p-3">
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      <div className="mb-2 flex gap-4 text-xs text-zinc-300">
        <span>설치 {status.installs}</span>
        <span>라벨 {status.labels}</span>
        <span>로그 파일 {status.logEntryFiles}</span>
        <span>진단 {status.diagnostics}</span>
      </div>
      <table className="w-full text-left text-xs">
        <tbody>
          {KIND_LABELS.map(([key, label]) => (
            <tr key={key} className="border-t border-zinc-700">
              <td className="py-1 pr-3 text-zinc-400">마지막 {label} 수신</td>
              <td>{agoLabel(status.lastReceived[key])}</td>
              <td className="text-zinc-500">{status.lastReceived[key] ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Counts({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts)
  return (
    <div className="rounded border border-zinc-700 bg-zinc-800 p-3">
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      {entries.length === 0 && <p className="text-xs text-zinc-500">없음</p>}
      {entries.map(([key, value]) => (
        <div key={key} className="flex justify-between text-xs">
          <span>{key}</span>
          <span>{value}</span>
        </div>
      ))}
    </div>
  )
}

export function AdminStatus({ active, tick }: { active: boolean; tick: number }) {
  const { data, error, loading } = useAdminData(getServerStatus, [], active, tick)
  return (
    <div className="flex flex-col gap-3">
      {error && <p className="rounded border border-red-800 bg-red-950 p-2 text-sm text-red-300">{error}</p>}
      {loading && !data && <p className="text-xs text-zinc-500">불러오는 중…</p>}
      {data && (
        <>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-3">
            <ModeCard title="release (배포판이 보낸 것)" status={data.release} />
            <ModeCard title="dev (개발 모드가 보낸 것)" status={data.dev} />
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
            <Counts title="오늘 받은 요청" counts={data.today.requests} />
            <Counts title="오늘 거부한 요청" counts={data.today.rejected} />
            <div className="rounded border border-zinc-700 bg-zinc-800 p-3 text-xs">
              <h3 className="mb-2 text-sm font-semibold">서버</h3>
              <div className="flex justify-between">
                <span>디스크 사용률</span>
                <span>{data.disk.usedPercent}%</span>
              </div>
              <div className="flex justify-between">
                <span>수신 데이터 용량</span>
                <span>{formatBytes(data.disk.dataBytes)}</span>
              </div>
              <div className="flex justify-between">
                <span>차단 중인 IP</span>
                <span>{data.blockedIps}개</span>
              </div>
              <div className="flex justify-between">
                <span>로그·진단 보관</span>
                <span>{data.retentionDays}일</span>
              </div>
              <div className="mt-1 text-zinc-500">서버 시각 {data.serverTime}</div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
