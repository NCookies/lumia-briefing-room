import { useAppInfo, videoFormatHelpText } from '../appInfo'
import { HelpTip } from './HelpTip'

export function VideoFormatHelp({ centered = false }: { centered?: boolean }) {
  const text = videoFormatHelpText(useAppInfo().videoFormats)
  return <HelpTip text={text} label="지원하는 영상 형식" centered={centered} />
}
