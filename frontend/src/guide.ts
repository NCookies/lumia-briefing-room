export type GuideTabId = 'start' | 'viewer' | 'clips' | 'cleanup' | 'vod' | 'folders' | 'shortcuts'

export type GuideBlock =
  | { kind: 'steps'; items: string[] }
  | { kind: 'notes'; title: string; items: string[] }
  | { kind: 'paras'; title?: string; lines: string[] }
  | { kind: 'callout'; title: string; lines: string[] }
  | { kind: 'tree' }
  | { kind: 'videoFormats' }
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
  메모: 'secondary',
  '구간 삭제': 'secondary',
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
          '`보관`을 눌러 카테고리를 선택하여 원하는 클립을 보관할 수 있습니다.',
          '"클립" 탭에서 카테고리별로 모아 봅니다.',
        ],
      },
      {
        kind: 'notes',
        title: '알아 두면 좋은 것',
        items: [
          '풀영상은 용량 한도(기본 40GB)를 넘으면 오래된 것부터 자동으로 지워지며, `고정`한 게임과 보관한 클립은 지워지지 않습니다.',
          '클립의 범위를 수정했다면 `다시 저장`을 눌러야 적용됩니다.',
          '분석이 끝나면 후보가 자동으로 클립이 됩니다(옵션 → 일반 → 클립 보관 방식에서 끌 수 있습니다). 자세한 내용은 "클립" 탭에 있습니다.',
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
        lines: ['게임 하나의 전체 영상입니다(캐릭터 선택 화면부터 결과 화면까지). 앱이 자동으로 만들고, 게임 목록의 `고정`을 누르면 자동 정리에서 제외됩니다.'],
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
        title: '클립은 자동 정리 대상이 아닙니다',
        lines: [
          '"클립" 탭에는 보관한 클립이 카테고리별로 모여 있고, 풀영상과 달리 자동으로 지워지지 않습니다.',
          '그래서 계속 쌓이니 저장 폴더의 용량에 신경 써야 합니다. 필요 없는 클립은 `클립 삭제`로 지우세요.',
        ],
      },
    ],
  },
  {
    id: 'cleanup',
    label: '자동 정리',
    blocks: [
      {
        kind: 'paras',
        title: '무엇이 지워지나',
        lines: [
          '지워지는 것은 게임의 풀영상(full.mp4)뿐입니다. 보관한 클립과 게임 기록(교전 후보·결과표)은 남습니다.',
          '스팀 녹화와 영상 파일 두 탭의 풀영상을 합쳐서 계산합니다. 게임 목록 위 막대가 "이 탭 / 전체 / 한도"입니다.',
          '한도는 전체 기준이라 한 탭만 봐서는 넘었는지 알 수 없습니다.',
        ],
      },
      {
        kind: 'paras',
        title: '어떤 게임부터 지워지나',
        lines: [
          '`고정`한 게임과 보호 태그가 붙은 게임은 처음부터 대상이 아닙니다. 나머지는 게임을 한 시각이 오래된 순서로 지우고, 용량이 큰지는 상관없습니다.',
          '기준(옵션 → 자동 정리)은 체크한 것만 적용됩니다. 용량 한도는 합계가 한도 아래로 내려올 때까지 가장 오래된 것부터 하나씩 더합니다.',
          '그래서 한도를 조금만 넘으면 가장 오래된 게임 한 개만 지워집니다.',
        ],
      },
      {
        kind: 'notes',
        title: '"삭제 예정만 보기"',
        items: [
          '다음 자동 정리 때 풀영상이 지워질 게임만 모아 보는 버튼입니다. 괄호 안 숫자가 그 게임 수입니다.',
          '버튼이 흐리면 지금 지워질 게임이 없다는 뜻입니다. 한도를 넘지 않았거나, 남은 게임이 모두 `고정`·보호 태그인 경우입니다.',
          '자동 정리를 끄거나 한도를 비워 두면 막대와 삭제 예정 표시가 사라집니다.',
        ],
      },
      {
        kind: 'notes',
        title: '알아 두면 좋은 것',
        items: [
          '정리는 앱이 켜져 있는 동안 1시간마다 돕니다. 한도를 넘자마자 지워지지는 않습니다.',
          '삭제 방식 기본값은 영구 삭제입니다. 휴지통으로 보내려면 옵션에서 바꾸세요.',
          '"지우기 전에" 옵션을 켜면 남길 후보를 클립으로 보관한 뒤 지웁니다. 보관에 실패한 게임은 이번에 지우지 않습니다.',
          '풀영상이 지워진 게임도 목록에 남고 보관한 클립은 그대로 볼 수 있지만, 새로 보관할 수는 없습니다.',
        ],
      },
    ],
  },
  {
    id: 'vod',
    label: '영상 파일',
    blocks: [
      {
        kind: 'paras',
        title: '스팀 녹화와 영상 파일',
        lines: [
          '스팀 백그라운드 녹화는 자동으로 분석합니다. OBS 녹화나 스트리머 다시보기 같은 영상 파일은 직접 추가해야 합니다.',
          '영상 파일에서 게임을 찾아 스팀 녹화와 같은 풀영상과 교전 후보를 만듭니다.',
        ],
      },
      {
        kind: 'steps',
        items: [
          '옵션 → 영상 파일에서 영상 파일이나 폴더를 추가합니다. 원본은 옮기거나 복사하지 않고 읽기만 합니다.',
          '"영상 파일" 탭에서 분석을 시작합니다.',
          '분석이 끝나면 게임을 눌러 풀영상 화면에서 후보를 다듬고 보관합니다.',
        ],
      },
      { kind: 'videoFormats' },
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
