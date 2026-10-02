import { useCallback, useEffect, useState } from 'react'
import { getStorage } from '../storageApi'
import { StorageSection } from './StorageSection'

export function LegacyStorageGate({ onMoved }: { onMoved?: () => void }) {
  const [legacy, setLegacy] = useState(false)

  const check = useCallback(() => {
    getStorage()
      .then((info) => setLegacy(info.layout === 'legacy'))
      .catch(() => {})
  }, [])

  useEffect(check, [check])

  if (!legacy) return null

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-zinc-900" data-testid="legacy-storage-gate">
      <div className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-10">
        <h2 className="text-xl font-semibold">새 저장 폴더 구조로 옮겨야 합니다</h2>
        <p className="text-sm text-zinc-300">
          이전 버전에서 쓰던 클립·풀영상 폴더는 더 이상 그대로 쓸 수 없습니다. 아래에서 저장 폴더를 정하면 기존 영상이 그 폴더 안으로 옮겨지고, 그
          뒤에 앱을 쓸 수 있습니다. 같은 드라이브 안에서 옮기면 오래 걸리지 않습니다.
        </p>
        <StorageSection
          forced
          onChanged={() => {
            check()
            onMoved?.()
          }}
        />
      </div>
    </div>
  )
}
