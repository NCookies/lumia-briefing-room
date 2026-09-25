import { useEffect, useState } from 'react'
import { DIAGNOSTICS_URL } from '../onboardingApi'
import { diagnosticsSummary, receiptShareText, type DiagnosticsPreview, type DiagnosticsResult } from '../telemetry'
import { getDiagnosticsPreview, sendDiagnostics } from '../telemetryApi'

function Raw({ value }: { value: unknown }) {
  return (
    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-zinc-900 p-2 text-[11px] text-zinc-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function DiagnosticsSendDialog({ onClose, onSent }: { onClose: () => void; onSent: () => void }) {
  const [preview, setPreview] = useState<DiagnosticsPreview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<DiagnosticsResult | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    getDiagnosticsPreview()
      .then(setPreview)
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const send = async () => {
    setSending(true)
    setError(null)
    try {
      setResult(await sendDiagnostics())
      onSent()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSending(false)
    }
  }

  const copy = () => {
    if (!preview) return
    void navigator.clipboard
      ?.writeText(receiptShareText(result?.receiptId ?? null, preview.displayId))
      .then(() => setCopied(true))
      .catch(() => {})
  }

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="flex h-[min(40rem,90vh)] w-full max-w-3xl flex-col rounded-lg border border-zinc-600 bg-zinc-800 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
          <h2 className="text-base font-medium">진단 정보 보내기</h2>
          <button type="button" className="text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            닫기 ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {result ? (
            <div className="space-y-3">
              <p className="text-sm text-emerald-300">진단 정보를 보냈습니다. 아래 번호를 개발자에게 알려 주세요.</p>
              <p className="rounded border border-emerald-500/50 bg-emerald-500/10 p-3 text-center text-2xl font-semibold tracking-wider">
                {result.receiptId ?? '(접수 번호를 받지 못했습니다)'}
              </p>
              {preview && (
                <p className="text-xs text-zinc-400">
                  내 설치 ID: <code className="text-zinc-200">{preview.displayId}</code> · 이 ID 로도 보낸 내용을 찾을 수 있습니다.
                </p>
              )}
              <button
                type="button"
                className="rounded bg-zinc-700 px-3 py-1.5 text-sm hover:bg-zinc-600"
                onClick={copy}
              >
                {copied ? '복사했습니다' : '접수 번호와 ID 복사'}
              </button>
            </div>
          ) : (
            <>
              <p className="text-xs text-zinc-400">
                아래 내용만 서버로 한 번 보냅니다. 닉네임과 경로 속 사용자 이름은 이미 지운 상태이고, 영상·이미지는
                들어가지 않습니다. 오류 로그 전송 설정과 관계없이, 이 버튼을 누를 때만 보내며 그 뒤로 자동 전송이
                켜지지는 않습니다.
              </p>
              {!preview && !error && <p className="text-sm text-zinc-400">불러오는 중…</p>}
              {preview && (
                <>
                  <p className="text-sm text-zinc-200">{diagnosticsSummary(preview)}</p>
                  <section className="space-y-1">
                    <h3 className="text-sm font-medium">환경 정보</h3>
                    <Raw value={preview.env} />
                  </section>
                  <section className="space-y-2">
                    <h3 className="text-sm font-medium">
                      오류 기록 {preview.count}건 (최근 순서대로 최대 100건)
                    </h3>
                    {preview.items.length === 0 && <p className="text-xs text-zinc-500">보낼 오류 기록이 없습니다.</p>}
                    {preview.items.map((item, i) => (
                      <details key={i} className="rounded border border-zinc-700 bg-zinc-900/50 p-2 text-sm">
                        <summary className="cursor-pointer break-all">
                          {String(item.level)} · {String(item.message).slice(0, 80)}
                        </summary>
                        <Raw value={item} />
                      </details>
                    ))}
                  </section>
                  {!preview.canSend && (
                    <p className="text-xs text-amber-300">
                      {preview.endpointConfigured
                        ? '개발 모드에서는 서버로 보내지 않습니다.'
                        : '이 빌드에는 서버 연결 정보가 없어 보낼 수 없습니다.'}{' '}
                      대신 아래 "파일로 저장"을 눌러 zip 파일을 보내 주세요.
                    </p>
                  )}
                </>
              )}
            </>
          )}
          {error && (
            <div className="space-y-1 rounded border border-rose-500/50 bg-rose-500/10 p-3 text-sm text-rose-200">
              <p>{error}</p>
              <a href={DIAGNOSTICS_URL} download className="inline-block text-sky-300 underline hover:text-sky-200">
                파일로 저장 (진단 정보 zip)
              </a>
            </div>
          )}
        </div>
        {!result && (
          <div className="flex items-center justify-end gap-2 border-t border-zinc-700 px-4 py-3">
            <a
              href={DIAGNOSTICS_URL}
              download
              className="rounded px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700"
            >
              파일로 저장
            </a>
            <button type="button" className="rounded px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-700" onClick={onClose}>
              취소
            </button>
            <button
              type="button"
              className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40"
              disabled={!preview || !preview.canSend || sending}
              onClick={() => void send()}
            >
              {sending ? '보내는 중…' : '이 내용을 서버로 보내기'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
