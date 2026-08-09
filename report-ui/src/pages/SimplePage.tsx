import type { LucideIcon } from 'lucide-react'
import {
  Boxes,
  Cloud,
  FolderGit2,
  Layers,
  MonitorSmartphone,
  Package,
  Smartphone,
  Sparkles,
  Terminal,
  Workflow,
} from 'lucide-react'
import type { ReportPack } from '../types'
import { fmtMoney, fmtMs, shortAt } from '../format'
import { PageHeader } from '../components/PageHeader'
import { ArtifactDownload } from '../components/ArtifactDownload'

type Mode = 'env' | 'reports' | 'settings' | 'artifacts'

type Props = {
  title: string
  subtitle: string
  data: ReportPack
  mode: Mode
  bare?: boolean
}

type EnvRow = {
  label: string
  value?: string
  icon: LucideIcon
  title?: string
}

function firstNonEmpty(...vals: Array<string | undefined | null>): string {
  for (const v of vals) {
    const s = (v || '').trim()
    if (s) return s
  }
  return ''
}

export function SimplePage({ title, subtitle, data, mode, bare }: Props) {
  const env = data.env
  const casePlatforms = Array.from(
    new Set(
      (data.cases || [])
        .flatMap((c) => [
          (c.url || '').trim(),
          ...((c.tags || []).filter((t) => /^(ios|android)$/i.test(t))),
        ])
        .filter(Boolean),
    ),
  ).filter((p) => /^(ios|android)$/i.test(p))
  const caseProviders = Array.from(
    new Set(
      (data.cases || [])
        .map((c) => String(c.artifacts?.provider || '').trim())
        .filter(Boolean),
    ),
  )
  const caseDevices = Array.from(
    new Set(
      (data.cases || [])
        .map((c) => String(c.artifacts?.device_id || '').trim())
        .filter(Boolean),
    ),
  )
  const caseAppIds = Array.from(
    new Set(
      (data.cases || [])
        .map((c) => {
          const u = (c.url || '').trim()
          if (u && !/^(ios|android)$/i.test(u)) return u
          return ''
        })
        .filter(Boolean),
    ),
  )

  const device = firstNonEmpty(
    env.device,
    caseDevices[0],
  )
  const appId = firstNonEmpty(
    env.app_id,
    caseAppIds[0],
  )
  const mobilePlatform = firstNonEmpty(
    env.mobile_platform,
    casePlatforms[0],
  )
  const deviceProvider = firstNonEmpty(
    env.device_provider,
    caseProviders[0],
    'local',
  )

  const envRows: EnvRow[] = [
    { label: 'Device', value: device || undefined, icon: MonitorSmartphone },
    { label: 'Platform', value: mobilePlatform || undefined, icon: Smartphone },
    { label: 'Provider', value: deviceProvider || undefined, icon: Cloud },
    { label: 'App ID', value: appId || undefined, icon: Layers, title: appId || undefined },
    { label: 'Host OS', value: env.platform, icon: Terminal },
    { label: 'Python', value: env.python, icon: Terminal },
    { label: 'MobiFlow', value: env.mobiflow_version, icon: Package },
    { label: 'Maestro', value: env.maestro || undefined, icon: Workflow },
    {
      label: 'Stack',
      value: [env.stack_language, env.stack_tool || 'maestro', env.stack_runner || 'maestro']
        .filter(Boolean)
        .join(' / '),
      icon: Boxes,
    },
  ]
  if (env.llm_provider) {
    envRows.push({ label: 'LLM provider', value: env.llm_provider, icon: Sparkles })
  }
  if (env.repo_path) {
    envRows.push({ label: 'Repo path', value: env.repo_path, icon: FolderGit2 })
  }

  const artifacts = data.cases.flatMap((c) => {
    const shots = Array.isArray(c.artifacts?.screenshots)
      ? (c.artifacts?.screenshots as string[])
      : c.artifacts?.screenshot
        ? [String(c.artifacts.screenshot)]
        : []
    const list = [
      c.artifacts?.video_path,
      c.artifacts?.screenshot,
      ...shots,
      c.artifacts?.flow,
      c.artifacts?.artifact_dir,
      ...(c.files_generated || []),
    ].filter(Boolean) as string[]
    return [...new Set(list)].map((path) => ({ case: c.name, path }))
  })

  return (
    <>
      {bare ? null : <PageHeader title={title} subtitle={subtitle} />}

      {mode === 'env' ? (
        <div className="card">
          <h3 className="card-cap">Runtime & Stack</h3>
          <div className="env-grid">
            {envRows.map((row) => {
              const Icon = row.icon
              return (
                <div className="env-item" key={row.label}>
                  <span className="env-label">
                    <Icon size={12} />
                    {row.label}
                  </span>
                  <strong title={row.title || row.value || undefined}>{row.value || '—'}</strong>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      {mode === 'artifacts' ? (
        <div className="card">
          <h3 className="card-cap">Flows, screenshots & video</h3>
          {artifacts.length ? (
            <table className="data">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Path</th>
                  <th>Download</th>
                </tr>
              </thead>
              <tbody>
                {artifacts.map((a, i) => (
                  <tr key={`${a.case}-${a.path}-${i}`}>
                    <td className="cell-name">{a.case}</td>
                    <td className="cell-path">{a.path}</td>
                    <td>
                      <ArtifactDownload path={a.path} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty">No artifact paths recorded</div>
          )}
        </div>
      ) : null}

      {mode === 'reports' ? (
        <div className="card">
          <h3 className="card-cap">This pack</h3>
          <div className="env-grid">
            <div className="env-item">
              <span className="env-label">
                <Package size={12} /> Pack id
              </span>
              <strong>{data.id}</strong>
            </div>
            <div className="env-item">
              <span className="env-label">
                <Sparkles size={12} /> Generated
              </span>
              <strong>{shortAt(data.generated_at)}</strong>
            </div>
            <div className="env-item">
              <span className="env-label">
                <Layers size={12} /> Cases
              </span>
              <strong>{data.summary.total}</strong>
            </div>
            <div className="env-item">
              <span className="env-label">
                <Workflow size={12} /> Duration
              </span>
              <strong>{fmtMs(data.summary.duration_ms)}</strong>
            </div>
            <div className="env-item">
              <span className="env-label">
                <Sparkles size={12} /> Tokens
              </span>
              <strong>{data.summary.total_tokens.toLocaleString()}</strong>
            </div>
            <div className="env-item">
              <span className="env-label">
                <Cloud size={12} /> Cost
              </span>
              <strong>{fmtMoney(data.summary.cost)}</strong>
            </div>
          </div>
          <p className="hint-text">
            Export the raw pack from Test Results → Export. History lives in
            <code> .mobiflow/history.jsonl</code>.
          </p>
        </div>
      ) : null}

      {mode === 'settings' ? (
        <div className="card">
          <h3 className="card-cap">Report settings</h3>
          <p className="hint-text">
            This report is a single self-contained HTML file. Data is injected at generation time by
            <code> mobiflow report</code>, so every page works offline with no network calls.
          </p>
          <div className="env-grid" style={{ marginTop: 10 }}>
            <div className="env-item">
              <span>Theme</span>
              <strong>MobiFlow light</strong>
            </div>
            <div className="env-item">
              <span>Sidebar</span>
              <strong>#e8eef5</strong>
            </div>
            <div className="env-item">
              <span>Accent</span>
              <strong>#0074bf</strong>
            </div>
            <div className="env-item">
              <span>Typeface</span>
              <strong>Montserrat</strong>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
