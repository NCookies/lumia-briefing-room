import { useCallback, useEffect, useState } from 'react'
import { pickFolder } from '../exportApi'
import {
  RECORDING_STATE_TEXT,
  RESOLUTION_TONE,
  SOURCE_TEXT,
  recordingState,
  type FirstRunInfo,
} from '../onboarding'
import { clearRecordingRoot, getFirstRun, setRecordingRoot } from '../onboardingApi'

const TONE_CLASS = {
  ok: 'text-emerald-300',
  info: 'text-sky-300',
  warn: 'text-amber-300',
}

export function RecordingRootSection() {
  const [info, setInfo] = useState<FirstRunInfo | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    getFirstRun()
      .then(setInfo)
      .catch((e: Error) => setStatus(e.message))
  }, [])

  useEffect(load, [load])

  const change = async () => {
    setBusy(true)
    setStatus(null)
    try {
      const picked = await pickFolder(info?.recording.root ?? '', '스팀 녹화 폴더 선택')
      if (picked === null) return
      await setRecordingRoot(picked)
      setStatus('바꿨습니다. 감시가 새 폴더로 다시 시작됩니다.')
      load()
    } catch (e) {
      setStatus((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const reset = async () => {
    setBusy(true)
    setStatus(null)
    try {
      await clearRecordingRoot()
      setStatus('스팀 설정에서 자동으로 찾도록 되돌렸습니다.')
      load()
    } catch (e) {
      setStatus((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const recording = info?.recording
  const state = recording ? recordingState(recording) : null
  const resolution = recording?.resolution

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-200">스팀 녹화 폴더</h3>
      <p className="text-xs text-zinc-500">
        스팀이 배경 녹화를 저장하는 폴더입니다. <span className="font-mono">bg_1049590_…</span> 같은 이름의
        폴더들이 들어 있는 <span className="font-mono">video</span> 폴더를 가리켜야 합니다. 기본 위치는{' '}
        <span className="font-mono">스팀 설치 폴더\userdata\숫자\gamerecordings\video</span> 입니다.
      </p>
      <div className="flex items-center gap-2">
        <div
          className="flex-1 truncate rounded bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200"
          title={recording?.root ?? ''}
        >
          {recording?.root ?? '찾지 못했습니다'}
        </div>
        <button
          type="button"
          className="rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40"
          disabled={busy || !info}
          onClick={() => void change()}
        >
          바꾸기
        </button>
      </div>
      {state && (
        <p className={`text-xs ${state === 'ok' ? 'text-emerald-300' : 'text-amber-300'}`}>
          {RECORDING_STATE_TEXT[state]}
          {recording?.source && <span className="ml-2 text-zinc-500">({SOURCE_TEXT[recording.source]})</span>}
        </p>
      )}
      {resolution && (
        <p className={`text-xs ${TONE_CLASS[RESOLUTION_TONE[resolution.kind]]}`}>{resolution.message}</p>
      )}
      {recording?.source === 'config' && (
        <div>
          <button
            type="button"
            className="text-xs text-zinc-400 underline hover:text-zinc-100 disabled:opacity-40"
            disabled={busy}
            onClick={() => void reset()}
          >
            직접 고른 폴더 대신 자동으로 찾기
          </button>
        </div>
      )}
      {status && <p className="text-xs text-zinc-400">{status}</p>}
    </section>
  )
}
