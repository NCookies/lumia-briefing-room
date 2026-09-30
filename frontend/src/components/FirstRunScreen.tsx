import { useCallback, useEffect, useState } from 'react'
import {
  RECORDING_STATE_TEXT,
  canOfferFirstBackfill,
  canStartFirstRun,
  diskFreeText,
  diskTone,
  RESOLUTION_TONE,
  SOURCE_TEXT,
  recordingState,
  type FirstRunInfo,
} from '../onboarding'
import { DEFAULT_CHOICES, consentPatch, isPending, type ConsentChoices } from '../consent'
import { saveConsentPatch } from '../consentApi'
import { startBackfill } from '../backfillApi'
import { completeFirstRun, getFirstRun, setRecordingRoot } from '../onboardingApi'
import { ConsentChoicesForm } from './ConsentChoicesForm'
import { StorageSection } from './StorageSection'
import { FolderPicker } from './FolderPicker'
import { GuideContent } from './GuideContent'
import { useLabelingState } from '../labelingContext'

const TONE_CLASS = {
  ok: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-200',
  info: 'border-sky-500/50 bg-sky-500/10 text-sky-200',
  warn: 'border-amber-500/60 bg-amber-500/10 text-amber-200',
}

function FolderEditor({
  title,
  hint,
  onSave,
  onCancel,
}: {
  title: string
  hint: string
  onSave: (path: string) => Promise<void>
  onCancel: () => void
}) {
  const [dir, setDir] = useState('')
  const [error, setError] = useState<string | null>(null)
  const pick = useCallback((path: string) => setDir(path), [])

  const save = async () => {
    try {
      await onSave(dir)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded border border-zinc-600 bg-zinc-900/60 p-3">
      <h4 className="text-sm font-medium">{title}</h4>
      <p className="text-xs text-zinc-400">{hint}</p>
      <FolderPicker value={dir} onChange={pick} />
      <div className="flex items-center justify-end gap-2">
        {error && <span className="text-xs text-rose-300">{error}</span>}
        <button type="button" className="rounded px-3 py-1 text-sm text-zinc-300 hover:bg-zinc-700" onClick={onCancel}>
          취소
        </button>
        <button
          type="button"
          className="rounded bg-sky-600 px-3 py-1 text-sm hover:bg-sky-500 disabled:opacity-40"
          disabled={dir === ''}
          onClick={save}
        >
          이 폴더로 지정
        </button>
      </div>
    </div>
  )
}

export function FirstRunScreen({ onDone }: { onDone: (backfillStarted: boolean) => void }) {
  const { reload } = useLabelingState()
  const [choices, setChoices] = useState<ConsentChoices>(DEFAULT_CHOICES)
  const [info, setInfo] = useState<FirstRunInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<'recording' | null>(null)
  const [analyzePast, setAnalyzePast] = useState(true)
  const [diskAcknowledged, setDiskAcknowledged] = useState(false)

  const load = useCallback(() => {
    getFirstRun()
      .then(setInfo)
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(load, [load])

  const finish = async () => {
    try {
      await saveConsentPatch(consentPatch(choices, info?.pendingItems ?? []))
      await completeFirstRun()
      let started = false
      if (info && analyzePast && canOfferFirstBackfill(info)) {
        started = await startBackfill().then(
          () => true,
          () => false,
        )
      }
      reload()
      onDone(started)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const saveRecording = async (path: string) => {
    await setRecordingRoot(path)
    setEditing(null)
    load()
  }

  if (!info) {
    return (
      <div className="fixed inset-0 z-[90] flex items-center justify-center bg-zinc-900 text-zinc-300">
        {error ?? '불러오는 중…'}
      </div>
    )
  }

  const showSetup = isPending(info.pendingItems, 'setup')
  const showConsent = ['update', 'labels', 'logs'].some((k) => isPending(info.pendingItems, k))
  const state = recordingState(info.recording)
  const resolution = info.recording.resolution

  return (
    <div className="fixed inset-0 z-[90] overflow-y-auto bg-zinc-900 p-4 text-zinc-100">
      <div className="mx-auto flex max-w-2xl flex-col gap-5 py-6">
        <header>
          <h2 className="text-2xl font-semibold">루미아 브리핑룸에 오신 것을 환영합니다</h2>
          <p className="mt-1 text-sm text-zinc-400">
            스팀이 저장한 배경 녹화에서 교전 장면을 자동으로 잘라 줍니다. 시작하기 전에 몇 가지만 확인하세요.
            게임 프로세스는 건드리지 않고, 스팀이 저장한 파일만 읽습니다.
          </p>
        </header>

        {showSetup && (
          <>
        <section className="flex flex-col gap-2">
          <h3 className="text-base font-medium">1. 스팀 녹화 폴더</h3>
          <div
            className={`rounded border px-3 py-2 text-sm ${
              state === 'ok' ? TONE_CLASS.ok : state === 'no-session' ? TONE_CLASS.info : TONE_CLASS.warn
            }`}
          >
            <p>{RECORDING_STATE_TEXT[state]}</p>
            {info.recording.root && (
              <p className="mt-1 break-all font-mono text-xs">
                {info.recording.root}
                {info.recording.source && (
                  <span className="ml-2 font-sans text-zinc-400">({SOURCE_TEXT[info.recording.source]})</span>
                )}
              </p>
            )}
          </div>
          {state !== 'ok' && (
            <p className="text-xs text-zinc-400">
              스팀 → 설정 → 게임 녹화에서 <b>배경 녹화</b>를 켜고 녹화 폴더를 정해 두세요. 폴더 안에{' '}
              <span className="font-mono">bg_1049590_…</span> 같은 이름의 폴더들이 생기는 곳이 이 앱이 찾는
              폴더입니다. 스팀에서 녹화 폴더를 바꾸지 않았다면 기본 위치는{' '}
              <span className="font-mono">스팀 설치 폴더\userdata\숫자\gamerecordings\video</span> 입니다. 폴더를
              지정하면 앱이 곧바로 감시를 시작합니다.
            </p>
          )}
          {editing === 'recording' ? (
            <FolderEditor
              title="스팀 녹화 폴더 고르기"
              hint="bg_로 시작하는 폴더들이 들어 있는 폴더(보통 이름이 video)를 고르세요."
              onSave={saveRecording}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <div>
              <button
                type="button"
                className="rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700"
                onClick={() => setEditing('recording')}
              >
                녹화 폴더 직접 고르기
              </button>
            </div>
          )}
          {!info.ffmpegFound && (
            <p className="rounded border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
              ffmpeg를 찾지 못했습니다. 클립을 만들 수 없습니다.
            </p>
          )}
        </section>

        <StorageSection variant="firstRun" onChanged={load} />

        <section className="flex flex-col gap-2" data-testid="disk-notice">
          <h3 className="text-base font-medium">저장 공간</h3>
          <div
            className={`rounded border-2 px-4 py-3 ${
              diskTone(info.disk) === 'warn'
                ? 'border-rose-500 bg-rose-500/10 text-rose-100'
                : 'border-amber-500/70 bg-amber-500/10 text-amber-100'
            }`}
          >
            <p className="text-lg font-semibold">
              게임 하나에 2~5GB 가 저장됩니다. {info.disk.recommendedGb[0]}~{info.disk.recommendedGb[1]}GB 여유 공간을
              확보하고 사용하세요.
            </p>
            <p className={`mt-2 text-sm ${diskTone(info.disk) === 'warn' ? 'font-semibold text-rose-300' : ''}`}>
              {diskFreeText(info.disk)}
              {diskTone(info.disk) === 'warn' && ` (권장 ${info.disk.recommendedGb[0]}GB 미만)`}
            </p>
            <p className="mt-1 text-xs text-zinc-400">
              게임 전체 영상을 저장하기 때문입니다. 오래된 영상은 옵션의 자동 정리 한도(기본 40GB)로 지울 수 있습니다.
            </p>
          </div>
          <label className="flex cursor-pointer items-center gap-2 rounded border border-zinc-600 bg-zinc-900/60 p-3 text-sm">
            <input type="checkbox" checked={diskAcknowledged} onChange={(e) => setDiskAcknowledged(e.target.checked)} />
            <b>확인했습니다</b>
          </label>
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-base font-medium">2. 녹화 해상도</h3>
          {resolution && info.recording.session ? (
            <div className={`rounded border px-3 py-2 text-sm ${TONE_CLASS[RESOLUTION_TONE[resolution.kind]]}`}>
              <p>{resolution.message}</p>
              <p className="mt-1 text-xs text-zinc-400">
                가장 최근 녹화 기준 · 코덱 {info.recording.session.codec ?? '알 수 없음'}
              </p>
            </div>
          ) : (
            <p className="rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-300">
              아직 확인할 녹화가 없습니다. 첫 게임을 녹화한 뒤 옵션 → 정보·진단에서 확인할 수 있습니다.
            </p>
          )}
          <p className="text-xs text-zinc-500">
            지원 해상도: 2560x1440 · 1920x1080(측정), 그 밖의 16:9 화면은 비율에 맞춰 조정해 대응합니다. 확인 결과와 관계없이 시작할 수 있습니다.
          </p>
        </section>

        {canOfferFirstBackfill(info) && (
          <section className="flex flex-col gap-2">
            <h3 className="text-base font-medium">3. 과거 녹화 분석</h3>
            <label className="flex cursor-pointer items-start gap-2 rounded border border-zinc-600 bg-zinc-900/60 p-3 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={analyzePast}
                onChange={(e) => setAnalyzePast(e.target.checked)}
              />
              <span>
                <b>시작하면서 스팀에 남아 있는 과거 녹화도 분석하기</b>
                <span className="mt-1 block text-xs text-zinc-400">
                  이미 녹화돼 있는 게임에서 교전 클립을 미리 만들어 둡니다. 게임 하나에 2~6분쯤 걸리고, 그동안 화면
                  위쪽에 진행 상황이 표시됩니다. 언제든 취소할 수 있고, 나중에 위쪽의 &quot;과거 녹화 분석&quot; 버튼으로 해도
                  됩니다.
                </span>
              </span>
            </label>
          </section>
        )}

          </>
        )}

        {showConsent && (
          <section className="flex flex-col gap-2">
            <h3 className="text-base font-medium">{showSetup ? `${canOfferFirstBackfill(info) ? 4 : 3}. ` : ''}선택 기능</h3>
            <p className="text-xs text-zinc-400">
              모두 처음에는 꺼져 있고, 켜야만 동작합니다. 옵션 → 정보·진단에서 언제든 바꿀 수 있습니다. 이 버전에서는
              아직 네트워크를 쓰는 기능이 동작하지 않으며, 켜 둔 선택은 해당 기능이 추가되는 버전부터 적용됩니다.
            </p>
            <ConsentChoicesForm choices={choices} pending={info.pendingItems} onChange={setChoices} />
          </section>
        )}

        <details className="rounded border border-zinc-700 p-3">
          <summary className="cursor-pointer text-sm text-zinc-300">사용 방법 미리 보기 (건너뛰어도 됩니다)</summary>
          <div className="mt-3">
            <GuideContent />
          </div>
        </details>

        {error && <p className="text-sm text-rose-300">{error}</p>}
        <div className="flex justify-end">
          <button
            type="button"
            className="rounded bg-sky-600 px-6 py-2 text-sm font-medium hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!canStartFirstRun(info.pendingItems, diskAcknowledged)}
            onClick={finish}
          >
            시작하기
          </button>
        </div>
        <p className="text-xs text-zinc-500">
          이 창을 그냥 닫으면 다음에 실행할 때 다시 나타나며, 그때까지 선택 기능은 모두 꺼진 채로 있습니다. 이 앱은 지금 어떤 데이터도 외부로 보내지 않습니다.
        </p>
      </div>
    </div>
  )
}
