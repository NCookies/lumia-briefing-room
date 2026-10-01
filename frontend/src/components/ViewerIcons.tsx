const svg = (children: React.ReactNode) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true" className="inline-block align-middle">
    {children}
  </svg>
)

export const PlayIcon = () => svg(<path d="M8 5v14l11-7z" />)
export const PauseIcon = () => svg(<path d="M6 5h4v14H6zM14 5h4v14h-4z" />)
export const PrevIcon = () => svg(<path d="M6 6h2v12H6zM9.5 12 18 18V6z" />)
export const NextIcon = () => svg(<path d="M16 6h2v12h-2zM6 18l8.5-6L6 6z" />)
export const VolumeIcon = () => svg(<path d="M3 9v6h4l5 5V4L7 9zM14 8.5v7a4.5 4.5 0 0 0 0-7z" />)
export const MuteIcon = () =>
  svg(<path d="M3 9v6h4l5 5V4L7 9zM16.6 9.2 15.2 10.6 16.6 12l-1.4 1.4 1.4 1.4 1.4-1.4 1.4 1.4 1.4-1.4-1.4-1.4 1.4-1.4-1.4-1.4-1.4 1.4z" />)
const zoomSvg = (sign: React.ReactNode) => (
  <svg
    viewBox="0 0 24 24"
    width="24"
    height="24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.6"
    strokeLinecap="round"
    aria-hidden="true"
    className="inline-block align-middle"
  >
    <circle cx="10" cy="10" r="6.8" />
    <path d="m15.2 15.2 6 6" strokeWidth="3.2" />
    {sign}
  </svg>
)

export const ZoomInIcon = () => zoomSvg(<path d="M10 6.6v6.8M6.6 10h6.8" />)
export const ZoomOutIcon = () => zoomSvg(<path d="M6.6 10h6.8" />)
export const EditIcon = () => svg(<path d="M3 17.25V21h3.75L17.8 9.94l-3.75-3.75zM20.7 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75z" />)
export const FullscreenIcon = () => svg(<path d="M4 4h6v2H6v4H4zM14 4h6v6h-2V6h-4zM4 14h2v4h4v2H4zM18 14h2v6h-6v-2h4z" />)
export const ExitFullscreenIcon = () => svg(<path d="M8 4h2v6H4V8h4zM14 4h2v4h4v2h-6zM4 14h6v6H8v-4H4zM14 14h6v2h-4v4h-2z" />)

const bookmark = (filled: boolean) => (
  <svg
    viewBox="0 0 24 24"
    width="16"
    height="16"
    fill={filled ? 'currentColor' : 'none'}
    stroke="currentColor"
    strokeWidth="2"
    strokeLinejoin="round"
    aria-hidden="true"
    className="inline-block align-middle"
  >
    <path d="M6 3h12v18l-6-4.5L6 21z" />
  </svg>
)
export const BookmarkIcon = () => bookmark(false)
export const BookmarkFilledIcon = () => bookmark(true)

const seekSvg = (seconds: number, mirror: boolean) => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="inline-block align-middle">
    <g transform={mirror ? 'translate(24 0) scale(-1 1)' : undefined}>
      <path d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5" />
      <path d="M4 3.5v4h4" />
    </g>
    <text x="12" y="15.2" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="currentColor" stroke="none" fontFamily="inherit">
      {seconds}
    </text>
  </svg>
)

export const SeekBackIcon = ({ seconds }: { seconds: number }) => seekSvg(seconds, false)
export const SeekForwardIcon = ({ seconds }: { seconds: number }) => seekSvg(seconds, true)

const stroke = (children: React.ReactNode, size = 18) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="inline-block align-middle">
    {children}
  </svg>
)

export const UndoIcon = () => stroke(<><path d="M9 14 4 9l5-5" /><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" /></>)
export const RedoIcon = () => stroke(<><path d="m15 14 5-5-5-5" /><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13" /></>)
export const KeyboardIcon = () =>
  stroke(<><rect x="2.5" y="6" width="19" height="12" rx="2" /><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7 14h10" /></>)
export const PlusIcon = () => stroke(<path d="M12 5v14M5 12h14" />, 16)
