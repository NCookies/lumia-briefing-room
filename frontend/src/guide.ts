export type GuideTabId = 'start' | 'viewer' | 'clips' | 'folders' | 'shortcuts'

export type GuideBlock =
  | { kind: 'steps'; items: string[] }
  | { kind: 'notes'; title: string; items: string[] }
  | { kind: 'paras'; title?: string; lines: string[] }
  | { kind: 'callout'; title: string; lines: string[] }
  | { kind: 'tree' }
  | { kind: 'shortcuts' }

export interface GuideTab {
  id: GuideTabId
  label: string
  blocks: GuideBlock[]
}

/** 칩이 따라 그리는 실제 화면 버튼의 모양. 모양은 `GuideChip` 이 정한다. */
export type ChipKind = 'primary' | 'archived' | 'secondary' | 'danger' | 'pin' | 'category'

/** 가이드 문장 속 `용어` 중 칩으로 그리는 것. 화면의 버튼·배지 이름과 같아야 한다. */
export const GUIDE_CHIPS: Record<string, ChipKind> = {
  보관: 'primary',
  보관됨: 'archived',
  '다시 저장': 'primary',
  삭제: 'secondary',
  '구간 삭제': 'secondary',
  메모: 'secondary',
  '클립 삭제': 'danger',
  고정: 'pin',
  '자동 보관': 'category',
  보관함: 'category',
}

export type GuideSegment = { type: 'text' | 'chip' | 'kbd'; value: string }

