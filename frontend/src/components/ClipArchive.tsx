import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { patchClip, splitClip, thumbnailUrl, trimClip } from '../api'
import { cardHeadline, flattenGroups, formatWhen, searchResultLabel, sortedForCategory, sortedGroups } from '../clipArchive'
import { idAfterRemoval } from '../clipViewer'
import { createCategory, getCategories, moveClipsToCategory, type Category } from '../categoriesApi'
import type { DeleteMode } from '../deleteConfirm'
import { getExportDefault, pickFolder } from '../exportApi'
import { deleteEntries, exportEntries, getLibrary, renameEntry, revealEntry, searchLibrary, type LibraryClip, type SearchedClip } from '../libraryApi'
import { formatBytes } from '../retention'
import { isSearching, matchLabel } from '../search'
import { useSearch } from '../useSearch'
import { ArchivePopup } from './ArchivePopup'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { ExportDialog } from './ExportDialog'
import { ClipViewer } from './ClipViewer'
import { PortraitRow } from './PortraitRow'
import { PromptDialog } from './PromptDialog'
import { SearchBox } from './SearchBox'

interface Props {
  active: boolean
  /** 주소가 정한 카테고리(없으면 맨 위 카테고리). */
  category: string | null
  onCategoryChange: (name: string | null, replace?: boolean) => void
  /** 주소가 정한 재생 화면의 클립(없으면 카테고리 목록). */
  clipId: string | null
  /** 재생 화면에서 보는 클립을 바꾼다(`null` 이면 카테고리 목록으로). 클립을 오가는 건 history 에 쌓지 않는다. */
  onClipChange: (category: string | null, clipId: string | null, replace?: boolean) => void
  /** `← 카테고리` 와 브라우저 뒤로 가기가 같은 동작. */
  onCloseClip: () => void
  /** 클립을 만든 게임의 풀영상 화면을 그 후보가 선택된 채로 연다. */
  onOpenGame: (tab: 'steam' | 'vod', gameKey: string, candidateId: string) => void
  /** 옵션의 저장 폴더 화면을 연다(옛 폴더 구조 사용자가 새 구조로 옮길 때). */
  onOpenStorage?: () => void
  refreshTick: number
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
  deleteMode: DeleteMode
  onDeleteModeChange: (value: DeleteMode) => void
}

type DeleteRequest = { label: string; items: string[]; after?: string | null }

function formatDuration(sec: number): string {
  if (!sec) return ''
  return `${Math.floor(sec / 60)}:${Math.floor(sec % 60).toString().padStart(2, '0')}`
}

