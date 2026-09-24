import { useEffect, useState } from 'react'
import { getTelemetryPreview } from '../telemetryApi'
import { LABEL_TEXT } from '../consent'
import type { TelemetryPreview } from '../telemetry'

const wireLabel = (value: unknown): string =>
  value === 'combat' ? LABEL_TEXT.pvp : value === 'other' ? LABEL_TEXT.pve : '?'

function Raw({ value }: { value: unknown }) {
  return (
    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-zinc-900 p-2 text-[11px] text-zinc-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function TelemetryPreviewDialog({ onClose }: { onClose: () => void }) {
  const [preview, setPreview] = useState<TelemetryPreview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getTelemetryPreview()
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

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="flex h-[min(40rem,90vh)] w-full max-w-3xl flex-col rounded-lg border border-zinc-600 bg-zinc-800 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
          <h2 className="text-base font-medium">보낼 내용 미리보기</h2>
          <button type="button" className="text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            닫기 ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <p className="text-xs text-zinc-400">
            아직 서버로 보내지 않은 내용입니다. 닉네임과 경로 속 사용자 이름은 이미 지운 상태이고, 영상·이미지는
            없습니다. 이 화면을 여는 것만으로는 아무것도 전송되지 않습니다.
          </p>
          {error && <p className="text-sm text-rose-300">{error}</p>}
          {!preview && !error && <p className="text-sm text-zinc-400">불러오는 중…</p>}
          {preview && (
            <>
              <section className="flex flex-col gap-2 shrink-0">
                <h3 className="text-sm font-medium">
                  라벨 {preview.labels.count}건
                  {preview.labels.count > preview.labels.items.length &&
                    ` (앞의 ${preview.labels.items.length}건만 표시)`}
                </h3>
                {preview.labels.items.length === 0 && <p className="text-xs text-zinc-500">보낼 라벨이 없습니다.</p>}
                {preview.labels.items.map((item, i) => (
                  <details key={i} className="rounded border border-zinc-700 bg-zinc-900/50 p-2 text-sm">
                    <summary className="cursor-pointer">
                      {wireLabel(item.userLabel)}
                      {item.source === 'vod' && ' · 다시보기'}
                      {typeof item.labelNote === 'string' && ` · 메모: ${item.labelNote}`}
                    </summary>
                    <Raw value={item} />
                  </details>
                ))}
              </section>
              <section className="flex flex-col gap-2 shrink-0">
                <h3 className="text-sm font-medium">환경 정보 (오류 로그와 함께 보냄)</h3>
                <Raw value={preview.logs.env} />
              </section>
              <section className="flex flex-col gap-2 shrink-0">
                <h3 className="text-sm font-medium">
                  오류 로그 {preview.logs.count}건
                  {preview.logs.count > preview.logs.items.length &&
                    ` (앞의 ${preview.logs.items.length}건만 표시)`}
                </h3>
                {preview.logs.items.length === 0 && (
                  <p className="text-xs text-zinc-500">보낼 오류 로그가 없습니다.</p>
                )}
                {preview.logs.items.map((item, i) => (
                  <details key={i} className="rounded border border-zinc-700 bg-zinc-900/50 p-2 text-sm">
                    <summary className="cursor-pointer break-all">
                      {String(item.level)} · {String(item.message).slice(0, 80)}
                    </summary>
                    <Raw value={item} />
                  </details>
                ))}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
