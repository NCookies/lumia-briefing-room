/** 화면 아래까지 남은 높이. 소수 좌표로 1px 넘치면 세로 스크롤이 생기므로 내림한다. */
export function fillHeight(o: { top: number; viewportHeight: number; bottomGap: number; min: number }): number {
  return Math.max(o.min, Math.floor(o.viewportHeight - o.top - o.bottomGap))
}
