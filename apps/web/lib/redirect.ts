// Behind App Hosting / Cloud Run, request.url carries the container's internal host,
// so derive the public origin from the forwarded headers instead.
export function publicOrigin(request: Request): string {
  const host = request.headers.get('x-forwarded-host') ?? request.headers.get('host')
  const proto = request.headers.get('x-forwarded-proto') ?? 'https'
  if (host && !host.startsWith('0.0.0.0') && !host.startsWith('localhost')) return `${proto}://${host}`
  return new URL(request.url).origin
}

// Only allow same-site relative paths (blocks //evil.com, https://evil.com, backslash tricks).
export function safeNext(next: string | null, fallback = '/dashboard'): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return fallback
  return next
}
