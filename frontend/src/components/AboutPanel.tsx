import { useEffect, useState } from 'react'
import { useAppInfo } from '../appInfo'
import { RESOLUTION_TONE, type FirstRunInfo } from '../onboarding'
import { getFirstRun } from '../onboardingApi'
import { DEFAULT_CHOICES, consentPatch, type ConsentChoices } from '../consent'
import { getConsentChoices, saveConsentPatch } from '../consentApi'
import { useLabelingState } from '../labelingContext'
import { ConsentChoicesForm } from './ConsentChoicesForm'
import { DiagnosticsPanel } from './DiagnosticsPanel'
import { PatchNotesDialog } from './PatchNotesDialog'
import { TelemetryPanel } from './TelemetryPanel'

const TONE_CLASS = {
  ok: 'text-emerald-300',
  info: 'text-sky-300',
  warn: 'text-amber-300',
}

export function AboutPanel() {
  const info = useAppInfo()
  const [firstRun, setFirstRun] = useState<FirstRunInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [choices, setChoices] = useState<ConsentChoices>(DEFAULT_CHOICES)
  const [showPatchNotes, setShowPatchNotes] = useState(false)
  const { reload } = useLabelingState()

  useEffect(() => {
    getFirstRun()
      .then(setFirstRun)
      .catch((e: Error) => setError(e.message))
    getConsentChoices()
      .then(setChoices)
      .catch(() => {})
  }, [])

  const changeChoices = (next: ConsentChoices) => {
    setChoices(next)
    saveConsentPatch(consentPatch(next, ['update', 'labels', 'logs']))
      .then(reload)
      .catch((e: Error) => setError(e.message))
  }

  const reloadChoices = () => {
    getConsentChoices()
      .then(setChoices)
      .catch(() => {})
    reload()
  }

  const resolution = firstRun?.recording.resolution

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1">
        <h3 className="text-sm font-medium text-zinc-200">버전</h3>
        <p className="text-sm text-zinc-300">
          {info.version || '알 수 없음'}
          {info.mode === 'dev' && <span className="ml-2 text-xs text-zinc-500">(개발 모드)</span>}
        </p>
        <button
          type="button"
          className="w-fit text-xs text-sky-300 underline hover:text-sky-200"
          onClick={() => setShowPatchNotes(true)}
        >
          패치노트 보기
        </button>
      </section>
      {showPatchNotes && <PatchNotesDialog onClose={() => setShowPatchNotes(false)} />}

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-zinc-200">선택 기능</h3>
        <ConsentChoicesForm choices={choices} pending={['update', 'labels', 'logs']} onChange={changeChoices} />
      </section>

      <TelemetryPanel refreshKey={choices} onChanged={reloadChoices} />

      <section className="flex flex-col gap-1">
        <h3 className="text-sm font-medium text-zinc-200">녹화 해상도</h3>
        {error && <p className="text-xs text-rose-300">{error}</p>}
        {resolution && firstRun?.recording.session ? (
          <>
            <p className={`text-sm ${TONE_CLASS[RESOLUTION_TONE[resolution.kind]]}`}>{resolution.message}</p>
            <p className="text-xs text-zinc-500">
              가장 최근 녹화 기준 · 코덱 {firstRun.recording.session.codec ?? '알 수 없음'}
            </p>
          </>
        ) : (
          !error && <p className="text-xs text-zinc-500">확인할 녹화가 아직 없습니다.</p>
        )}
      </section>

      <DiagnosticsPanel />
    </div>
  )
}
