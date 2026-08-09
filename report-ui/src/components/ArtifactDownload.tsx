import { Download, ExternalLink } from 'lucide-react'
import {
  artifactBasename,
  artifactUrl,
  canDownloadArtifact,
} from '../artifacts'
import { ICON_STROKE } from '../iconDefaults'

type Props = {
  path: string
  label?: string
  kind?: 'videos' | 'traces' | 'reports' | 'screenshots'
  className?: string
}

export function ArtifactDownload({ path, label, kind, className = '' }: Props) {
  const url = artifactUrl(path, kind)
  const name = artifactBasename(path) || 'artifact'
  const downloadable = canDownloadArtifact(url)

  if (!url) {
    return (
      <span className={`artifact-actions ${className}`.trim()} title="No download URL">
        <button type="button" className="btn btn-sm" disabled>
          <Download size={12} strokeWidth={ICON_STROKE} />
          Download
        </button>
      </span>
    )
  }

  return (
    <span className={`artifact-actions ${className}`.trim()}>
      {downloadable ? (
        <a className="btn btn-sm" href={url} download={name} title={`Download ${name}`}>
          <Download size={12} strokeWidth={ICON_STROKE} />
          {label || 'Download'}
        </a>
      ) : (
        <a
          className="btn btn-sm"
          href={url}
          target="_blank"
          rel="noreferrer"
          title="Open file (use mobiflow serve for direct download)"
        >
          <ExternalLink size={12} strokeWidth={ICON_STROKE} />
          Open
        </a>
      )}
    </span>
  )
}
