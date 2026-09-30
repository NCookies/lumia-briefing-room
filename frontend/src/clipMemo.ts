export const CLIP_MEMO_MAX = 5000

/** 입력을 상한에 맞춘다(서버 `normalize_memo` 와 같은 5,000자). */
export function clampMemo(text: string): string {
  return text.length > CLIP_MEMO_MAX ? text.slice(0, CLIP_MEMO_MAX) : text
}

/** 저장할 값: 공백뿐이면 null(= 지움). */
export function memoToSave(draft: string, current: string | null | undefined): string | null | undefined {
  const next = draft.trim() === '' ? null : draft.trim()
  return next === (current ?? null) ? undefined : next
}
