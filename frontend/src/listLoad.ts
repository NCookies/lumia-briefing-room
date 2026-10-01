/** 영상 파일 목록(영상 묶음 + 게임)은 두 요청이 모두 와야 그린다. 하나만 와서 그리면 게임이 아직 없는 것처럼(게임 0개·"찾은 게임이 없습니다") 보인다. */
export function listLoading(o: { vodsLoaded: boolean; gamesLoaded: boolean; failed?: boolean }): boolean {
  return !o.failed && !(o.vodsLoaded && o.gamesLoaded)
}

export function gameCountLabel(o: { loaded: boolean; total: number; shown: number; dueOnly: boolean }): string {
  if (!o.loaded) return '게임 불러오는 중…'
  return o.dueOnly ? `게임 ${o.shown} / ${o.total}개` : `게임 ${o.total}개`
}

/** 풀영상 화면에서 목록으로 돌아온 순간(그 사이 보관·삭제한 값이 목록 행에 바로 반영되도록 조용히 다시 읽는다). */
export function returnedToList(prevOpen: string | null, open: string | null): boolean {
  return prevOpen !== null && open === null
}