/** 가이드 문장을 글·칩(`백틱`)·키(`{중괄호}`)로 쪼갠다. */
export function parseGuideText(text: string): GuideSegment[] {
  const segments: GuideSegment[] = []
  const pattern = /`([^`]+)`|\{([^}]+)\}/g
  let last = 0
  for (const m of text.matchAll(pattern)) {
    if (m.index > last) segments.push({ type: 'text', value: text.slice(last, m.index) })
    segments.push(m[1] !== undefined ? { type: 'chip', value: m[1] } : { type: 'kbd', value: m[2] })
    last = m.index + m[0].length
  }
  if (last < text.length) segments.push({ type: 'text', value: text.slice(last) })
  return segments
}

export const SSD_TITLE = '스팀 녹화 폴더는 SSD 를 권장합니다'

export const SSD_LINES = [
  '스팀 설정 → 게임 녹화에서 녹화 폴더를 SSD 로 두세요. 녹화 폴더가 HDD 이고 클립·풀영상도 같은 HDD 이면, 게임 중 풀영상을 만드는 동안 스팀 녹화가 밀려 오류로 멈출 수 있습니다.',
  '멈추면 게임을 다시 켜야 녹화가 재개됩니다. 클립·풀영상은 녹화와 다른 디스크(큰 HDD 도 됩니다)에 두세요.',
]

/** `(?)` 도움말에 붙이는 한 덩어리 문구. */
export const SSD_ADVICE = `${SSD_TITLE}. ${SSD_LINES.join(' ')}`

/** 처음 쓰는 사람을 위한 안내. 용어는 "보관"(후보를 클립으로 남김)과 "저장"(보관한 클립에 고친 범위 반영)을 섞지 않는다. */
export const GUIDE_TABS: GuideTab[] = [
  {
    id: 'start',
    label: '시작하기',
    blocks: [
      {
        kind: 'paras',
        lines: ['게임이 끝나면 앱이 게임 전체 영상을 만들고 교전 후보를 찾아 줍니다. 마음에 드는 장면만 골라 남기면 됩니다.'],
      },
      {
        kind: 'steps',
        items: [
          '게임을 합니다. 스팀 백그라운드 녹화가 켜져 있으면 끝난 게임이 "스팀 녹화" 탭에 생깁니다.',
          '게임을 눌러 풀영상 화면을 엽니다. 재생 막대의 노란 구간이 교전 후보이니 양 끝 손잡이로 다듬고, 아닌 것은 `삭제`합니다.',
          '남기고 싶은 후보는 `보관`을 눌러 카테고리를 고릅니다. 그 구간이 클립(영상 파일)이 됩니다.',
          '"클립" 탭에서 카테고리별로 모아 봅니다.',
        ],
      },
      {
        kind: 'notes',
        title: '알아 두면 좋은 것',
        items: [
          '풀영상은 용량 한도(기본 40GB)를 넘으면 오래된 것부터 자동으로 지워지며, `고정`한 게임과 보관한 클립은 지워지지 않습니다.',
          '보관한 클립의 범위를 고쳤다면 `다시 저장`을 눌러야 새 범위가 반영됩니다.',
          '옵션 → 일반 → 클립 보관 방식에서 분석이 끝날 때 후보를 자동으로 클립으로 만들게 할 수 있습니다. 자세한 내용은 "클립" 탭에 있습니다.',
        ],
      },
    ],
  },
  {
    id: 'viewer',
    label: '풀영상 화면',
    blocks: [
      {
        kind: 'paras',
        title: '풀영상',
        lines: ['게임 하나의 전체 영상입니다(캐릭터 선택 화면부터 결과 화면까지). 앱이 자동으로 만들고, 게임 줄의 `고정`을 누르면 자동 정리에서 제외됩니다.'],
      },
      {
        kind: 'paras',
        title: '교전 후보',
        lines: [
          '재생 막대의 노란 구간입니다. 앱이 찾은 "교전일 것 같은 곳"이라 완벽하지는 않습니다.',
          '후보를 선택하면 양 끝에 손잡이가 생기니 끌어서 범위를 바꿉니다. {N} 키나 "여기서 구간 추가" 버튼으로 직접 구간을 더할 수도 있습니다.',
          '막대 아래 눈금은 초록 킬 · 파랑 어시스트 · 빨강 사망 · 주황 팀원 사망입니다.',
        ],
      },
      {
        kind: 'notes',
        title: '후보 카드의 버튼',
        items: [
          '`보관` : 후보를 클립으로 만들어 카테고리에 남깁니다. 남기고 나면 `보관됨` 으로 바뀌고, 누르면 카테고리를 바꿀 수 있습니다.',
          '`다시 저장` : 보관한 클립의 범위를 고친 뒤 누르면 새 범위로 클립이 다시 만들어집니다.',
          '`삭제` : 아닌 후보를 목록에서 숨깁니다. "삭제한 후보도 보기"를 켜면 되살릴 수 있습니다.',
          '`클립 삭제` : 클립 영상과 그 구간까지 지웁니다. 되돌릴 수 없습니다.',
          '`구간 삭제` : 직접 추가한 구간을 지웁니다.',
          '`메모` : 보관한 클립에 나만 보는 메모를 남깁니다. 서버로 보내지 않습니다.',
        ],
      },
    ],
  },
  {
    id: 'clips',
    label: '클립',
    blocks: [
      {
        kind: 'paras',
        title: '보관과 저장은 다릅니다',
        lines: [
          '보관은 후보를 클립으로 남기는 것이고, 저장(`다시 저장`)은 이미 보관한 클립에 고친 범위를 반영하는 것입니다.',
          '보관하지 않은 후보의 수정은 바로 기억되므로 따로 저장할 필요가 없습니다.',
        ],
      },
      {
        kind: 'paras',
        title: '클립은 자동으로 지워지지 않습니다',
        lines: [
          '"클립" 탭에는 보관한 클립만 카테고리별로 모여 있습니다. 카테고리는 폴더 하나이고, 그 탭에서 새로 만들거나 이름을 바꿀 수 있습니다.',
        ],
      },
      {
        kind: 'paras',
        title: '자동 보관 옵션',
        lines: [
          '기본은 직접 보관이라 처음에는 어떤 후보도 보관되어 있지 않습니다.',
          '옵션의 "클립 보관 방식"을 "자동 보관"으로 바꾸면 분석이 끝날 때 후보가 전부 클립이 되어 `자동 보관` 카테고리에 쌓입니다. 게임마다 1.5~2GB 씩 쌓이고, 이 클립들은 아직 "보관한 것"이 아닙니다.',
          '마음에 드는 것만 `보관`으로 `보관함`이나 직접 만든 카테고리에 옮기고, 필요 없는 것은 `클립 삭제`로 지웁니다.',
        ],
      },
    ],
  },
  {
    id: 'folders',
    label: '폴더',
    blocks: [
      {
        kind: 'paras',
        lines: ['저장 폴더 안에 폴더 두 개가 생깁니다. 클립 폴더 아래의 폴더 하나가 카테고리 하나이고, 탐색기에서 폴더를 만들거나 옮겨도 앱에 그대로 보입니다.'],
      },
      { kind: 'tree' },
      {
        kind: 'paras',
        title: '스팀 녹화 / 영상 파일',
        lines: ['스팀 백그라운드 녹화는 자동으로 분석합니다. 다른 영상(스트리머 다시보기 등)은 옵션 → 영상 파일에서 추가한 뒤 "영상 파일" 탭에서 분석합니다.'],
      },
      { kind: 'callout', title: SSD_TITLE, lines: SSD_LINES },
    ],
  },
  { id: 'shortcuts', label: '단축키', blocks: [{ kind: 'shortcuts' }] },
]

export const GUIDE_FOLDER_TREE = [
  '<저장 폴더>',
  '├─ clips          보관한 클립(자동으로 지워지지 않음)',
  '│   ├─ 보관함       직접 보관한 클립의 기본 칸',
  '│   ├─ 자동 보관    앱이 자동으로 보관한 클립',
  '│   └─ (내가 만든 카테고리들)',
  '└─ full_video     풀영상(용량 한도를 넘으면 자동 정리)',
  '    ├─ steam_replay  스팀 녹화 게임',
  '    └─ vod           영상 파일 게임',
].join('\n')
