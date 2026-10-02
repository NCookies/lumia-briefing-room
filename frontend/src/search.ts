/** 검색 규칙 한 곳: 대소문자·공백 차이를 무시한 부분 일치(서버 `api/search.py` 와 같은 규칙). 세 탭이 같이 쓴다. */

export const SEARCH_DEBOUNCE_MS = 300

const LABEL_MAX = 30

export interface SearchMatch {
  where: string
  text: string
}

export function normalizeQuery(text: string): string {
  return text.replace(/\s+/g, '').toLowerCase()
}

export function isSearching(query: string): boolean {
  return normalizeQuery(query) !== ''
}

export function matchesQuery(text: string | null | undefined, query: string): boolean {
  const wanted = normalizeQuery(query)
  return wanted !== '' && text != null && normalizeQuery(text).includes(wanted)
}

/** 결과 행의 "어디서 찾았는지" 한 줄. */
export function matchLabel(match: SearchMatch | null | undefined): string {
  if (!match) return ''
  const flat = match.text.replace(/\s+/g, ' ').trim()
  const text = flat.length > LABEL_MAX ? `${flat.slice(0, LABEL_MAX)}…` : flat
  return `${match.where} '${text}'`
}
