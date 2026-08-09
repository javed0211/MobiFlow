export function fmtMs(ms?: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60_000).toFixed(1)}m`
}

export function fmtMoney(n?: number | null): string {
  return `$${(n ?? 0).toFixed(4)}`
}

export function fmtTok(n?: number | null): string {
  return Number(n ?? 0).toLocaleString()
}

export function shortAt(iso?: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function chartLabel(at: string, index: number, total: number): string {
  if (index === total - 1) return 'now'
  try {
    return new Date(at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  } catch {
    return String(index + 1)
  }
}
