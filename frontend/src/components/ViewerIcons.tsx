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
export const ZoomInIcon = () =>
  svg(<path d="M15.5 14h-.8l-.3-.3A6.5 6.5 0 1 0 14 15.5l.3.3v.8l5 5 1.5-1.5zM9.5 14A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14zM10.5 7h-2v2h-2v2h2v2h2v-2h2V9h-2z" />)
export const ZoomOutIcon = () =>
  svg(<path d="M15.5 14h-.8l-.3-.3A6.5 6.5 0 1 0 14 15.5l.3.3v.8l5 5 1.5-1.5zM9.5 14A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14zM6.5 9h6v2h-6z" />)
export const FullscreenIcon = () => svg(<path d="M4 4h6v2H6v4H4zM14 4h6v6h-2V6h-4zM4 14h2v4h4v2H4zM18 14h2v6h-6v-2h4z" />)
export const ExitFullscreenIcon = () => svg(<path d="M8 4h2v6H4V8h4zM14 4h2v4h4v2h-6zM4 14h6v6H8v-4H4zM14 14h6v2h-4v4h-2z" />)
