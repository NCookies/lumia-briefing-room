import { useEffect, useState } from 'react'
import { ClipBrowser, type ClipSource } from './components/ClipBrowser'
import { SettingsModal } from './components/SettingsModal'
import { getConfirmDelete, setConfirmDelete } from './exportApi'

const TABS: { id: ClipSource; label: string }[] = [
  { id: 'steam', label: '내 녹화' },
  { id: 'vod', label: '다시보기' },
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
  const [tab, setTab] = useState<ClipSource>(loadTab)
  const [showSettings, setShowSettings] = useState(false)
  const [confirmDelete, setConfirmDeleteState] = useState(true)

  useEffect(() => {
    getConfirmDelete()
      .then(setConfirmDeleteState)
      .catch(() => {})
  }, [])

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
      <header className="flex items-end justify-between border-b border-zinc-700 px-4 pt-3">
        <div className="flex items-end gap-6">
          <h1 className="pb-2 text-xl font-semibold">루미아 브리핑룸</h1>
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
        <button
          type="button"
          className="mb-2 rounded border border-zinc-600 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
          onClick={() => setShowSettings(true)}
        >
          ⚙ 옵션
        </button>
      </header>

      {TABS.map((t) => (
        <div key={t.id} className={tab === t.id ? 'flex flex-1 flex-col' : 'hidden'}>
          <ClipBrowser
            source={t.id}
            active={tab === t.id}
            confirmDelete={confirmDelete}
            onConfirmDeleteChange={changeConfirmDelete}
          />
        </div>
      ))}

      {showSettings && (
        <SettingsModal
          confirmDelete={confirmDelete}
          onConfirmDeleteChange={changeConfirmDelete}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  )
}
