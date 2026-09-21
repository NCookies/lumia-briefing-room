import { useEffect, useState } from 'react'
import { getExportDefault, getNickname, setExportDefault, setNickname } from '../exportApi'
import { FolderPicker } from './FolderPicker'

interface Props {
  onClose: () => void
}

export function SettingsModal({ onClose }: Props) {
  const [nickname, setNicknameDraft] = useState('')
  const [nickStatus, setNickStatus] = useState<string | null>(null)
  const [dir, setDir] = useState('')
  const [ready, setReady] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    getExportDefault()
      .then(setDir)
      .catch((e: Error) => setStatus(e.message))
      .finally(() => setReady(true))
  }, [])

  useEffect(() => {
    getNickname()
      .then(setNicknameDraft)
      .catch((e: Error) => setNickStatus(e.message))
  }, [])

  const saveNickname = async () => {
    try {
      await setNickname(nickname.trim())
      setNickStatus('저장했다')
    } catch (e) {
      setNickStatus((e as Error).message)
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const save = async () => {
    try {
      await setExportDefault(dir)
      setStatus('저장했다')
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="flex w-full max-w-lg flex-col gap-4 rounded-lg border border-zinc-600 bg-zinc-800 p-4 text-zinc-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">옵션</h2>
          <button type="button" className="text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            닫기 ✕
          </button>
        </div>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-zinc-200">내 닉네임</h3>
          <p className="text-xs text-zinc-500">
            첫 경기 결과 화면에서 자동으로 읽어 채워진다. 잘못 읽었으면 여기서 고친다(한글·영문·일본어·한자 모두 가능).
          </p>
          <div className="flex items-center gap-2">
            <input
              className="flex-1 rounded border border-zinc-600 bg-zinc-900 px-2 py-1 text-sm"
              placeholder="아직 인식된 닉네임 없음"
              value={nickname}
              onChange={(e) => setNicknameDraft(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && saveNickname()}
            />
            <button
              type="button"
              className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500"
              onClick={saveNickname}
            >
              저장
            </button>
          </div>
          {nickStatus && <span className="text-xs text-zinc-400">{nickStatus}</span>}
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-zinc-200">영상 저장 기본 폴더</h3>
          <p className="text-xs text-zinc-500">
            저장 창을 열면 이 폴더에서 시작한다. 영상을 저장할 때마다 마지막에 고른 폴더로 자동 갱신된다.
          </p>
          {ready && <FolderPicker value={dir} onChange={setDir} />}
          <div className="flex items-center justify-end gap-3">
            {status && <span className="text-xs text-zinc-400">{status}</span>}
            <button
              type="button"
              className="rounded bg-sky-600 px-4 py-1.5 text-sm hover:bg-sky-500 disabled:opacity-40"
              disabled={dir === ''}
              onClick={save}
            >
              기본 폴더로 저장
            </button>
          </div>
        </section>
      </div>
    </div>
  )
}
