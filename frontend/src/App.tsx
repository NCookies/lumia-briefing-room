import { useEffect, useState } from 'react'
import { useAppInfo, versionLabel } from './appInfo'
import { BackfillDialog } from './components/BackfillDialog'
import { ClipBrowser, type ClipSource } from './components/ClipBrowser'
import { FirstRunScreen } from './components/FirstRunScreen'
import { SettingsModal } from './components/SettingsModal'
import { UpdateBanner } from './components/UpdateBanner'
import { UpdateBadge } from './components/UpdateBadge'
import { ActivityBar } from './components/ActivityBar'
import { activityLabels } from './activity'
import { useActivity } from './useActivity'
import { getConfirmDelete, setConfirmDelete } from './exportApi'
import { getFirstRun } from './onboardingApi'
import { isBackfillActive, progressPercent, type BackfillStatus } from './backfill'
import { getBackfillStatus } from './backfillApi'
import { browserCanPlayHevc } from './playback'
import { reportClientCapabilities } from './telemetryApi'

const TABS: { id: ClipSource; label: string }[] = [
  { id: 'steam', label: '스팀 녹화' },
  { id: 'vod', label: '영상 파일' },
]
const TAB_KEY = 'lumia.tab'

function loadTab(): ClipSource {
  try {
    return localStorage.getItem(TAB_KEY) === 'vod' ? 'vod' : 'steam'
  } catch {
    return 'steam'
  }
}

export default function App() {
  const version = versionLabel(useAppInfo())
  const [tab, setTab] = useState<ClipSource>(loadTab)
  const [showSettings, setShowSettings] = useState(false)
  const [settingsTab, setSettingsTab] = useState<'general' | 'vod' | 'about'>('general')
  const [browserKey, setBrowserKey] = useState(0)
  const [confirmDelete, setConfirmDeleteState] = useState(true)
  const [firstRun, setFirstRun] = useState(false)
  const [showBackfill, setShowBackfill] = useState(false)
  const [backfill, setBackfill] = useState<BackfillStatus>({ state: 'idle' })

  useEffect(() => {
    getFirstRun()
      .then((info) => setFirstRun(info.needed))
      .catch(() => {})
  }, [])

  useEffect(() => {
    reportClientCapabilities({ hevcPlayable: browserCanPlayHevc() !== '' }).catch(() => {})
  }, [])

  useEffect(() => {
    getConfirmDelete()
      .then(setConfirmDeleteState)
      .catch(() => {})
  }, [])

  useEffect(() => {
    getBackfillStatus()
      .then(setBackfill)
      .catch(() => {})
  }, [])

  const backfillRunning = isBackfillActive(backfill.state)
  const { tasks, refreshTick } = useActivity(backfillRunning)
  useEffect(() => {
    if (!backfillRunning) return
    const timer = window.setInterval(() => {
      getBackfillStatus()
        .then((next) => {
          setBackfill(next)
          if (!isBackfillActive(next.state)) setBrowserKey((k) => k + 1)
        })
        .catch(() => {})
    }, 1500)
    return () => window.clearInterval(timer)
  }, [backfillRunning])

  const changeConfirmDelete = (value: boolean) => {
    setConfirmDeleteState(value)
    setConfirmDelete(value).catch(() => {})
  }

  const selectTab = (next: ClipSource) => {
    setTab(next)
    try {
      localStorage.setItem(TAB_KEY, next)
    } catch {
      // 저장하지 못해도 화면은 동작한다
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-zinc-900 text-zinc-100">
      {firstRun && <FirstRunScreen onDone={() => setFirstRun(false)} />}
      <header className="flex items-end justify-between border-b border-zinc-700 px-4 pt-3">
        <div className="flex items-end gap-6">
          <h1 className="pb-2 text-xl font-semibold">
            루미아 브리핑룸
            {version && <span className="ml-2 text-xs font-normal text-zinc-500">{version}</span>}
            <UpdateBadge />
          </h1>
          <nav className="flex gap-1" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={`rounded-t border-x border-t px-4 py-2 text-sm ${
                  tab === t.id
                    ? 'border-zinc-600 bg-zinc-800 font-semibold text-zinc-100'
                    : 'border-transparent text-zinc-400 hover:text-zinc-200'
                }`}
                onClick={() => selectTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
        <div className="mb-2 flex items-center gap-2">
          <button
            type="button"
            className="rounded border border-zinc-600 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
            title="게임 로그에 남지 않은 과거 녹화에서 게임을 찾아 클립으로 만듭니다"
            onClick={() => setShowBackfill(true)}
          >
            {backfillRunning ? `과거 녹화 분석 중 ${progressPercent(backfill)}%` : '과거 녹화 분석'}
          </button>
          <button
            type="button"
            className="rounded border border-zinc-600 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
            onClick={() => {
              setSettingsTab('general')
              setShowSettings(true)
            }}
          >
            ⚙ 옵션
          </button>
        </div>
      </header>

      <ActivityBar
        labels={activityLabels(tasks, backfillRunning ? `과거 녹화 분석 중 ${progressPercent(backfill)}%` : null)}
      />

      <UpdateBanner />

      {TABS.map((t) => (
        <div key={`${t.id}-${browserKey}`} className={tab === t.id ? 'flex flex-1 flex-col' : 'hidden'}>
          <ClipBrowser
            source={t.id}
            active={tab === t.id}
            confirmDelete={confirmDelete}
            onConfirmDeleteChange={changeConfirmDelete}
            refreshTick={refreshTick}
            onBackfill={() => setShowBackfill(true)}
            backfillLabel={backfillRunning ? `과거 녹화 분석 중 ${progressPercent(backfill)}%` : '과거 녹화 분석'}
            onAddVodSources={() => {
              setSettingsTab('vod')
              setShowSettings(true)
            }}
          />
        </div>
      ))}

      {showBackfill && (
        <BackfillDialog
          status={backfill}
          onStatusChange={setBackfill}
          onClose={() => {
            setShowBackfill(false)
            if (backfill.state === 'done' || backfill.state === 'cancelled') setBrowserKey((k) => k + 1)
          }}
        />
      )}

      {showSettings && (
        <SettingsModal
          confirmDelete={confirmDelete}
          onConfirmDeleteChange={changeConfirmDelete}
          initialTab={settingsTab}
          onClose={() => setShowSettings(false)}
          onClipsDirChanged={() => setBrowserKey((k) => k + 1)}
        />
      )}
    </div>
  )
}
