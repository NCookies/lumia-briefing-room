const NEWLINE = String.fromCharCode(10)

export function vodAnalyzeConfirmMessage(name: string, options: { force?: boolean; rebuild?: boolean }): string {
  if (options.force) {
    return [`"${name}" 영상을 처음부터 다시 분석합니다.`, '영상 길이에 따라 수십 분이 걸릴 수 있습니다. 계속하시겠습니까?'].join(NEWLINE)
  }
  if (options.rebuild) {
    return [`"${name}" 영상을 다시 분석합니다.`, '몇 분 정도 소요될 수 있습니다. 계속하시겠습니까?'].join(NEWLINE)
  }
  return [
    `"${name}" 영상을 분석합니다.`,
    '게임마다 풀영상(캐릭터 선택 ~ 결과 화면)이 저장되어 디스크를 게임 구간만큼 씁니다. 영상 길이에 따라 수십 분이 걸릴 수 있으며, 도중에 취소해도 다음에 이어서 할 수 있습니다. 계속하시겠습니까?',
  ].join(NEWLINE)
}
