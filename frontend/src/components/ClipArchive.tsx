import { useCallback, useEffect, useMemo, useState } from 'react'
import { patchClip, splitClip, thumbnailUrl, trimClip } from '../api'
import { cardHeadline, filterClips, sortedForCategory } from '../clipArchive'
import { createCategory, getCategories, moveClipsToCategory, type Category } from '../categoriesApi'
import type { DeleteMode } from '../deleteConfirm'
import { getExportDefault, pickFolder } from '../exportApi'
import { deleteEntries, exportEntries, getLibrary, renameEntry, revealEntry, type LibraryClip } from '../libraryApi'
import { formatBytes } from '../retention'
import type { UserLabel } from '../types'
import { ArchivePopup } from './ArchivePopup'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { ExportDialog } from './ExportDialog'
import { PlayerModal } from './PlayerModal'
import { PortraitRow } from './PortraitRow'
import { PromptDialog } from './PromptDialog'

interface Props {
  active: boolean
  refreshTick: number
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
  deleteMode: DeleteMode
  onDeleteModeChange: (value: DeleteMode) => void
}

type DeleteRequest = { label: string; items: string[] }

function formatDuration(sec: number): string {
  if (!sec) return ''
  return `${Math.floor(sec / 60)}:${Math.floor(sec % 60).toString().padStart(2, '0')}`
}

