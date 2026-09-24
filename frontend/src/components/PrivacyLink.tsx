import { useState } from 'react'
import { PrivacyDialog } from './PrivacyDialog'

export function PrivacyLink() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <p className="text-xs text-zinc-500">
        보내는 항목, 보관 기간, 삭제 방법은{' '}
        <button type="button" className="text-sky-300 underline hover:text-sky-200" onClick={() => setOpen(true)}>
          개인정보 처리 안내
        </button>
        에서 확인할 수 있습니다. 켜지 않아도 기능 제한은 없습니다.
      </p>
      {open && <PrivacyDialog onClose={() => setOpen(false)} />}
    </>
  )
}
