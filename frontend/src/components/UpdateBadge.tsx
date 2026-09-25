import { useUpdate } from '../updateContext'

/** 제목 옆 버전 표시 곁에 붙는 "새 버전" 알림. 누르면 변경 내용 창이 열리고 거기서 업데이트할 수 있다. */
export function UpdateBadge() {
  const { release, openNotes } = useUpdate()
  if (!release) return null

  return (
    <button
      type="button"
      className="ml-2 rounded-full border border-sky-500/60 bg-sky-500/15 px-2 py-0.5 text-[11px] font-normal text-sky-300 hover:bg-sky-500/30"
      title="새 버전이 나왔습니다. 눌러서 변경 내용을 보고 업데이트할 수 있습니다"
      onClick={() => openNotes(release)}
    >
      ⬆ 새 버전 v{release.version}
    </button>
  )
}
