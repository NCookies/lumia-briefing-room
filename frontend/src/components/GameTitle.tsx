import { useState } from 'react'
import { TITLE_MAX, titleValue } from '../gameEdit'

interface Props {
  value: string | null | undefined
  onSave: (title: string | null) => void
}

/** 게임 행의 사용자 제목. 더블클릭하거나 연필을 눌러 그 자리에서 고친다(빈 값 = 제목 없음). */
export function GameTitle({ value, onSave }: Props) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')

  const start = () => {
    setText(value ?? '')
    setEditing(true)
  }
  const finish = (save: boolean) => {
    setEditing(false)
    if (!save) return
    const next = titleValue(text)
    if (next !== (value ?? null)) onSave(next)
  }

  if (editing) {
    return (
      <input
        autoFocus
        className="w-52 rounded-md border border-sky-500 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
        value={text}
        maxLength={TITLE_MAX}
        placeholder="제목"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => finish(true)}
        onKeyDown={(e) => {
          e.stopPropagation()
          if (e.key === 'Enter') finish(true)
          if (e.key === 'Escape') finish(false)
        }}
      />
    )
  }

  return (
    <div
      className="group/title flex max-w-xs items-center gap-1"
      onDoubleClick={(e) => {
        e.stopPropagation()
        start()
      }}
    >
      {value && (
        <span className="truncate text-sm font-semibold text-zinc-100" title={value}>
          {value}
        </span>
      )}
      <button
        type="button"
        aria-label="제목 편집"
        className="rounded-md px-1 text-sm text-zinc-500 transition hover:bg-zinc-700 hover:text-sky-300"
        title="제목 편집"
        onClick={(e) => {
          e.stopPropagation()
          start()
        }}
      >
        ✎
      </button>
    </div>
  )
}
