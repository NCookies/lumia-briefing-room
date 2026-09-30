interface Props {
  checked: boolean
  count: number
  onChange: (value: boolean) => void
}

/** "삭제 예정만 보기" — 자동 정리 대상 게임만 보이게 한다. 대상이 없으면 켤 수 없다(켜져 있으면 끌 수는 있다). */
export function DueOnlyToggle({ checked, count, onChange }: Props) {
  return (
    <button
      type="button"
      className={`rounded border px-2 py-0.5 text-xs disabled:opacity-40 ${
        checked ? 'border-rose-500 bg-rose-500/20 text-rose-200' : 'border-zinc-600 hover:bg-zinc-700'
      }`}
      disabled={!checked && count === 0}
      title="자동 정리 때 풀영상이 지워질 게임만 봅니다"
      onClick={() => onChange(!checked)}
    >
      삭제 예정만 보기{count > 0 ? ` (${count})` : ''}
    </button>
  )
}
