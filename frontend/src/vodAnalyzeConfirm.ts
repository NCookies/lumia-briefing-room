const NEWLINE = String.fromCharCode(10)
const QUEUE_NOTE = '다른 분석이 돌고 있으면 줄을 서서 차례로 합니다.'
/** 저장 방식이 자동(`clip.saveMode=auto`)이면 이 영상의 기존 클립은 보관 카테고리로 옮긴 것까지 전부 지우고 새로 만든다. 수동이면 저장한 클립은 그대로 둔다. */
const CLIPS =
  '클립 저장 방식이 자동이면 이 영상의 기존 클립은 보관 카테고리로 옮긴 것까지 모두 지우고 새로 만듭니다(라벨만 옮겨집니다, 지우는 방식은 삭제 설정을 따릅니다). 수동 저장이면 저장한 클립은 그대로 둡니다.'

export function vodAnalyzeConfirmMessage(name: string, options: { force?: boolean; rebuild?: boolean }): string {
  if (options.force) {
    return [
      `"${name}" 영상을 처음부터 다시 분석합니다.`,
      `게임마다 풀영상을 새로 만듭니다. ${CLIPS} 실패하면 기존 결과는 그대로 남습니다.`,
      `영상 길이에 따라 수십 분이 걸릴 수 있습니다. ${QUEUE_NOTE} 계속하시겠습니까?`,
    ].join(NEWLINE)
  }
  if (options.rebuild) {
    return [
      `"${name}" 영상의 게임 풀영상과 클립을 저장된 분석 결과로 다시 만듭니다.`,
      `성공하면 기존 풀영상을 새로 바꿉니다. ${CLIPS}`,
      `${QUEUE_NOTE} 계속하시겠습니까?`,
    ].join(NEWLINE)
  }
  return [
    `"${name}" 영상을 분석합니다.`,
    `게임마다 풀영상(캐릭터 선택 ~ 결과 화면)이 저장되어 디스크를 게임 구간만큼 씁니다. 영상 길이에 따라 수십 분이 걸릴 수 있으며, 도중에 취소해도 다음에 이어서 할 수 있습니다. ${QUEUE_NOTE} 계속하시겠습니까?`,
  ].join(NEWLINE)
}
