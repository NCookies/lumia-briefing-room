import { useEffect, useState } from 'react'
import { getAutoStart, getExportDefault, getNickname, setAutoStart, setExportDefault, setNickname } from '../exportApi'
import { AboutPanel } from './AboutPanel'
import { CleanupPanel } from './CleanupPanel'
import { FolderPicker } from './FolderPicker'
import { VodSettingsPanel } from './VodSettingsPanel'

type Tab = 'general' | 'export' | 'vod' | 'cleanup' | 'about'

const TABS: { id: Tab; label: string }[] = [
  { id: 'general', label: '일반' },
  { id: 'export', label: '영상 저장' },
  { id: 'vod', label: '다시보기' },
  { id: 'cleanup', label: '자동 정리' },
  { id: 'about', label: '정보·진단' },
]

interface Props {
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
  onClose: () => void
}

function GeneralPanel({
  confirmDelete,
  onConfirmDeleteChange,
}: {
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
}) {
  const [nickname, setDraft] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [autoStart, setAutoStartState] = useState(true)
  const [autoStartError, setAutoStartError] = useState<string | null>(null)

  useEffect(() => {
    getNickname()
      .then(setDraft)
      .catch((e: Error) => setStatus(e.message))
    getAutoStart()
      .then(setAutoStartState)
      .catch(() => {})
  }, [])

  const changeAutoStart = async (value: boolean) => {
    const previous = autoStart
    setAutoStartState(value)
    setAutoStartError(null)
    try {
      await setAutoStart(value)
    } catch (e) {
      setAutoStartState(previous)
      setAutoStartError((e as Error).message)
    }
  }

  const save = async () => {
    try {
      await setNickname(nickname.trim())
      setStatus('저장했습니다')
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-6">
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-200">시작</h3>
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input type="checkbox" checked={autoStart} onChange={(e) => void changeAutoStart(e.target.checked)} />
        윈도우에 로그인할 때 자동으로 실행
      </label>
      <p className="text-xs text-zinc-500">
        켜 두면 로그인할 때 트레이에 조용히 떠서 경기가 끝날 때마다 클립을 만듭니다.
        꺼도 이미 만든 클립은 그대로 남고, 직접 실행하면 그때부터 다시 감시합니다.
      </p>
      {autoStartError && <p className="text-xs text-rose-300">{autoStartError}</p>}
    </section>
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-200">삭제</h3>
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input type="checkbox" checked={confirmDelete} onChange={(e) => onConfirmDeleteChange(e.target.checked)} />
        클립을 삭제할 때 확인 창 표시
      </label>
      <p className="text-xs text-zinc-500">
        끄면 삭제 버튼을 누르는 즉시 휴지통으로 이동합니다. 완전 삭제는 이 설정과 관계없이 항상 확인합니다.
      </p>
    </section>
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-200">내 닉네임</h3>
      <p className="text-xs text-zinc-500">
        첫 경기의 결과 화면에서 자동으로 인식해 채워집니다. 잘못 인식되었다면 여기서 수정하세요. (한글, 영문, 일본어, 한자를 모두 사용할 수 있습니다.)
      </p>
      <div className="flex items-center gap-2">
        <input
          className="flex-1 rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
          placeholder="아직 인식된 닉네임이 없습니다"
          value={nickname}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && save()}
        />
        <button type="button" className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500" onClick={save}>
          저장
        </button>
      </div>
      {status && <span className="text-xs text-zinc-400">{status}</span>}
    </section>
    </div>
  )
}

function ExportPanel() {
  const [dir, setDir] = useState('')
  const [ready, setReady] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    getExportDefault()
      .then(setDir)
      .catch((e: Error) => setStatus(e.message))
      .finally(() => setReady(true))
  }, [])

  const save = async () => {
    try {
      await setExportDefault(dir)
      setStatus('저장했습니다')
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-200">영상 저장 기본 폴더</h3>
      <p className="text-xs text-zinc-500">
        저장 창을 열면 이 폴더에서 시작합니다. 영상을 저장할 때마다 마지막으로 선택한 폴더로 자동 변경됩니다.
      </p>
      {ready && <FolderPicker value={dir} onChange={setDir} />}
      <div className="flex items-center justify-end gap-3">
        {status && <span className="text-xs text-zinc-400">{status}</span>}
        <button
          type="button"
          className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40"
          disabled={dir === ''}
          onClick={save}
        >
          기본 폴더로 지정
        </button>
      </div>
    </section>
  )
}

export function SettingsModal({ confirmDelete, onConfirmDeleteChange, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('general')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="flex h-[min(40rem,90vh)] w-full max-w-3xl flex-col rounded-lg border border-zinc-600 bg-zinc-800 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-3">
          <h2 className="text-lg font-medium">옵션</h2>
          <button type="button" className="text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            닫기 ✕
          </button>
        </div>
        <div className="flex min-h-0 flex-1">
          <nav className="flex w-36 shrink-0 flex-col gap-1 border-r border-zinc-700 p-2">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`rounded px-3 py-2 text-left text-sm ${
                  tab === t.id ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-700/50'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="min-w-0 flex-1 overflow-y-auto p-4">
            {tab === 'general' && (
              <GeneralPanel confirmDelete={confirmDelete} onConfirmDeleteChange={onConfirmDeleteChange} />
            )}
            {tab === 'export' && <ExportPanel />}
            {tab === 'vod' && <VodSettingsPanel />}
            {tab === 'cleanup' && <CleanupPanel />}
            {tab === 'about' && <AboutPanel />}
          </div>
        </div>
      </div>
    </div>
  )
}
