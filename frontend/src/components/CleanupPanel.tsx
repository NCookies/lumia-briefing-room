import { useEffect, useState } from 'react'
import { useConfirm } from '../confirmContext'
import { getRetention, runCleanup, setRetention } from '../exportApi'
import { TAG_LABELS } from '../labels'
import { describeCleanup, parseLimit, type CleanupResult, type RetentionSettings } from '../retention'
import type { ClipTag } from '../types'

const PROTECTABLE: ClipTag[] = ['kill', 'assist', 'death', 'teammate_death', 'no_result']
const INPUT = 'w-24 rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm'

interface Draft {
  autoCleanEnabled: boolean
  deleteMode: 'trash' | 'permanent'
  trashDays: string
  ageOn: boolean
  maxAgeDays: string
  countOn: boolean
  maxCount: string
  gbOn: boolean
  maxTotalGb: string
  protectPinned: boolean
  protectTags: string[]
  keepGameRecords: boolean
}

const toDraft = (r: RetentionSettings): Draft => ({
  autoCleanEnabled: r.autoCleanEnabled,
  deleteMode: r.deleteMode,
  trashDays: String(r.trashDays),
  ageOn: r.maxAgeDays != null,
  maxAgeDays: r.maxAgeDays == null ? '' : String(r.maxAgeDays),
  countOn: r.maxCount != null,
  maxCount: r.maxCount == null ? '' : String(r.maxCount),
  gbOn: r.maxTotalGb != null,
  maxTotalGb: r.maxTotalGb == null ? '' : String(r.maxTotalGb),
  protectPinned: r.protectPinned,
  protectTags: r.protectTags,
  keepGameRecords: r.keepGameRecords ?? true,
})

const toSettings = (d: Draft): RetentionSettings => ({
  autoCleanEnabled: d.autoCleanEnabled,
  deleteMode: d.deleteMode,
  trashDays: Math.max(1, Math.round(parseLimit(d.trashDays) ?? 30)),
  maxAgeDays: d.ageOn ? parseLimit(d.maxAgeDays) : null,
  maxCount: d.countOn ? parseLimit(d.maxCount) : null,
  maxTotalGb: d.gbOn ? parseLimit(d.maxTotalGb) : null,
  protectPinned: d.protectPinned,
  protectTags: d.protectTags,
  keepGameRecords: d.keepGameRecords,
})

