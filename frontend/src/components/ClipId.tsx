import { useTuningUi } from '../appInfo'

export function ClipId({ id }: { id: string }) {
  if (!useTuningUi()) return null
  return (
    <button
      type="button"
      title="클릭하면 ID를 복사합니다"
      className="w-fit font-mono text-[11px] text-zinc-500 hover:text-zinc-300"
      onClick={() => {
        try {
          void navigator.clipboard?.writeText(id)
        } catch {
          /* 복사 실패는 무시 */
        }
      }}
    >
      {id}
    </button>
  )
}
