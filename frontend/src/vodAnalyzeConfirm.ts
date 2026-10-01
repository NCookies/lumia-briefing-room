const NEWLINE = String.fromCharCode(10)

export function vodAnalyzeConfirmMessage(name: string, options: { force?: boolean; rebuild?: boolean }, fromFullVideos = false): string {
  if (fromFullVideos) {
    return [`"${name}" 원본 영상이 없어 저장된 게임 풀영상에서 클립만 다시 추출합니다.`, '몇 분 정도 소요될 수 있습니다. 계속하시겠습니까?'].join(NEWLINE)
  }
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

/** 작업이 끝났을 때 알림 문구. 원본이 없어 풀영상에서 클립만 다시 추출했으면 그 사실을 알린다. */
export function vodDoneNotice(job: { kind?: string; fromFullVideos?: boolean; clipsFailed?: number }): string {
  if (job.kind === 'fullVideos') return '풀영상을 만들었습니다.'
  if (job.fromFullVideos) {
    const base = '원본 영상이 없어 저장된 풀영상에서 클립만 다시 추출했습니다.'
    return job.clipsFailed ? `${base} (클립 ${job.clipsFailed}개는 만들지 못했습니다)` : base
  }
  return '분석을 마쳤습니다.'
}
