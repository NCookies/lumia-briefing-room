export type Edit =
  | { kind: 'range'; id: string; prev: [number, number]; next: [number, number] }
  | { kind: 'add'; id: string; range: [number, number] }
  | { kind: 'dismiss'; id: string }

/** 풀영상 화면의 실행 취소(Ctrl+Z)·다시 시도(Ctrl+Y) 기록. */
export interface History {
  undo: Edit[]
  redo: Edit[]
}

export const EMPTY_HISTORY: History = { undo: [], redo: [] }

/** 새 편집을 하면 다시 시도 기록은 버린다. */
export function pushEdit(h: History, edit: Edit): History {
  return { undo: [...h.undo, edit], redo: [] }
}

export function undoStep(h: History): { history: History; edit: Edit } | null {
  const edit = h.undo[h.undo.length - 1]
  if (!edit) return null
  return { edit, history: { undo: h.undo.slice(0, -1), redo: [...h.redo, edit] } }
}

export function redoStep(h: History): { history: History; edit: Edit } | null {
  const edit = h.redo[h.redo.length - 1]
  if (!edit) return null
  return { edit, history: { undo: [...h.undo, edit], redo: h.redo.slice(0, -1) } }
}

/** 지웠다 다시 추가한 구간은 새 id 를 받으므로, 그 구간을 가리키던 기록의 id 를 바꾼다. */
export function remapId(h: History, from: string, to: string): History {
  const map = (e: Edit): Edit => (e.id === from ? { ...e, id: to } : e)
  return { undo: h.undo.map(map), redo: h.redo.map(map) }
}
