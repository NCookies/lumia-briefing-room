export type DeleteMode = 'recycle' | 'permanent'

export interface DeleteConfirmChoice {
  skipNext: boolean
  permanent: boolean
}

export interface DeleteChoiceResult {
  mode: DeleteMode
  skipNext: boolean
}

export function deleteConfirmMessage(mode: DeleteMode): string {
  if (mode === 'permanent') {
    return '영구 삭제하면 되돌릴 수 없습니다.'
  }
  return (
    'Windows 휴지통으로 보냅니다. Windows 휴지통에서 되살릴 때는 ' +
    '이 클립의 파일(영상·정보·썸네일)을 모두 복원해야 이 앱에서 다시 볼 수 있습니다.'
  )
}

export function needsPermanentSkipWarning(choice: DeleteConfirmChoice): boolean {
  return choice.skipNext && choice.permanent
}

export function resolveDeleteChoice(choice: DeleteConfirmChoice): DeleteChoiceResult {
  return { mode: choice.permanent ? 'permanent' : 'recycle', skipNext: choice.skipNext }
}
