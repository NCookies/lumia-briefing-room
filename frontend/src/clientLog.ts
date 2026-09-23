const DEDUPE_MS = 5000
const recent = new Map<string, number>()

function send(level: string, message: string, stack?: string): void {
  const now = Date.now()
  const key = `${level}|${message}`
  const last = recent.get(key)
  if (last !== undefined && now - last < DEDUPE_MS) return
  recent.set(key, now)
  try {
    void fetch('/api/client-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, message, stack, url: location.href, time: new Date().toISOString() }),
      keepalive: true,
    }).catch(() => {})
  } catch {
    // 로그 전송 실패는 재시도하지 않는다
  }
}

const describe = (value: unknown): string =>
  value instanceof Error ? value.message : typeof value === 'string' ? value : JSON.stringify(value) ?? String(value)

export function installClientLog(): void {
  window.addEventListener('error', (e) => send('error', e.message, e.error?.stack))
  window.addEventListener('unhandledrejection', (e) => {
    const reason = e.reason
    send('unhandledrejection', describe(reason), reason instanceof Error ? reason.stack : undefined)
  })
  const original = console.error
  console.error = (...args: unknown[]) => {
    original.apply(console, args)
    send('console.error', args.map(describe).join(' '))
  }
}
