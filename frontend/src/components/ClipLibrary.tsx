import { useCallback, useEffect, useMemo, useState } from 'react'
import { patchClip, splitClip, thumbnailUrl, trimClip } from '../api'
import type { DeleteMode } from '../deleteConfirm'
import { getExportDefault, pickFolder } from '../exportApi'
import {
  createFolder,
  deleteEntries,
  exportEntries,
  getLibrary,
  moveEntries,
  renameEntry,
  revealEntry,
  type LibraryClip,
  type LibraryFolder,
  type LibraryListing,
} from '../libraryApi'
import { canDropOn, dragItems, parentRel, selectionSummary, toggle } from '../library'
import { formatBytes } from '../retention'
import type { UserLabel } from '../types'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { ExportDialog } from './ExportDialog'
import { LibraryFolderPicker } from './LibraryFolderPicker'
import { FolderIcon, PencilIcon } from './LibraryIcons'
import { PlayerModal } from './PlayerModal'
import { PromptDialog } from './PromptDialog'

interface Props {
  active: boolean
  refreshTick: number
  confirmDelete: boolean
  onConfirmDeleteChange: (value: boolean) => void
  deleteMode: DeleteMode
  onDeleteModeChange: (value: DeleteMode) => void
}

type Prompt = { kind: 'newFolder' } | { kind: 'rename'; rel: string; initial: string; isFile: boolean }

const DRAG_TYPE = 'application/x-lumia-library-items'