/** "클립" 탭: 보관한 클립을 카테고리(= `clips\` 아래 폴더)별로 본다. 왼쪽 카테고리 목록, 오른쪽 그 카테고리의 클립 카드(게임 정보 중심). */
export function ClipArchive({ active, category, onCategoryChange, clipId, onClipChange, onCloseClip, onOpenGame, onOpenStorage, refreshTick, confirmDelete, onConfirmDeleteChange, deleteMode, onDeleteModeChange }: Props) {
  const [enabled, setEnabled] = useState(true)
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [clips, setClips] = useState<LibraryClip[]>([])
  const [results, setResults] = useState<{ name: string; clips: SearchedClip[] }[]>([])
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)
  const [exportTarget, setExportTarget] = useState<LibraryClip | null>(null)
  const [deleteRequest, setDeleteRequest] = useState<DeleteRequest | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [moveAnchor, setMoveAnchor] = useState<DOMRect | null>(null)
  const current = category ?? categories?.[0]?.name ?? null
  const wanted = useRef({ category, onCategoryChange })
  wanted.current = { category, onCategoryChange }

  const loadCategories = useCallback(
    () =>
      getCategories()
        .then((list) => {
          setEnabled(list.enabled)
          setCategories(list.categories)
          setError(null)
          const { category: want, onCategoryChange: change } = wanted.current
          if (want && !list.categories.some((c) => c.name === want)) change(list.categories[0]?.name ?? null, true)
        })
        .catch((e: Error) => setError(e.message)),
    [],
  )

  const loadClips = useCallback(() => {
    if (!current) return setClips([])
    getLibrary(current)
      .then((listing) => {
        setClips(listing.clips)
        setLoadedFor(current)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [current])

  const appliedRef = useRef('')
  const searchSeq = useRef(0)
  const loadSearch = useCallback(() => {
    const q = appliedRef.current
    const seq = ++searchSeq.current
    if (!q) return setResults([])
    searchLibrary(q)
      .then((found) => {
        if (seq !== searchSeq.current) return
        setResults(found.categories)
      })
      .catch((e: Error) => setError(e.message))
  }, [])
  const search = useSearch(active, loadSearch)
  appliedRef.current = search.applied
  const searching = search.searching && isSearching(search.query)

  const reload = useCallback(() => {
    void loadCategories()
    loadClips()
    loadSearch()
  }, [loadCategories, loadClips, loadSearch])

  useEffect(() => {
    if (active) void loadCategories()
  }, [active, loadCategories, refreshTick])

  useEffect(() => {
    if (active) loadClips()
  }, [active, loadClips, refreshTick])

  useEffect(() => {
    if (active) loadSearch()
  }, [active, loadSearch, refreshTick])

  const groups = useMemo(() => sortedGroups(results), [results])
  const shown = useMemo(() => (searching ? flattenGroups(groups) : sortedForCategory(clips)), [searching, groups, clips])
  const playing = clipId && loadedFor === current ? (clips.find((c) => c.id === clipId) ?? null) : null
  const viewerClips = useMemo(() => sortedForCategory(clips), [clips])

  useEffect(() => {
    if (active && clipId && loadedFor === current && !clips.some((c) => c.id === clipId)) onClipChange(current, null, true)
  }, [active, clipId, loadedFor, current, clips, onClipChange])
  useEffect(() => {
    const present = new Set(shown.map((c) => c.relPath))
    setSelected((prev) => (prev.size === 0 ? prev : new Set([...prev].filter((k) => present.has(k)))))
  }, [shown])
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
    if (request?.after !== undefined) onClipChange(current, request.after, true)
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

  const viewerDelete = (clip: LibraryClip) => {
    const next = idAfterRemoval(viewerClips.map((c) => c.id), clip.id)
    const remove = async () => {
      onClipChange(current, next, true)
      await run(() => deleteEntries([clip.relPath]))
    }
    if (!confirmDelete) void remove()
    else setDeleteRequest({ label: `"${clip.title}" 클립을 삭제합니다.`, items: [clip.relPath], after: next })
  }

  const card = (c: LibraryClip & { match?: SearchedClip['match'] }, inCategory: string | null) => (
    <div key={c.relPath} className={`flex flex-col overflow-hidden rounded-md border bg-zinc-800/60 ${selected.has(c.relPath) ? 'border-sky-500' : 'border-zinc-700'}`}>
      <div data-testid="clip-open" className="relative aspect-video cursor-pointer bg-zinc-900" onClick={() => (selectMode ? setSelected((s) => { const n = new Set(s); if (n.has(c.relPath)) n.delete(c.relPath); else n.add(c.relPath); return n }) : onClipChange(inCategory, c.id))}>
        <img src={thumbnailUrl(c.id)} alt="" className="h-full w-full object-cover" loading="lazy" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
        {selectMode && <input type="checkbox" className="absolute left-2 top-2" aria-label={`${c.title} 선택`} checked={selected.has(c.relPath)} readOnly />}
        {c.durationSec > 0 && <span className="absolute bottom-1 right-1 rounded-md bg-black/70 px-1.5 text-xs text-zinc-100">{formatDuration(c.durationSec)}</span>}
        {c.unknownVideo && <span className="absolute right-1 top-1 rounded-md bg-zinc-700/90 px-1.5 text-xs text-zinc-200">앱 밖 영상</span>}
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
        {c.match && <div className="truncate text-xs text-amber-300/90" title={c.match.text}>🔍 {matchLabel(c.match)}</div>}
        {c.sizeBytes ? <div className="text-xs text-zinc-600">{formatBytes(c.sizeBytes)}</div> : null}
      </div>
    </div>
  )

  return (
    <>
    {playing && current && (
      <ClipViewer
        clips={viewerClips}
        clip={playing}
        category={current}
        active={active}
        paused={deleteRequest !== null || exportTarget !== null}
        onBack={onCloseClip}
        onOpenGame={onOpenGame}
        onOpen={(id) => onClipChange(current, id, true)}
        onRename={(clip, title) => void run(() => patchClip(clip.id, { title }))}
        onMemo={(clip, memo) => void run(() => patchClip(clip.id, { memo }))}
        onMove={(clip, to) => {
          const next = idAfterRemoval(viewerClips.map((c) => c.id), clip.id)
          onClipChange(current, next, true)
          void run(() => moveClipsToCategory([clip.id], to), `"${clip.title}" 을(를) "${to}"로 옮겼습니다.`)
        }}
        onExport={setExportTarget}
        onReveal={(clip) => void run(() => revealEntry(clip.relPath))}
        onDelete={viewerDelete}
        onTrim={async (clip, ranges) => {
          if (ranges.length === 1) {
            await trimClip(clip.id, ranges[0].start, ranges[0].end)
          } else {
            const pieces = await splitClip(clip.id, ranges)
            onClipChange(current, pieces[0]?.id ?? null, true)
          }
          reload()
        }}
      />
    )}
    <div className={playing ? 'hidden' : 'flex flex-1 gap-4 p-4'} data-testid="clip-archive">
      <aside className="flex w-56 shrink-0 flex-col gap-1">
        <div className="flex items-center justify-between px-1 pb-1 text-xs text-zinc-400">
          <span>카테고리</span>
          <button type="button" className="rounded-md px-1.5 py-0.5 text-sky-300 transition hover:bg-zinc-700 disabled:opacity-40" disabled={!enabled} onClick={() => setCreating(true)}>
            + 새 카테고리
          </button>
        </div>
        {categories?.map((c) => (
          <div
            key={c.name}
            className={`group flex items-center gap-2 rounded-md border px-2 py-1.5 ${
              current === c.name && !searching ? 'border-sky-500 bg-zinc-800' : 'border-transparent transition hover:bg-zinc-800/70'
            } ${c.auto ? 'opacity-60' : ''}`}
          >
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => { search.setQuery(''); onCategoryChange(c.name); leaveSelectMode() }}>
              <span className="h-8 w-12 shrink-0 overflow-hidden rounded-md bg-zinc-900">
                {c.thumbnailClipId && <img className="h-full w-full object-cover" src={thumbnailUrl(c.thumbnailClipId)} alt="" loading="lazy" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{c.name}</span>
                <span className="block text-xs text-zinc-500">{c.clipCount}개{c.auto ? ' · 자동' : ''}</span>
              </span>
            </button>
            {isUser(c) && (
              <span className="flex shrink-0 gap-0.5 opacity-0 group-hover:opacity-100">
                <button type="button" className="rounded-md px-1 text-xs text-zinc-400 transition hover:bg-zinc-700 hover:text-zinc-100" aria-label={`${c.name} 이름 바꾸기`} onClick={() => setRenaming(c.name)}>
                  ✎
                </button>
                <button
                  type="button"
                  className="rounded-md px-1 text-xs text-rose-300 transition hover:bg-zinc-700"
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
          <h2 className="text-base font-semibold">{searching ? searchResultLabel(groups) : (current ?? '')}</h2>
          <SearchBox value={search.query} onChange={search.setQuery} label="클립 검색" placeholder="모든 카테고리에서 제목·메모·게임 검색" />
          <span className="ml-auto flex items-center gap-2">
            <button type="button" className={`rounded-md border px-3 py-1 text-sm ${selectMode ? 'border-sky-500 bg-sky-500/20' : 'border-zinc-600/70 transition hover:bg-zinc-700'}`} onClick={() => (selectMode ? leaveSelectMode() : setSelectMode(true))}>
              선택
            </button>
            <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 text-sm transition hover:bg-zinc-700 disabled:opacity-40" disabled={!current || !enabled} onClick={() => void run(() => revealEntry(current!))}>
              탐색기에서 열기
            </button>
            <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 text-sm transition hover:bg-zinc-700" onClick={reload}>
              새로고침
            </button>
          </span>
        </div>

        {selectMode && (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-sky-600/60 bg-sky-500/10 px-3 py-2 text-sm" role="toolbar" aria-label="선택한 클립">
            <span className="text-sky-200">{selectedClips.length}개 선택</span>
            <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 transition hover:bg-zinc-700 disabled:opacity-40" disabled={selectedClips.length === 0 || !enabled} onClick={(e) => setMoveAnchor(e.currentTarget.getBoundingClientRect())}>
              카테고리 옮기기
            </button>
            <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 transition hover:bg-zinc-700 disabled:opacity-40" disabled={selectedClips.length === 0} onClick={() => void exportSelected()}>
              내보내기…
            </button>
            <button
              type="button"
              className="rounded-md border border-rose-500/60 px-3 py-1 text-rose-200 transition hover:bg-rose-500/20 disabled:opacity-40"
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

        {error && <p className="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{error}</p>}
        {info && <p className="text-sm text-zinc-400">{info}</p>}

        {categories && !enabled && !searching && (
          <div className="mx-auto mt-10 flex max-w-xl flex-col items-center gap-3 rounded-lg border border-amber-500/50 bg-amber-500/10 px-5 py-5 text-center text-sm text-amber-100" data-testid="legacy-layout-notice">
            <p>이전 버전에서 쓰던 폴더 구조를 그대로 쓰고 있어서 이 탭에는 카테고리가 없습니다.</p>
            <p>클립은 사라지지 않았습니다. 스팀 녹화·영상 파일 탭에서 게임을 열면 "보관한 클립"으로 볼 수 있습니다.</p>
            <p>이 탭에서 카테고리별로 보려면 저장 폴더를 새 구조로 옮기세요. 게임 목록과 클립은 그대로 이어지고, 옮긴 직후에는 되돌릴 수도 있습니다.</p>
            {onOpenStorage && (
              <button type="button" className="rounded-md border border-amber-400/60 bg-amber-500/20 px-4 py-1.5 text-amber-50 transition hover:bg-amber-500/30" onClick={onOpenStorage}>
                저장 폴더 설정 열기
              </button>
            )}
          </div>
        )}

        {categories && enabled && shown.length === 0 && (
          <p className="py-12 text-center text-sm text-zinc-500">
            {searching
              ? '검색에 맞는 클립이 없습니다.'
              : '이 카테고리에는 보관한 클립이 없습니다. 게임의 풀영상 화면에서 후보의 "보관"을 눌러 보관하세요.'}
          </p>
        )}

        {searching ? (
          groups.map((g) => (
            <div key={g.name} className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold text-zinc-300">
                {g.name} <span className="text-xs font-normal text-zinc-500">{g.clips.length}개</span>
              </h3>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">{g.clips.map((c) => card(c, g.name))}</div>
            </div>
          ))
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">{shown.map((c) => card(c, current))}</div>
        )}
      </section>
    </div>

      {creating && (
        <PromptDialog
          title="새 카테고리"
          initial=""
          confirmLabel="만들기"
          onCancel={() => setCreating(false)}
          onSubmit={async (value) => {
            const name = await createCategory(value)
            setCreating(false)
            onCategoryChange(name)
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
            if (current === renaming) onCategoryChange(next, true)
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
      {exportTarget && <ExportDialog clip={exportTarget} onClose={() => setExportTarget(null)} />}
    </>
  )
}
