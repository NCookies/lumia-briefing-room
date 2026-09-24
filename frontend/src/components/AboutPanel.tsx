import { useEffect, useState } from 'react'
import { useAppInfo } from '../appInfo'
import { RESOLUTION_TONE, type FirstRunInfo } from '../onboarding'
import { DIAGNOSTICS_URL, getFirstRun } from '../onboardingApi'
import { DEFAULT_CHOICES, consentPatch, type ConsentChoices } from '../consent'
import { getConsentChoices, saveConsentPatch } from '../consentApi'
import { useLabelingState } from '../labelingContext'
import { ConsentChoicesForm } from './ConsentChoicesForm'

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

  const resolution = firstRun?.recording.resolution

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-1">
        <h3 className="text-sm font-medium text-zinc-200">버전</h3>
        <p className="text-sm text-zinc-300">
          {info.version || '알 수 없음'}
          {info.mode === 'dev' && <span className="ml-2 text-xs text-zinc-500">(개발 모드)</span>}
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-zinc-200">선택 기능</h3>
        <ConsentChoicesForm choices={choices} pending={['update', 'labels', 'logs']} onChange={changeChoices} />
      </section>

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

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-zinc-200">진단 정보 내보내기</h3>
        <p className="text-xs text-zinc-500">
          로그·버전·녹화 해상도와 코덱·설정을 zip 하나로 묶습니다. 닉네임과 경로 속 사용자 이름은 지워지고,
          영상이나 화면은 들어가지 않습니다. 자동으로 전송되지 않으니, 문제를 알릴 때 이 파일을 직접 첨부해 주세요.
        </p>
        <div>
          <a
            href={DIAGNOSTICS_URL}
            download
            className="inline-block rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500"
          >
            진단 정보 zip 받기
          </a>
        </div>
      </section>
    </div>
  )
}
