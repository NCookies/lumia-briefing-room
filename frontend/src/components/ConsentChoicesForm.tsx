import { isPending, type ConsentChoices } from '../consent'

const ITEMS: { key: keyof ConsentChoices; id: string; title: string; detail: string }[] = [
  {
    key: 'update',
    id: 'update',
    title: '새 버전이 나오면 알려 주기',
    detail: '끄면 새 버전 알림을 받지 못합니다. 버전은 화면 위쪽 제목 옆에서 확인할 수 있습니다.',
  },
  {
    key: 'labels',
    id: 'labels',
    title: '교전 / 그 외 라벨 보내기',
    detail:
      '직접 붙인 라벨과 그 근거(검출 신호·수치)만 보냅니다. 영상과 화면 이미지는 보내지 않습니다. 켜야 클립에 라벨을 붙이는 기능이 나타납니다.',
  },
  {
    key: 'logs',
    id: 'logs',
    title: '오류 로그와 환경 정보 보내기',
    detail: '앱 버전·OS·녹화 해상도·오류 기록만 보냅니다. 닉네임과 경로 속 사용자 이름은 지운 뒤 보냅니다.',
  },
]

export function ConsentChoicesForm({
  choices,
  pending,
  onChange,
}: {
  choices: ConsentChoices
  pending: string[]
  onChange: (next: ConsentChoices) => void
}) {
  return (
    <div className="flex flex-col gap-3">
      {ITEMS.filter((item) => isPending(pending, item.id)).map((item) => (
        <label key={item.key} className="flex cursor-pointer items-start gap-3 rounded border border-zinc-700 bg-zinc-800 p-3">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4"
            checked={choices[item.key]}
            onChange={(e) => onChange({ ...choices, [item.key]: e.target.checked })}
          />
          <span className="flex flex-col gap-0.5">
            <span className="text-sm font-medium">{item.title}</span>
            <span className="text-xs text-zinc-400">{item.detail}</span>
          </span>
        </label>
      ))}
    </div>
  )
}
