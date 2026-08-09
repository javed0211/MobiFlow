/** Resolve local .mobiflow artifact paths for the report UI. */

export function artifactBasename(absPath: string | null | undefined): string | null {
  if (!absPath) return null
  return absPath.split(/[/\\]/).pop() || null
}

/** Map an absolute path under `.mobiflow/` to an HTTP URL when `mobiflow serve` is used. */
export function artifactHttpUrl(absPath: string | null | undefined): string | null {
  if (!absPath) return null
  const normalized = absPath.replace(/\\/g, '/')

  if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
    const m = normalized.match(/\/\.mobiflow\/(.+)$/i)
    if (m?.[1]) {
      const rel = m[1]
        .split('/')
        .map((seg) => encodeURIComponent(seg))
        .join('/')
      return `${window.location.origin}/${rel}`
    }
    const name = artifactBasename(normalized)
    if (!name) return null
    const kind = artifactKindFromPath(normalized)
    if (kind) return `${window.location.origin}/${kind}/${encodeURIComponent(name)}`
    return `${window.location.origin}/reports/${encodeURIComponent(name)}`
  }

  if (normalized.startsWith('/') || /^[A-Za-z]:[\\/]/.test(absPath)) {
    return `file://${normalized.startsWith('/') ? normalized : `/${normalized}`}`
  }
  return absPath
}

export function artifactKindFromPath(
  absPath: string,
): 'videos' | 'traces' | 'reports' | 'screenshots' | 'evidence' | null {
  const p = absPath.replace(/\\/g, '/').toLowerCase()
  if (p.includes('/videos/') || /\.(webm|mp4|mov)$/.test(p)) return 'videos'
  if (p.includes('/screenshots/') || /\.(png|jpe?g|webp|gif)$/.test(p)) return 'screenshots'
  if (p.includes('/traces/')) return 'traces'
  if (p.includes('/evidence/')) return 'evidence'
  if (p.includes('/reports/') || p.includes('/memory/')) return 'reports'
  return null
}

export function artifactUrl(
  absPath: string | null | undefined,
  kind?: 'videos' | 'traces' | 'reports' | 'screenshots',
): string | null {
  if (!absPath) return null
  const http = artifactHttpUrl(absPath)
  if (http) return http

  const name = artifactBasename(absPath)
  if (!name) return null

  if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
    const k = kind || artifactKindFromPath(absPath) || 'reports'
    return `${window.location.origin}/${k}/${encodeURIComponent(name)}`
  }

  if (absPath.startsWith('/') || /^[A-Za-z]:[\\/]/.test(absPath)) {
    return `file://${absPath}`
  }
  return absPath
}

export function canDownloadArtifact(url: string | null | undefined): boolean {
  if (!url) return false
  // Same-origin HTTP downloads work with the download attribute; file:// usually does not.
  return url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:')
}

export function videoPathOf(c: {
  artifacts?: Record<string, unknown> | null
}): string | null {
  const p = c.artifacts?.video_path
  return p ? String(p) : null
}

export function screenshotPathOf(c: {
  artifacts?: Record<string, unknown> | null
}): string | null {
  const arts = c.artifacts || {}
  const primary = arts.screenshot
  if (primary) return String(primary)
  const many = arts.screenshots
  if (Array.isArray(many) && many.length) return String(many[0])
  if (typeof many === 'string' && many) {
    try {
      const parsed = JSON.parse(many)
      if (Array.isArray(parsed) && parsed[0]) return String(parsed[0])
    } catch {
      return many.split(',')[0]?.trim() || null
    }
  }
  return null
}

export function screenshotPathsOf(c: {
  artifacts?: Record<string, unknown> | null
}): string[] {
  const arts = c.artifacts || {}
  const many = arts.screenshots
  if (Array.isArray(many)) return many.map(String).filter(Boolean)
  if (typeof many === 'string' && many.trim()) {
    try {
      const parsed = JSON.parse(many)
      if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean)
    } catch {
      return many
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    }
  }
  const one = screenshotPathOf(c)
  return one ? [one] : []
}

export function tracePathOf(c: {
  artifacts?: Record<string, unknown> | null
}): string | null {
  const p = c.artifacts?.trace_path || c.artifacts?.trace
  return p ? String(p) : null
}
