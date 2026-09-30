import { useEffect, useState } from 'react'
import { showTuningUi, useAppInfo, versionLabel } from './appInfo'
import { AdminPanel } from './components/AdminPanel'
import { BackfillDialog } from './components/BackfillDialog'
import type { ClipSource } from './components/ClipBrowser'
import { ClipLibrary } from './components/ClipLibrary'
import { FirstRunScreen } from './components/FirstRunScreen'
import { GameList } from './components/GameList'
import { SettingsModal } from './components/SettingsModal'
import { VodGameList } from './components/VodGameList'
import { UpdateBanner } from './components/UpdateBanner'
import { UpdateBadge } from './components/UpdateBadge'
import { ActivityBar } from './components/ActivityBar'
import { NoticeBanner } from './components/NoticeBanner'
import { WatchFailureBanner } from './components/WatchFailureBanner'
import { activityLabels } from './activity'
import { useActivity } from './useActivity'
import { LegacyTrashDialog } from './components/LegacyTrashDialog'
import { getConfirmDelete, getDeleteMode, setConfirmDelete, setDeleteMode } from './exportApi'
import type { DeleteMode } from './deleteConfirm'
import { getFirstRun } from './onboardingApi'
import { isBackfillActive, progressPercent, type BackfillStatus } from './backfill'
import { getBackfillStatus } from './backfillApi'
import { getLegacyTrashCount } from './legacyTrashApi'
import { browserCanPlayHevc } from './playback'
import { reportClientCapabilities } from './telemetryApi'

const ADMIN_TAB = { id: 'admin', label: '관리자' } as const
type Tab = ClipSource | 'library' | typeof ADMIN_TAB.id
const TABS: { id: Tab; label: string }[] = [
  { id: 'steam', label: '스팀 녹화' },
  { id: 'vod', label: '영상 파일' },
  { id: 'library', label: '클립' },
]
const TAB_KEY = 'lumia.tab'

function loadTab(): Tab {
  try {
    const saved = localStorage.getItem(TAB_KEY)
    return saved === 'vod' || saved === 'library' || saved === 'admin' ? saved : 'steam'
  } catch {
    return 'steam'
  }
}

export default function App() {
  const appInfo = useAppInfo()
  const version = versionLabel(appInfo)
  const isDev = showTuningUi(appInfo)
  const [savedTab, setTab] = useState<Tab>(loadTab)
  const tab: Tab = savedTab === 'admin' && !isDev ? 'steam' : savedTab
  const navTabs: { id: Tab; label: string }[] = isDev ? [...TABS, ADMIN_TAB] : TABS
  const [showSettings, setShowSettings] = useState(false)
  const [settingsTab, setSettingsTab] = useState<'general' | 'vod' | 'about'>('general')
  const [browserKey, setBrowserKey] = useState(0)
  const [confirmDelete, setConfirmDeleteState] = useState(true)
  const [deleteMode, setDeleteModeState] = useState<DeleteMode>('recycle')
  const [firstRun, setFirstRun] = useState(false)
  const [showBackfill, setShowBackfill] = useState(false)
  const [backfill, setBackfill] = useState<BackfillStatus>({ state: 'idle' })
  const [legacyTrashCount, setLegacyTrashCount] = useState(0)

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
    getDeleteMode()
      .then(setDeleteModeState)
      .catch(() => {})
  }, [])

  useEffect(() => {
    getBackfillStatus()
      .then(setBackfill)
      .catch(() => {})
  }, [])

  useEffect(() => {
    getLegacyTrashCount()
      .then(setLegacyTrashCount)
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

  const changeDeleteMode = (value: DeleteMode) => {
    setDeleteModeState(value)
    setDeleteMode(value).catch(() => {})
  }

  const selectTab = (next: Tab) => {
    setTab(next)
    try {
      localStorage.setItem(TAB_KEY, next)
    } catch {
      // 저장하지 못해도 화면은 동작한다
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-zinc-900 text-zinc-100">
      {firstRun && (
        <FirstRunScreen
          onDone={(backfillStarted) => {
            setFirstRun(false)
            if (backfillStarted) {
              getBackfillStatus()
                .then(setBackfill)
                .catch(() => {})
            }
          }}
        />
      )}
      <header className="flex items-end justify-between border-b border-zinc-700 px-4 pt-3">
        <div className="flex items-end gap-6">
          <h1 className="pb-2 text-xl font-semibold">
            루미아 브리핑룸
            {version && <span className="ml-2 text-xs font-normal text-zinc-500">{version}</span>}
            <UpdateBadge />
          </h1>
          <nav className="flex gap-1" role="tablist">
            {navTabs.map((t) => (
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
      <WatchFailureBanner />
      <NoticeBanner />

      <UpdateBanner />

      {isDev && (
        <div className={tab === 'admin' ? 'flex flex-1 flex-col' : 'hidden'}>
          <AdminPanel active={tab === 'admin'} />
        </div>
      )}

      <div className={tab === 'steam' ? 'flex flex-1 flex-col' : 'hidden'}>
        <GameList
          key={browserKey}
          active={tab === 'steam'}
          refreshTick={refreshTick}
          onBackfill={() => setShowBackfill(true)}
          backfillLabel={backfillRunning ? `과거 녹화 분석 중 ${progressPercent(backfill)}%` : '과거 녹화 분석'}
        />
      </div>

      <div key={`vod-${browserKey}`} className={tab === 'vod' ? 'flex flex-1 flex-col' : 'hidden'}>
        <VodGameList
          active={tab === 'vod'}
          refreshTick={refreshTick}
          confirmDelete={confirmDelete}
          onConfirmDeleteChange={changeConfirmDelete}
          deleteMode={deleteMode}
          onDeleteModeChange={changeDeleteMode}
          onAddVodSources={() => {
            setSettingsTab('vod')
            setShowSettings(true)
          }}
        />
      </div>

      <div className={tab === 'library' ? 'flex flex-1 flex-col' : 'hidden'}>
        <ClipLibrary
          key={`library-${browserKey}`}
          active={tab === 'library'}
          refreshTick={refreshTick}
          confirmDelete={confirmDelete}
          onConfirmDeleteChange={changeConfirmDelete}
          deleteMode={deleteMode}
          onDeleteModeChange={changeDeleteMode}
        />
      </div>

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
          deleteMode={deleteMode}
          onDeleteModeChange={changeDeleteMode}
          initialTab={settingsTab}
          onClose={() => setShowSettings(false)}
          onClipsDirChanged={() => setBrowserKey((k) => k + 1)}
        />
      )}

      {legacyTrashCount > 0 && (
        <LegacyTrashDialog
          count={legacyTrashCount}
          onDone={() => {
            setLegacyTrashCount(0)
            setBrowserKey((k) => k + 1)
          }}
          onLater={() => setLegacyTrashCount(0)}
        />
      )}
    </div>
  )
}
