import { useEffect, useState } from 'react'
import { showTuningUi, useAppInfo, versionLabel } from './appInfo'
import { AdminPanel } from './components/AdminPanel'
import { BackfillDialog } from './components/BackfillDialog'
import { ClipArchive } from './components/ClipArchive'
import { GuideDialog } from './components/GuideDialog'
import { FirstRunScreen } from './components/FirstRunScreen'
import { LegacyStorageGate } from './components/LegacyStorageGate'
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
import { probePlayback } from './playback'
import { reportClientCapabilities } from './telemetryApi'
import type { Route, TabId } from './route'
import { useRoute, type GameNav } from './useRoute'

const ADMIN_TAB = { id: 'admin', label: '관리자' } as const
type Tab = TabId
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
  const { route, inApp, memo, navigate, back } = useRoute(loadTab())
  const tab: Tab = route.tab === 'admin' && !isDev ? 'steam' : route.tab
  const navTabs: { id: Tab; label: string }[] = isDev ? [...TABS, ADMIN_TAB] : TABS
  const [showSettings, setShowSettings] = useState(false)
  const [showGuide, setShowGuide] = useState(false)
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
    probePlayback()
      .then(reportClientCapabilities)
      .catch(() => {})
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

  useEffect(() => {
    try {
      localStorage.setItem(TAB_KEY, route.tab)
    } catch {
      // 저장하지 못해도 화면은 동작한다
    }
  }, [route.tab])

  const routeOf = (id: Tab): Route => (route.tab === id ? route : (memo[id] ?? { tab: id }))
  const selectTab = (next: Tab) => {
    if (next !== tab) navigate(routeOf(next))
  }
  const gameNav = (id: 'steam' | 'vod'): GameNav => {
    const own = routeOf(id)
    const fromClip = own.cand !== undefined
    return {
      openKey: own.game ?? null,
      openCand: own.cand ?? null,
      backLabel: fromClip ? '← 클립' : undefined,
      userOpened: inApp,
      open: (key) => navigate({ tab: id, game: key }),
      close: () => (fromClip ? back(own, routeOf('library')) : back(own)),
      missing: () => navigate({ tab: id }, true),
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
      {!firstRun && <LegacyStorageGate key={browserKey} onMoved={() => setBrowserKey((k) => k + 1)} />}
      <header className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/60 px-4 py-2.5">
        <div className="flex items-center gap-6">
          <h1 className="text-xl font-semibold">
            루미아 브리핑룸
            {version && <span className="ml-2 text-xs font-normal text-zinc-500">{version}</span>}
            <UpdateBadge />
          </h1>
          <nav className="flex gap-1 rounded-lg border border-zinc-700/50 bg-zinc-800/60 p-1" role="tablist">
            {navTabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={`rounded-md px-4 py-1.5 text-sm transition active:scale-95 ${
                  tab === t.id
                    ? 'bg-zinc-600/70 font-semibold text-white shadow-sm'
                    : 'text-zinc-400 hover:bg-zinc-700/50 hover:text-zinc-100'
                }`}
                onClick={() => selectTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-zinc-700/60 bg-zinc-800/60 text-sm leading-none text-zinc-300 transition hover:bg-zinc-700 hover:text-white active:scale-95"
            aria-label="사용 안내"
            title="풀영상·후보·클립이 무엇인지 안내"
            onClick={() => setShowGuide(true)}
          >
            ?
          </button>
          <button
            type="button"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-zinc-700/60 bg-zinc-800/60 px-3 text-sm text-zinc-200 transition hover:bg-zinc-700 hover:text-white active:scale-95"
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
          nav={gameNav('steam')}
          refreshTick={refreshTick}
          onBackfill={() => setShowBackfill(true)}
          backfillLabel={backfillRunning ? `과거 녹화 분석 중 ${progressPercent(backfill)}%` : '과거 녹화 분석'}
          confirmDelete={confirmDelete}
          onConfirmDeleteChange={changeConfirmDelete}
          deleteMode={deleteMode}
          onDeleteModeChange={changeDeleteMode}
        />
      </div>

      <div key={`vod-${browserKey}`} className={tab === 'vod' ? 'flex flex-1 flex-col' : 'hidden'}>
        <VodGameList
          active={tab === 'vod'}
          nav={gameNav('vod')}
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
        <ClipArchive
          key={`library-${browserKey}`}
          active={tab === 'library'}
          category={routeOf('library').category ?? null}
          onCategoryChange={(name, replace) => navigate({ tab: 'library', category: name ?? undefined }, replace)}
          clipId={routeOf('library').clip ?? null}
          onClipChange={(name, id, replace) => navigate({ tab: 'library', category: name ?? undefined, clip: id ?? undefined }, replace)}
          onCloseClip={() => back(routeOf('library'))}
          onOpenGame={(tab, gameKey, candidateId) => navigate({ tab, game: gameKey, cand: candidateId })}
          onOpenStorage={() => {
            setSettingsTab('general')
            setShowSettings(true)
          }}
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

      {showGuide && <GuideDialog onClose={() => setShowGuide(false)} />}
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
