import { useCallback, useEffect, useState } from 'react'
import { useConfirm } from '../confirmContext'
import { formatSentAt, pendingText, sendStateText, type TelemetryStatus } from '../telemetry'
import { deleteSentData, getTelemetryStatus } from '../telemetryApi'
import { PrivacyLink } from './PrivacyLink'
import { TelemetryPreviewDialog } from './TelemetryPreviewDialog'

export function TelemetryPanel({ refreshKey, onChanged }: { refreshKey: unknown; onChanged: () => void }) {
  const ask = useConfirm()
  const [status, setStatus] = useState<TelemetryStatus | null>(null)
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    getTelemetryStatus()
      .then(setStatus)
      .catch((e: Error) => setMessage({ text: e.message, error: true }))
  }, [])

  useEffect(load, [load, refreshKey])

  const requestDeletion = async () => {
    const confirmed = await ask({
      message:
        '서버에 보낸 라벨·오류 로그·진단 정보를 모두 삭제하도록 요청합니다. 삭제하면 전송이 꺼지고, 나중에 다시 켜면 처음부터 다시 보냅니다. 계속하시겠습니까?',
      confirmLabel: '삭제 요청',
      danger: true,
    })
    if (!confirmed.ok) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await deleteSentData()
      setMessage({
        text: result.deleted
          ? '서버에서 삭제했습니다. 전송을 껐습니다.'
          : '서버에 보낸 데이터가 없었습니다. 전송을 껐습니다.',
        error: false,
      })
      onChanged()
      load()
    } catch (e) {
      setMessage({ text: (e as Error).message, error: true })
    } finally {
      setBusy(false)
    }
  }

  const copyId = () => {
    if (status) void navigator.clipboard?.writeText(status.installId).catch(() => {})
  }

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-200">보낸 데이터</h3>
      {status ? (
        <>
          <p className="text-sm text-zinc-300">{sendStateText(status)}</p>
          <ul className="space-y-0.5 text-xs text-zinc-500">
            <li>
              라벨: 마지막 전송 {formatSentAt(status.lastLabelsSentAt)} · {pendingText(status.pendingLabels, '라벨')}
            </li>
            <li>
              오류 로그: 마지막 전송 {formatSentAt(status.lastLogsSentAt)} ·{' '}
              {pendingText(status.pendingLogs, '오류 로그')}
            </li>
          </ul>
          <p className="break-all text-xs text-zinc-500">
            설치 식별자(삭제 요청 확인용, 계정·닉네임과 연결되지 않음):{' '}
            <code className="select-all text-zinc-300">{status.installId}</code>{' '}
            <button type="button" className="text-sky-300 hover:text-sky-200" onClick={copyId}>
              복사
            </button>
          </p>
        </>
      ) : (
        !message && <p className="text-xs text-zinc-500">불러오는 중…</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="rounded bg-zinc-700 px-3 py-1.5 text-sm hover:bg-zinc-600"
          onClick={() => setPreviewOpen(true)}
        >
          보낼 내용 미리보기
        </button>
        <button
          type="button"
          className="rounded bg-rose-700 px-3 py-1.5 text-sm hover:bg-rose-600 disabled:opacity-40"
          disabled={busy}
          onClick={() => void requestDeletion()}
        >
          보낸 데이터 삭제 요청
        </button>
      </div>
      {message && <p className={`text-xs ${message.error ? 'text-rose-300' : 'text-emerald-300'}`}>{message.text}</p>}
      <PrivacyLink />
      {previewOpen && <TelemetryPreviewDialog onClose={() => setPreviewOpen(false)} />}
    </section>
  )
}
