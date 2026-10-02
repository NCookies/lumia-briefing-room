import { SSD_ADVICE } from './guide.ts'

/** `(?)` 도움말(`HelpTip`) 문구. HelpTip 은 글자 그대로 보여 주므로 마크업을 쓰지 않는다. */

export const AUTO_CLEAN_HELP =
  '기본은 꺼져 있습니다. 켜면 지우는 것은 풀영상(게임 전체 영상)뿐입니다. 용량 한도(권장 40GB) 같은 기준을 넘으면 오래된 것부터 지워지고, 보관한 클립과 게임 기록(교전 후보·결과표)은 남습니다.\n남기고 싶은 게임은 게임 목록의 "고정"을 누르세요.'

export const SAVE_MODE_HELP =
  '자동 보관(기본): 분석이 끝나면 후보를 전부 클립으로 만들어 "자동 보관" 카테고리에 쌓습니다. 게임마다 1.5~2GB 가 쌓이고, 마음에 드는 것만 골라 "보관"해야 보관한 클립이 됩니다.\n직접 보관: 클립을 만들지 않고, 풀영상 화면에서 고른 후보만 보관합니다.'

export const VOD_DELETE_SOURCE_HELP =
  '분석이 끝나 게임 풀영상이 1개 이상 저장된 영상만 지웁니다. 취소·실패했거나 게임을 못 찾은 영상은 지우지 않습니다.\n"묻기"는 분석을 시작할 때마다 확인 창을 띄웁니다. 삭제 방식의 기본값은 Windows 휴지통이라 되돌릴 수 있습니다.'

export const FULL_VIDEO_LOCATION_HELP = `풀영상은 한 판에 수 GB 라 큰 하드디스크로 빼고 싶을 때만 따로 정하세요. 기본은 저장 폴더 아래 full_video 폴더입니다.\n${SSD_ADVICE}`

export const FULL_VIDEO_MISSING_HELP =
  '풀영상(게임 전체 영상)이 없는 게임입니다. 이전 버전에서 분석했거나, 자동 정리로 지워졌거나, 만들지 못한 경우입니다.\n교전 후보 목록과 이미 보관한 클립은 남아 있습니다.'

export const RECORDING_STOPPED_HELP = `스팀 백그라운드 녹화가 게임 도중 오류로 멈춰 이 게임의 영상이 없거나 일부뿐입니다.\n${SSD_ADVICE}`