function formatWhen(iso: string | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** "클립" 탭: 보관한 클립을 카테고리(= `clips\` 아래 폴더)별로 본다. 왼쪽 카테고리 목록, 오른쪽 그 카테고리의 클립 카드(게임 정보 중심). */
export function ClipArchive({ active, refreshTick, confirmDelete, onConfirmDeleteChange, deleteMode, onDeleteModeChange }: Props) {
  const [enabled, setEnabled] = useState(true)
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [current, setCurrent] = useState<string | null>(null)
  const [clips, setClips] = useState<LibraryClip[]>([])
  const [query, setQuery] = useState('')
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [exportTarget, setExportTarget] = useState<LibraryClip | null>(null)
  const [deleteRequest, setDeleteRequest] = useState<DeleteRequest | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [moveAnchor, setMoveAnchor] = useState<DOMRect | null>(null)

  const loadCategories = useCallback(
    () =>
      getCategories()
        .then((list) => {
          setEnabled(list.enabled)
          setCategories(list.categories)
          setCurrent((now) => (now && list.categories.some((c) => c.name === now) ? now : (list.categories[0]?.name ?? null)))
        })
        .catch((e: Error) => setError(e.message)),
    [],
  )

  const loadClips = useCallback(() => {
    if (!current) return setClips([])
    getLibrary(current)
      .then((listing) => {
        setClips(listing.clips)
        setSelected((prev) => new Set([...prev].filter((k) => listing.clips.some((c) => c.relPath === k))))
      })
      .catch((e: Error) => setError(e.message))
  }, [current])

  const reload = useCallback(() => {
    void loadCategories()
    loadClips()
  }, [loadCategories, loadClips])

  useEffect(() => {
    if (active) void loadCategories()
  }, [active, loadCategories, refreshTick])

  useEffect(() => {
    if (active) loadClips()
  }, [active, loadClips, refreshTick])

  const shown = useMemo(() => filterClips(sortedForCategory(clips), query), [clips, query])
  const playingIndex = shown.findIndex((c) => c.id === playingId)
  const selectedClips = shown.filter((c) => selected.has(c.relPath))

  const run = async (action: () => Promise<unknown>, done?: string) => {
    setError(null)
    setInfo(null)
    try {
      await action()
      if (done) setInfo(done)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      reload()
    }
  }

  const requestDelete = (items: string[], label: string) => {
    if (!confirmDelete) void run(() => deleteEntries(items))
    else setDeleteRequest({ label, items })
  }

  const confirmDeletion = async ({ mode, skipNext }: { mode: DeleteMode; skipNext: boolean }) => {
    const request = deleteRequest
    setDeleteRequest(null)
    if (skipNext) onConfirmDeleteChange(false)
    if (mode !== deleteMode) onDeleteModeChange(mode)
    if (request) await run(() => deleteEntries(request.items))
  }

  const exportSelected = () =>
    run(async () => {
      const dir = await pickFolder(await getExportDefault().catch(() => ''), '내보낼 폴더 선택')
      if (dir === null) return
      const saved = await exportEntries(selectedClips.map((c) => c.relPath), dir)
      setInfo(`${saved.length}개를 내보냈습니다.`)
    })

  const leaveSelectMode = () => {
    setSelectMode(false)
    setSelected(new Set())
  }

  const isUser = (c: Category) => !c.auto && !c.default

  return (
    <div className="flex flex-1 gap-4 p-4" data-testid="clip-archive">
      <aside className="flex w-56 shrink-0 flex-col gap-1">
        <div className="flex items-center justify-between px-1 pb-1 text-xs text-zinc-400">
          <span>카테고리</span>
          <button type="button" className="rounded px-1.5 py-0.5 text-sky-300 hover:bg-zinc-700 disabled:opacity-40" disabled={!enabled} onClick={() => setCreating(true)}>
            + 새 카테고리
          </button>
        </div>
        {categories?.map((c) => (
          <div
            key={c.name}
            className={`group flex items-center gap-2 rounded border px-2 py-1.5 ${
              current === c.name ? 'border-sky-500 bg-zinc-800' : 'border-transparent hover:bg-zinc-800/70'
            } ${c.auto ? 'opacity-60' : ''}`}
          >
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => { setCurrent(c.name); leaveSelectMode() }}>
              <span className="h-8 w-12 shrink-0 overflow-hidden rounded bg-zinc-900">
                {c.thumbnailClipId && <img className="h-full w-full object-cover" src={thumbnailUrl(c.thumbnailClipId)} alt="" loading="lazy" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{c.name}</span>
                <span className="block text-xs text-zinc-500">{c.clipCount}개{c.auto ? ' · 자동' : ''}</span>
              </span>
            </button>
            {isUser(c) && (
              <span className="flex shrink-0 gap-0.5 opacity-0 group-hover:opacity-100">
                <button type="button" className="rounded px-1 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-100" aria-label={`${c.name} 이름 바꾸기`} onClick={() => setRenaming(c.name)}>
                  ✎
                </button>
                <button
                  type="button"
                  className="rounded px-1 text-xs text-rose-300 hover:bg-zinc-700"
                  aria-label={`${c.name} 삭제`}
                  onClick={() => requestDelete([c.name], `카테고리 "${c.name}" 과(와) 안의 클립 ${c.clipCount}개를 삭제합니다.`)}
                >
                  ✕
                </button>
              </span>
            )}
          </div>
        ))}
        {!enabled && categories && (
          <p className="px-1 text-xs text-zinc-500">이전 버전 폴더 구조에서는 카테고리를 쓸 수 없습니다. 옵션 → 저장 폴더에서 새 구조로 옮기면 쓸 수 있습니다.</p>
        )}
      </aside>

      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold">{current ?? ''}</h2>
          <input
            type="search"
            aria-label="클립 검색"
            placeholder="제목·메모 검색"
            className="w-48 rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm outline-none focus:border-sky-500"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <span className="ml-auto flex items-center gap-2">
            <button type="button" className={`rounded border px-3 py-1 text-sm ${selectMode ? 'border-sky-500 bg-sky-500/20' : 'border-zinc-600 hover:bg-zinc-700'}`} onClick={() => (selectMode ? leaveSelectMode() : setSelectMode(true))}>
              선택
            </button>
            <button type="button" className="rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700 disabled:opacity-40" disabled={!current || !enabled} onClick={() => void run(() => revealEntry(current!))}>
              탐색기에서 열기
            </button>
            <button type="button" className="rounded border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-700" onClick={reload}>
              새로고침
            </button>
          </span>
        </div>

        {selectMode && (
          <div className="flex flex-wrap items-center gap-2 rounded border border-sky-600/60 bg-sky-500/10 px-3 py-2 text-sm" role="toolbar" aria-label="선택한 클립">
            <span className="text-sky-200">{selectedClips.length}개 선택</span>
            <button type="button" className="rounded border border-zinc-600 px-3 py-1 hover:bg-zinc-700 disabled:opacity-40" disabled={selectedClips.length === 0 || !enabled} onClick={(e) => setMoveAnchor(e.currentTarget.getBoundingClientRect())}>
              카테고리 옮기기
            </button>
            <button type="button" className="rounded border border-zinc-600 px-3 py-1 hover:bg-zinc-700 disabled:opacity-40" disabled={selectedClips.length === 0} onClick={() => void exportSelected()}>
              내보내기…
            </button>
            <button
              type="button"
              className="rounded border border-rose-500/60 px-3 py-1 text-rose-200 hover:bg-rose-500/20 disabled:opacity-40"
              disabled={selectedClips.length === 0}
              onClick={() => requestDelete(selectedClips.map((c) => c.relPath), `선택한 클립 ${selectedClips.length}개를 삭제합니다.`)}
            >
              삭제
            </button>
            <button type="button" className="ml-auto text-zinc-400 hover:text-zinc-100" onClick={() => setSelected(new Set(shown.map((c) => c.relPath)))}>
              모두 선택
            </button>
          </div>
        )}

        {error && <p className="rounded border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{error}</p>}
        {info && <p className="text-sm text-zinc-400">{info}</p>}

        {categories && shown.length === 0 && (
          <p className="py-12 text-center text-sm text-zinc-500">
            {clips.length === 0
              ? '이 카테고리에는 보관한 클립이 없습니다. 게임의 풀영상 화면에서 후보의 "보관"을 눌러 보관하세요.'
              : '검색에 맞는 클립이 없습니다.'}
          </p>
        )}

        <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">
          {shown.map((c) => (
            <div key={c.relPath} className={`flex flex-col overflow-hidden rounded border bg-zinc-800/60 ${selected.has(c.relPath) ? 'border-sky-500' : 'border-zinc-700'}`}>
              <div className="relative aspect-video cursor-pointer bg-zinc-900" onClick={() => (selectMode ? setSelected((s) => { const n = new Set(s); if (n.has(c.relPath)) n.delete(c.relPath); else n.add(c.relPath); return n }) : setPlayingId(c.id))}>
                <img src={thumbnailUrl(c.id)} alt="" className="h-full w-full object-cover" loading="lazy" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
                {selectMode && <input type="checkbox" className="absolute left-2 top-2" aria-label={`${c.title} 선택`} checked={selected.has(c.relPath)} readOnly />}
                {c.durationSec > 0 && <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 text-xs text-zinc-100">{formatDuration(c.durationSec)}</span>}
                {c.unknownVideo && <span className="absolute right-1 top-1 rounded bg-zinc-700/90 px-1.5 text-xs text-zinc-200">앱 밖 영상</span>}
              </div>
              <div className="flex flex-col gap-1 px-2 py-2">
                {c.unknownVideo ? (
                  <div className="truncate text-sm" title={c.title}>{c.title}</div>
                ) : (
                  <>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-base font-bold">{cardHeadline(c)}</span>
                      <span className="text-xs text-zinc-500">{formatWhen(c.matchStartUtc)}</span>
                    </div>
                    <PortraitRow clip={c} />
                    <div className="truncate text-xs text-zinc-400" title={c.title}>{c.title}</div>
                    {c.memo && <div className="truncate text-xs text-amber-300/80" title={c.memo}>📝 메모 있음</div>}
                  </>
                )}
                {c.sizeBytes ? <div className="text-xs text-zinc-600">{formatBytes(c.sizeBytes)}</div> : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      {creating && (
        <PromptDialog
          title="새 카테고리"
          initial=""
          confirmLabel="만들기"
          onCancel={() => setCreating(false)}
          onSubmit={async (value) => {
            const name = await createCategory(value)
            setCreating(false)
            setCurrent(name)
            reload()
          }}
        />
      )}
      {renaming && (
        <PromptDialog
          title="카테고리 이름 바꾸기"
          initial={renaming}
          confirmLabel="바꾸기"
          hint="폴더 이름이 바뀝니다. 클립 제목·태그·라벨은 그대로입니다."
          onCancel={() => setRenaming(null)}
          onSubmit={async (value) => {
            const next = await renameEntry(renaming, value)
            setRenaming(null)
            if (current === renaming) setCurrent(next)
            reload()
          }}
        />
      )}
      {moveAnchor && current && (
        <ArchivePopup
          title="카테고리 옮기기"
          createLabel="만들고 옮기기"
          anchor={moveAnchor}
          current={current}
          archived={false}
          onPick={(category) => {
            setMoveAnchor(null)
            if (!category) return
            const ids = selectedClips.map((c) => c.id)
            leaveSelectMode()
            void run(() => moveClipsToCategory(ids, category), `${ids.length}개를 "${category}"로 옮겼습니다.`)
          }}
          onClose={() => setMoveAnchor(null)}
        />
      )}
      {deleteRequest && <DeleteConfirmDialog label={deleteRequest.label} deleteMode={deleteMode} onCancel={() => setDeleteRequest(null)} onConfirm={confirmDeletion} />}
      {playingIndex >= 0 && (
        <PlayerModal
          clips={shown}
          index={playingIndex}
          onIndexChange={(i) => setPlayingId(shown[i]?.id ?? null)}
          onLabel={(clip, label: UserLabel) => void run(() => patchClip(clip.id, { userLabel: label }))}
          onNote={(clip, note) => void run(() => patchClip(clip.id, { labelNote: note }))}
          onMemo={(clip, memo) => void run(() => patchClip(clip.id, { memo }))}
          onExport={(clip) => setExportTarget(clip as LibraryClip)}
          onRename={(clip, title) => void run(() => patchClip(clip.id, { title }))}
          onTrim={async (clip, ranges) => {
            if (ranges.length === 1) {
              await trimClip(clip.id, ranges[0].start, ranges[0].end)
            } else {
              const pieces = await splitClip(clip.id, ranges)
              setPlayingId(pieces[0]?.id ?? null)
            }
            reload()
          }}
          paused={exportTarget !== null}
          onDelete={(clip) => {
            const next = shown[playingIndex + 1] ?? shown[playingIndex - 1]
            const rel = (clip as LibraryClip).relPath
            if (!confirmDelete) {
              setPlayingId(next?.id ?? null)
              void run(() => deleteEntries([rel]))
            } else {
              setDeleteRequest({ label: `"${clip.title}" 클립을 삭제합니다.`, items: [rel] })
            }
          }}
          onClose={() => setPlayingId(null)}
        />
      )}
      {exportTarget && <ExportDialog clip={exportTarget} onClose={() => setExportTarget(null)} />}
    </div>
  )
}