export function CleanupPanel() {
  const ask = useConfirm()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [preview, setPreview] = useState<CleanupResult | null>(null)

  useEffect(() => {
    getRetention()
      .then((r) => setDraft(toDraft(r)))
      .catch((e: Error) => setStatus(e.message))
  }, [])

  if (!draft) return <p className="text-sm text-zinc-400">{status ?? '불러오는 중입니다...'}</p>

  const on = draft.autoCleanEnabled

  const patch = (change: Partial<Draft>) => {
    setDraft({ ...draft, ...change })
    setPreview(null)
    setStatus(null)
  }

  const toggleTag = (tag: string) =>
    patch({
      protectTags: draft.protectTags.includes(tag)
        ? draft.protectTags.filter((t) => t !== tag)
        : [...draft.protectTags, tag],
    })

  const save = async () => {
    await setRetention(toSettings(draft))
    setStatus('저장했습니다')
  }

  const check = async () => {
    try {
      await save()
      setPreview(await runCleanup(true))
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  const runNow = async () => {
    const confirmed = await ask({ message: '지금 정리를 실행합니다. 계속하시겠습니까?', confirmLabel: '정리 실행', danger: true })
    if (!confirmed.ok) return
    try {
      await save()
      const result = await runCleanup(false)
      setPreview(null)
      setStatus(`정리를 실행했습니다: ${describeCleanup(result)}`)
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <label className="flex items-center gap-2 text-sm font-medium text-zinc-100">
          <input
            type="checkbox"
            checked={draft.autoCleanEnabled}
            onChange={(e) => patch({ autoCleanEnabled: e.target.checked })}
          />
          자동 정리 켜기
        </label>
        <p className="text-xs text-zinc-500">
          켜면 1시간마다 아래 기준을 넘은 클립을 자동으로 정리합니다. 끄면 클립과 휴지통이 자동으로 삭제되지 않습니다.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-zinc-200">정리 기준 (체크한 기준만 적용합니다)</h3>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            disabled={!on}
            checked={draft.ageOn}
            onChange={(e) => patch({ ageOn: e.target.checked })}
          />
          경기 후
          <input
            className={INPUT}
            inputMode="decimal"
            disabled={!on || !draft.ageOn}
            value={draft.maxAgeDays}
            onChange={(e) => patch({ maxAgeDays: e.target.value })}
          />
          일이 지난 클립
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            disabled={!on}
            checked={draft.countOn}
            onChange={(e) => patch({ countOn: e.target.checked })}
          />
          클립 수가
          <input
            className={INPUT}
            inputMode="numeric"
            disabled={!on || !draft.countOn}
            value={draft.maxCount}
            onChange={(e) => patch({ maxCount: e.target.value })}
          />
          개를 넘으면 오래된 클립부터 정리
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            disabled={!on}
            checked={draft.gbOn}
            onChange={(e) => patch({ gbOn: e.target.checked })}
          />
          총 용량이
          <input
            className={INPUT}
            inputMode="decimal"
            disabled={!on || !draft.gbOn}
            value={draft.maxTotalGb}
            onChange={(e) => patch({ maxTotalGb: e.target.value })}
          />
          GB를 넘으면 오래된 클립부터 정리
        </label>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-zinc-200">삭제 방식</h3>
        <select
          className="w-64 rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
          value={draft.deleteMode}
          onChange={(e) => patch({ deleteMode: e.target.value as Draft['deleteMode'] })}
        >
          <option value="trash">휴지통으로 이동 (복구 가능)</option>
          <option value="permanent">즉시 영구 삭제</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          휴지통에서
          <input
            className={INPUT}
            inputMode="numeric"
            value={draft.trashDays}
            onChange={(e) => patch({ trashDays: e.target.value })}
          />
          일이 지나면 영구 삭제
        </label>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium text-zinc-200">보호 (자동 정리에서 제외)</h3>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={draft.protectPinned}
            onChange={(e) => patch({ protectPinned: e.target.checked })}
          />
          고정한 클립
        </label>
        <div className="flex flex-wrap gap-1">
          {PROTECTABLE.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => toggleTag(tag)}
              className={`rounded border px-2 py-1 text-xs ${
                draft.protectTags.includes(tag)
                  ? 'border-sky-500 bg-sky-500/20 text-sky-200'
                  : 'border-zinc-600 text-zinc-400 hover:border-zinc-400'
              }`}
            >
              {TAG_LABELS[tag]}
            </button>
          ))}
        </div>
        <p className="text-xs text-zinc-500">선택한 태그가 붙은 클립은 정리하지 않습니다.</p>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={draft.keepGameRecords}
            onChange={(e) => patch({ keepGameRecords: e.target.checked })}
          />
          게임 기록은 유지
        </label>
        <p className="text-xs text-zinc-500">
          클립이 모두 삭제된 경기도 순위·전적·결과표를 목록에 &quot;클립 삭제됨&quot;으로 남깁니다(경기당 약 100~200KB). 끄면 그런 경기의 기록도 지웁니다.
        </p>
      </section>

      <section className="flex flex-wrap items-center gap-3 border-t border-zinc-700 pt-3">
        <button
          type="button"
          className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500"
          onClick={() => save().catch((e: Error) => setStatus(e.message))}
        >
          저장
        </button>
        <button
          type="button"
          className="rounded border border-zinc-600 px-3 py-1.5 text-sm hover:bg-zinc-700"
          onClick={check}
        >
          저장 후 정리 대상 확인
        </button>
        <button
          type="button"
          className="rounded border border-rose-500/60 px-3 py-1.5 text-sm text-rose-300 hover:bg-rose-500/20 disabled:opacity-40"
          disabled={!draft.autoCleanEnabled}
          onClick={runNow}
        >
          지금 정리 실행
        </button>
        {preview && <span className="text-sm text-zinc-300">{describeCleanup(preview)}</span>}
        {status && <span className="text-sm text-zinc-400">{status}</span>}
      </section>
    </div>
  )
}