function formatDuration(sec: number): string {
  if (!sec) return ''
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function stemOf(name: string): string {
  const cut = name.lastIndexOf('.')
  return cut > 0 ? name.slice(0, cut) : name
}

export function ClipLibrary({ active, refreshTick, confirmDelete, onConfirmDeleteChange, deleteMode, onDeleteModeChange }: Props) {
  const [path, setPath] = useState('')
  const [listing, setListing] = useState<LibraryListing | null>(null)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const [moveItems, setMoveItems] = useState<string[] | null>(null)
  const [deleteRequest, setDeleteRequest] = useState<{ label: string; items: string[] } | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [exportTarget, setExportTarget] = useState<LibraryClip | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)

  const load = useCallback(() => {
    getLibrary(path)
      .then((next) => {
        setListing(next)
        setError(null)
        const present = new Set([...next.folders.map((f) => f.rel), ...next.clips.map((c) => c.relPath)])
        setSelected((prev) => new Set([...prev].filter((k) => present.has(k))))
      })
      .catch((e: Error) => {
        setError(e.message)
        if (path !== '') setPath('')
      })
  }, [path])

  useEffect(() => {
    if (active) load()
  }, [active, load, refreshTick])

  const folders: LibraryFolder[] = listing?.folders ?? []
  const clips: LibraryClip[] = listing?.clips ?? []
  const folderKeys = useMemo(() => folders.map((f) => f.rel), [folders])
  const clipKeys = useMemo(() => clips.map((c) => c.relPath), [clips])
  const selectedItems = [...folderKeys, ...clipKeys].filter((k) => selected.has(k))
  const playingIndex = clips.findIndex((c) => c.id === playingId)

  const run = async (action: () => Promise<unknown>, done?: string) => {
    setError(null)
    setInfo(null)
    try {
      await action()
      if (done) setInfo(done)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      load()
    }
  }

  const open = (rel: string) => {
    setSelected(new Set())
    setPath(rel)
  }

  const requestDelete = (items: string[]) => {
    const names = items.map((i) => i.slice(i.lastIndexOf('/') + 1))
    const label = items.length === 1 ? `"${names[0]}" 을(를) 삭제합니다.` : `선택한 ${items.length}개 항목을 삭제합니다.`
    const note = '폴더는 안의 클립까지 함께 지워집니다. '
    if (!confirmDelete) {
      void run(() => deleteEntries(items))
      return
    }
    setDeleteRequest({ label: label + (items.some((i) => folderKeys.includes(i)) ? ` ${note}` : ''), items })
  }

  const confirmDeletion = async ({ mode, skipNext }: { mode: DeleteMode; skipNext: boolean }) => {
    const request = deleteRequest
    setDeleteRequest(null)
    if (skipNext) onConfirmDeleteChange(false)
    if (mode !== deleteMode) onDeleteModeChange(mode)
    if (request) await run(() => deleteEntries(request.items))
  }

  const exportSelected = async (items: string[]) => {
    await run(async () => {
      const dir = await pickFolder(await getExportDefault().catch(() => ''), '내보낼 폴더 선택')
      if (dir === null) return
      const saved = await exportEntries(items, dir)
      setInfo(`${saved.length}개를 내보냈습니다.`)
    })
  }

  const dropOn = async (event: React.DragEvent, dest: string) => {
    event.preventDefault()
    setDropTarget(null)
    let items: string[] = []
    try {
      items = JSON.parse(event.dataTransfer.getData(DRAG_TYPE)) as string[]
    } catch {
      return
    }
    if (!canDropOn(items, dest)) return
    await run(() => moveEntries(items, dest), `${items.length}개를 옮겼습니다.`)
  }

  const startDrag = (event: React.DragEvent, rel: string) => {
    event.dataTransfer.setData(DRAG_TYPE, JSON.stringify(dragItems(selected, rel)))
    event.dataTransfer.effectAllowed = 'move'
  }

  const droppable = (dest: string) => ({
    onDragOver: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes(DRAG_TYPE)) return
      e.preventDefault()
      setDropTarget(dest)
    },
    onDragLeave: () => setDropTarget((t) => (t === dest ? null : t)),
    onDrop: (e: React.DragEvent) => void dropOn(e, dest),
  })

  const canEditHere = listing !== null && !listing.virtualTop
  const summary = selectionSummary(folderKeys, clipKeys, selected)

  return (
    <div className="flex flex-1 flex-col gap-3 p-4" data-testid="clip-library">
      <div className="flex flex-wrap items-center gap-2">
        <nav className="flex flex-1 flex-wrap items-center gap-1 text-sm" aria-label="경로">
          {listing?.crumbs.map((c, i) => (
            <span key={c.rel} className="flex items-center gap-1">
              {i > 0 && <span className="text-zinc-600">/</span>}
              <button
                type="button"
                className={`rounded-md px-1.5 py-0.5 transition hover:bg-zinc-700 ${dropTarget === c.rel ? 'bg-sky-700' : ''} ${
                  i === listing.crumbs.length - 1 ? 'font-semibold text-zinc-100' : 'text-zinc-400'
                }`}
                onClick={() => open(c.rel)}
                {...(listing.virtualTop && c.rel === '' ? {} : droppable(c.rel))}
              >
                {c.name}
              </button>
            </span>
          ))}
        </nav>
        <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 text-sm transition hover:bg-zinc-700 disabled:opacity-40" disabled={!canEditHere} onClick={() => setPrompt({ kind: 'newFolder' })}>
          새 폴더
        </button>
        <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 text-sm transition hover:bg-zinc-700 disabled:opacity-40" disabled={!canEditHere} onClick={() => void run(() => revealEntry(path))}>
          탐색기에서 열기
        </button>
        <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 text-sm transition hover:bg-zinc-700" onClick={load}>
          새로고침
        </button>
      </div>

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-sky-600/60 bg-sky-500/10 px-3 py-2 text-sm" role="toolbar" aria-label="선택한 항목">
          <span className="text-sky-200">{summary} 선택</span>
          <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 transition hover:bg-zinc-700" onClick={() => setMoveItems(selectedItems)}>
            이동…
          </button>
          <button type="button" className="rounded-md border border-zinc-600/70 px-3 py-1 transition hover:bg-zinc-700" onClick={() => void exportSelected(selectedItems)}>
            내보내기…
          </button>
          <button type="button" className="rounded-md border border-rose-500/60 px-3 py-1 text-rose-200 transition hover:bg-rose-500/20" onClick={() => requestDelete(selectedItems)}>
            삭제
          </button>
          <button type="button" className="ml-auto text-zinc-400 hover:text-zinc-100" onClick={() => setSelected(new Set())}>
            선택 해제
          </button>
        </div>
      )}

      {error && <p className="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{error}</p>}
      {info && <p className="text-sm text-zinc-400">{info}</p>}

      {listing && folders.length === 0 && clips.length === 0 && (
        <p className="py-12 text-center text-sm text-zinc-500">
          {listing.virtualTop ? '클립 폴더를 찾을 수 없습니다.' : '이 폴더는 비어 있습니다. 탐색기에서 영상을 넣거나 위의 "새 폴더"로 나눠 보세요.'}
        </p>
      )}

      <div className="grid grid-cols-[repeat(auto-fill,minmax(14rem,1fr))] gap-3">
        {folders.map((f) => (
          <div
            key={f.rel}
            draggable={!(listing?.virtualTop ?? false)}
            onDragStart={(e) => startDrag(e, f.rel)}
            {...droppable(f.rel)}
            className={`group flex cursor-pointer items-center gap-3 rounded-md border px-3 py-3 ${
              dropTarget === f.rel ? 'border-sky-400 bg-sky-500/20' : selected.has(f.rel) ? 'border-sky-500 bg-zinc-800' : 'border-zinc-700 bg-zinc-800/60 transition hover:bg-zinc-800'
            }`}
            onClick={() => open(f.rel)}
          >
            {!listing?.virtualTop && (
              <input
                type="checkbox"
                aria-label={`${f.name} 선택`}
                checked={selected.has(f.rel)}
                onClick={(e) => e.stopPropagation()}
                onChange={() => setSelected((s) => toggle(s, f.rel))}
              />
            )}
            <FolderIcon className="h-8 w-8 shrink-0 text-amber-400" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium" title={f.name}>
                {f.name}
              </div>
              <div className="text-xs text-zinc-500">클립 {f.clipCount}개</div>
            </div>
            {!listing?.virtualTop && (
              <button
                type="button"
                className="rounded-md p-1 text-zinc-400 opacity-0 transition hover:bg-zinc-700 hover:text-zinc-100 group-hover:opacity-100 focus:opacity-100"
                aria-label={`${f.name} 이름 바꾸기`}
                onClick={(e) => {
                  e.stopPropagation()
                  setPrompt({ kind: 'rename', rel: f.rel, initial: f.name, isFile: false })
                }}
              >
                <PencilIcon />
              </button>
            )}
          </div>
        ))}

        {clips.map((c) => (
          <div
            key={c.relPath}
            draggable
            onDragStart={(e) => startDrag(e, c.relPath)}
            className={`group flex flex-col overflow-hidden rounded-md border ${selected.has(c.relPath) ? 'border-sky-500' : 'border-zinc-700'} bg-zinc-800/60`}
          >
            <div className="relative aspect-video cursor-pointer bg-zinc-900" onClick={() => setPlayingId(c.id)}>
              <img src={thumbnailUrl(c.id)} alt="" className="h-full w-full object-cover" loading="lazy" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
              <input
                type="checkbox"
                className="absolute left-2 top-2"
                aria-label={`${c.fileName} 선택`}
                checked={selected.has(c.relPath)}
                onClick={(e) => e.stopPropagation()}
                onChange={() => setSelected((s) => toggle(s, c.relPath))}
              />
              {c.durationSec > 0 && (
                <span className="absolute bottom-1 right-1 rounded-md bg-black/70 px-1.5 text-xs text-zinc-100">{formatDuration(c.durationSec)}</span>
              )}
              {c.unknownVideo && <span className="absolute right-1 top-1 rounded-md bg-zinc-700/90 px-1.5 text-xs text-zinc-200">앱 밖 영상</span>}
            </div>
            <div className="flex items-start gap-1 px-2 py-1.5">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm" title={c.title}>
                  {c.title}
                </div>
                <div className="truncate text-xs text-zinc-500" title={c.fileName}>
                  {c.fileName}
                  {c.sizeBytes ? ` · ${formatBytes(c.sizeBytes)}` : ''}
                </div>
              </div>
              <button
                type="button"
                className="rounded-md p-1 text-zinc-400 opacity-0 transition hover:bg-zinc-700 hover:text-zinc-100 group-hover:opacity-100 focus:opacity-100"
                aria-label={`${c.fileName} 파일 이름 바꾸기`}
                onClick={() => setPrompt({ kind: 'rename', rel: c.relPath, initial: stemOf(c.fileName), isFile: true })}
              >
                <PencilIcon />
              </button>
            </div>
          </div>
        ))}
      </div>

      {prompt && (
        <PromptDialog
          title={prompt.kind === 'newFolder' ? '새 폴더' : prompt.isFile ? '파일 이름 바꾸기' : '폴더 이름 바꾸기'}
          initial={prompt.kind === 'rename' ? prompt.initial : ''}
          confirmLabel={prompt.kind === 'newFolder' ? '만들기' : '바꾸기'}
          hint={prompt.kind === 'rename' && prompt.isFile ? '파일 이름만 바뀝니다. 클립 제목·태그·라벨은 그대로입니다.' : undefined}
          onCancel={() => setPrompt(null)}
          onSubmit={async (value) => {
            if (prompt.kind === 'newFolder') await createFolder(path, value)
            else await renameEntry(prompt.rel, value)
            setPrompt(null)
            load()
          }}
        />
      )}

      {moveItems && (
        <LibraryFolderPicker
          items={moveItems}
          startPath={parentRel(moveItems[0] ?? '')}
          onCancel={() => setMoveItems(null)}
          onPick={async (dest) => {
            await moveEntries(moveItems, dest)
            setMoveItems(null)
            setSelected(new Set())
            setInfo(`${moveItems.length}개를 옮겼습니다.`)
            load()
          }}
        />
      )}

      {deleteRequest && (
        <DeleteConfirmDialog
          label={deleteRequest.label}
          deleteMode={deleteMode}
          onCancel={() => setDeleteRequest(null)}
          onConfirm={confirmDeletion}
        />
      )}

      {playingIndex >= 0 && (
        <PlayerModal
          clips={clips}
          index={playingIndex}
          onIndexChange={(i) => setPlayingId(clips[i]?.id ?? null)}
          onLabel={(clip, label: UserLabel) => void run(() => patchClip(clip.id, { userLabel: label }))}
          onNote={(clip, note) => void run(() => patchClip(clip.id, { labelNote: note }))}
          onExport={(clip) => setExportTarget(clip as LibraryClip)}
          onRename={(clip, title) => void run(() => patchClip(clip.id, { title }))}
          onTrim={async (clip, ranges) => {
            if (ranges.length === 1) {
              await trimClip(clip.id, ranges[0].start, ranges[0].end)
            } else {
              const pieces = await splitClip(clip.id, ranges)
              setPlayingId(pieces[0]?.id ?? null)
            }
            load()
          }}
          paused={exportTarget !== null}
          onDelete={(clip) => {
            const next = clips[playingIndex + 1] ?? clips[playingIndex - 1]
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
