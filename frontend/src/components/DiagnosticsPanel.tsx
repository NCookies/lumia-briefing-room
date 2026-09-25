import { useCallback, useEffect, useState } from 'react'
import { DIAGNOSTICS_URL } from '../onboardingApi'
import { DISPLAY_ID_NOTICE, formatSentAt, type TelemetryStatus } from '../telemetry'
import { getTelemetryStatus } from '../telemetryApi'
import { DiagnosticsSendDialog } from './DiagnosticsSendDialog'

export function DiagnosticsPanel() {
  const [status, setStatus] = useState<TelemetryStatus | null>(null)
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const load = useCallback(() => {
    getTelemetryStatus()
      .then(setStatus)
      .catch(() => {})
  }, [])

  useEffect(load, [load])

  const copyId = () => {
    if (!status) return
    void navigator.clipboard
      ?.writeText(status.displayId)
      .then(() => setCopied(true))
      .catch(() => {})
  }

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-200">진단 정보 보내기</h3>
      <p className="text-xs text-zinc-500">
        문제가 생겼을 때 누르면 로그 발췌·버전·환경·판독 실패 통계를 서버로 한 번 보내고 접수 번호를 알려 줍니다.
        보내기 전에 내용을 미리 볼 수 있고, 닉네임과 경로 속 사용자 이름은 지워지며 영상이나 화면은 들어가지 않습니다.
        오류 로그 전송 설정과 관계없이 이 버튼을 누를 때만 보냅니다.
      </p>
      {status && (
        <>
          <p className="text-sm text-zinc-300">
            내 설치 ID: <code className="select-all text-zinc-100">{status.displayId}</code>{' '}
            <button type="button" className="text-xs text-sky-300 hover:text-sky-200" onClick={copyId}>
              {copied ? '복사했습니다' : '복사'}
            </button>
          </p>
          <p className="text-xs text-zinc-500">{DISPLAY_ID_NOTICE}</p>
          {status.lastDiagnosticReceipt && (
            <p className="text-xs text-zinc-400">
              마지막으로 보낸 접수 번호: <code className="text-zinc-200">{status.lastDiagnosticReceipt}</code> (
              {formatSentAt(status.lastDiagnosticAt)})
            </p>
          )}
        </>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500" onClick={() => setOpen(true)}>
          진단 정보 보내기
        </button>
        <a href={DIAGNOSTICS_URL} download className="rounded bg-zinc-700 px-3 py-1.5 text-sm hover:bg-zinc-600">
          진단 정보 zip 받기 (파일로 저장)
        </a>
      </div>
      <p className="text-xs text-zinc-500">
        서버로 보낼 수 없을 때(오프라인·서버 점검 등)는 zip 파일을 받아 직접 보내 주세요. 앱이 아예 안 뜨면 로그 폴더의
        파일을 보내 주세요.
      </p>
      {open && <DiagnosticsSendDialog onClose={() => setOpen(false)} onSent={load} />}
    </section>
  )
}
