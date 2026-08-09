import { useMemo, useState } from 'react'
import {
  CheckCircle2,
  CircleAlert,
  Clock3,
  Coins,
  Download,
  ExternalLink,
  FileCode2,
  Filter,
  Globe2,
  ListChecks,
  Package,
  ScrollText,
  Search,
  Sparkles,
  Tag,
  Video,
  Workflow,
  XCircle,
} from 'lucide-react'
import type { CaseRecord, PhaseStatus, ReportPack, StepRecord } from '../types'
import { fmtMoney, fmtMs, fmtTok, shortAt } from '../format'
import { Badge } from '../components/Badge'
import { ArtifactDownload } from '../components/ArtifactDownload'
import {
  artifactBasename,
  artifactUrl,
  canDownloadArtifact,
  screenshotPathsOf,
  videoPathOf,
} from '../artifacts'
import { ICON_STROKE } from '../iconDefaults'

type Props = { data: ReportPack }
type StatusFilter = 'all' | 'passed' | 'failed' | 'video'
type DetailTab = 'details' | 'steps' | 'artifacts'

function isFailedStatus(status?: string) {
  return status === 'failed' || status === 'error'
}

function isPassedStatus(status?: string) {
  return status === 'passed' || status === 'success' || status === 'pass'
}

function phaseTone(status?: string) {
  if (isPassedStatus(status)) return 'pass'
  if (isFailedStatus(status)) return 'fail'
  return 'warn'
}

function phaseLabel(p: PhaseStatus) {
  if (p.status === 'skipped') return 'Skipped'
  if (isPassedStatus(p.status)) return 'Success'
  if (isFailedStatus(p.status)) return 'Failed'
  return p.status || 'Unknown'
}

function StatusDot({ status }: { status?: string }) {
  const failed = isFailedStatus(status)
  const passed = isPassedStatus(status)
  const title = status || 'unknown'
  return (
    <span
      className={`case-status-dot ${failed ? 'fail' : passed ? 'pass' : 'warn'}`}
      title={title}
      aria-label={title}
    >
      {failed ? <XCircle size={13} /> : passed ? <CheckCircle2 size={13} /> : <Workflow size={13} />}
    </span>
  )
}

function StepsTable({ steps }: { steps: StepRecord[] }) {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('all')
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase()
    return steps.filter((s) => {
      if (status !== 'all' && (s.status || '') !== status) return false
      if (!query) return true
      const hay = [s.raw, s.action, s.detail, s.locator, s.value, s.url]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return hay.includes(query)
    })
  }, [steps, q, status])

  return (
    <div>
      <div className="steps-toolbar">
        <div className="hint">
          {filtered.length} / {steps.length} steps · click row to expand
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <input
            className="field"
            placeholder="Filter steps…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select className="field" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">All statuses</option>
            <option value="pass">Pass</option>
            <option value="fail">Fail</option>
            <option value="skipped">Skipped</option>
            <option value="info">Info</option>
          </select>
        </div>
      </div>
      <div className="steps-wrap">
        {steps.length === 0 ? (
          <div className="empty">No step details recorded</div>
        ) : (
          <table className="steps-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Step</th>
                <th>Status</th>
                <th>ms</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const open = !!expanded[s.index]
                const detail = [s.action, s.detail, s.locator, s.value ? `value=${s.value}` : null, s.url]
                  .filter(Boolean)
                  .join(' · ')
                return (
                  <>
                    <tr
                      key={s.index}
                      className={open ? 'expanded' : ''}
                      onClick={() => setExpanded((prev) => ({ ...prev, [s.index]: !prev[s.index] }))}
                    >
                      <td className="num">{s.index}</td>
                      <td>
                        <div className="raw" title={s.raw || s.action}>
                          {s.raw || s.action}
                        </div>
                        {detail ? (
                          <div className="det" title={detail}>
                            {detail}
                          </div>
                        ) : null}
                      </td>
                      <td className="status-col">
                        <Badge status={s.status} />
                      </td>
                      <td className="ms">{s.duration_ms || '—'}</td>
                    </tr>
                    {open && s.screenshot ? (
                      <tr key={`${s.index}-shot`} className="step-shot-row">
                        <td colSpan={4}>
                          <a
                            href={artifactUrl(s.screenshot, 'screenshots') || s.screenshot}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <img
                              src={artifactUrl(s.screenshot, 'screenshots') || s.screenshot}
                              alt={`Step ${s.index} screenshot`}
                              style={{
                                maxWidth: '100%',
                                maxHeight: 280,
                                borderRadius: 8,
                                border: '1px solid #e2e8f0',
                              }}
                            />
                          </a>
                          <div className="video-path">{s.screenshot}</div>
                        </td>
                      </tr>
                    ) : null}
                  </>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function CaseDetail({ c }: { c?: CaseRecord }) {
  const [tab, setTab] = useState<DetailTab>('details')
  if (!c) {
    return (
      <div className="card detail suite-detail detail-pane">
        <div className="empty">Select a case from the suite list.</div>
      </div>
    )
  }

  const tu = c.total_usage || { prompt_tokens: 0, completion_tokens: 0, cost: 0 }
  const videoAbs = videoPathOf(c)
  const videoSrc = artifactUrl(videoAbs, 'videos')
  const shotPaths = screenshotPathsOf(c)
  const provider = c.artifacts?.provider ? String(c.artifacts.provider) : ''
  const deviceId = c.artifacts?.device_id ? String(c.artifacts.device_id) : ''
  const dashboardUrl = c.artifacts?.dashboard_url
    ? String(c.artifacts.dashboard_url)
    : ''
  const buildId = c.artifacts?.build_id ? String(c.artifacts.build_id) : ''
  const arts = [
    { label: 'Failure screenshot', path: c.artifacts?.screenshot },
    { label: 'Video', path: c.artifacts?.video_path },
    { label: 'Flow YAML', path: c.artifacts?.flow },
    { label: 'Artifact dir', path: c.artifacts?.artifact_dir },
  ].filter((a) => a.path) as Array<{ label: string; path: string }>

  const failureText =
    (c.failure_output || '').trim() ||
    (c.errors || []).filter(Boolean).join('\n').trim() ||
    (c.phases || [])
      .filter((p) => isFailedStatus(p.status) || p.status === 'skipped')
      .map((p) => `${p.name}: ${p.detail || p.status}`)
      .join('\n')

  const tabs: Array<{ id: DetailTab; label: string; icon: typeof ListChecks }> = [
    { id: 'details', label: 'Details', icon: ListChecks },
    { id: 'steps', label: 'Steps', icon: Workflow },
    { id: 'artifacts', label: 'Artifacts', icon: Package },
  ]

  return (
    <div className="card detail suite-detail detail-pane">
      <div className="detail-head">
        <h2 className="detail-title" title={c.title || c.name}>
          {c.title || c.name}
        </h2>
        <div className="detail-meta">
          <span title={c.url || undefined}>
            <Globe2 size={12} />
            {c.url || '—'}
          </span>
          <span>
            <Clock3 size={12} />
            {shortAt(c.finished_at)} · {fmtMs(c.duration_ms)}
          </span>
          <span>
            <Coins size={12} />
            {fmtMoney(tu.cost)}
          </span>
        </div>
        <div className="tags">
          <Badge status={c.status} />
          <Badge status="mode">{c.mode}</Badge>
          {(c.tags || []).map((t) => (
            <span className="tag-pill" key={t}>
              <Tag size={10} />@{t}
            </span>
          ))}
        </div>
      </div>

      <div className="detail-tabs">
        {tabs.map((t) => {
          const Icon = t.icon
          return (
            <button
              key={t.id}
              type="button"
              className={`detail-tab${tab === t.id ? ' active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <Icon size={13} />
              {t.label}
            </button>
          )
        })}
      </div>

      <div className="detail-scroll">
        {tab === 'details' ? (
          <div className="detail-panel">
            <div>
              <h3 className="section-label">
                <ScrollText size={12} /> Test case / prompt
              </h3>
              {c.prompt?.trim() ? (
                <div className="prompt-block">
                  {c.source_case ? (
                    <div className="prompt-source" title={c.source_case}>
                      <FileCode2 size={11} />
                      {c.source_case}
                    </div>
                  ) : null}
                  <pre className="prompt-text">{c.prompt.trim()}</pre>
                </div>
              ) : (
                <div className="empty" style={{ padding: 12 }}>
                  No case prompt was recorded for this run.
                  {c.source_case ? (
                    <>
                      {' '}
                      Source path: <code>{c.source_case}</code>
                    </>
                  ) : null}
                </div>
              )}
            </div>

            {isFailedStatus(c.status) ? (
              <div>
                <h3 className="section-label">
                  <CircleAlert size={12} /> Failure reason
                </h3>
                <div className="fail-block">
                  {failureText || 'No failure detail was captured for this case.'}
                </div>
                {shotPaths.length ? (
                  <div className="shot-gallery" style={{ marginTop: 10 }}>
                    {shotPaths.map((p) => {
                      const src = artifactUrl(p, 'screenshots')
                      return src ? (
                        <a key={p} href={src} target="_blank" rel="noreferrer" title={p}>
                          <img
                            src={src}
                            alt="Failure screenshot"
                            className="fail-shot"
                            style={{
                              maxWidth: '100%',
                              borderRadius: 8,
                              border: '1px solid #e2e8f0',
                              marginTop: 8,
                            }}
                          />
                        </a>
                      ) : null
                    })}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div>
              <h3 className="section-label">
                <Workflow size={12} /> Phases
              </h3>
              <div className="phase-row">
                {(c.phases || []).map((p, i) => (
                  <div className={`phase tone-${phaseTone(p.status)}`} key={i}>
                    <div className="phase-name">
                      {isPassedStatus(p.status) ? (
                        <CheckCircle2 size={11} />
                      ) : isFailedStatus(p.status) ? (
                        <XCircle size={11} />
                      ) : (
                        <Workflow size={11} />
                      )}
                      {p.name}
                    </div>
                    <div className={`phase-status ${phaseTone(p.status)}`}>{phaseLabel(p)}</div>
                    <div className="phase-detail" title={p.detail || undefined}>
                      {p.detail ||
                        (p.status === 'skipped'
                          ? 'No detail recorded for why this phase was skipped'
                          : '—')}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3 className="section-label">
                <Sparkles size={12} /> Token usage
              </h3>
              <div className="token-grid">
                <div className="token-box">
                  <div className="t">Explore</div>
                  <div className="v">
                    {fmtTok(c.explore_usage?.prompt_tokens)} in /{' '}
                    {fmtTok(c.explore_usage?.completion_tokens)} out
                  </div>
                  <div className="v">{fmtMoney(c.explore_usage?.cost)}</div>
                </div>
                <div className="token-box">
                  <div className="t">Codegen</div>
                  <div className="v">
                    {fmtTok(c.codegen_usage?.prompt_tokens)} in /{' '}
                    {fmtTok(c.codegen_usage?.completion_tokens)} out
                  </div>
                  <div className="v">{fmtMoney(c.codegen_usage?.cost)}</div>
                </div>
                <div className="token-box">
                  <div className="t">Total</div>
                  <div className="v">
                    {fmtTok(tu.prompt_tokens)} in / {fmtTok(tu.completion_tokens)} out
                  </div>
                  <div className="v">{fmtMoney(tu.cost)}</div>
                </div>
              </div>
              {c.heal_attempts ? (
                <div className="detail-footnote">
                  Heal / verify attempts: {c.heal_attempts}
                </div>
              ) : null}
              {(c.files_generated || []).length ? (
                <div className="detail-footnote">
                  <div>Generated:</div>
                  <div className="generated-files">
                    {c.files_generated!.map((f) => (
                      <span className="file-chip" key={f} title={f}>
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {tab === 'steps' ? (
          <div className="detail-panel">
            <StepsTable steps={c.steps || []} />
          </div>
        ) : null}

        {tab === 'artifacts' ? (
          <div className="detail-panel">
            {provider || deviceId || dashboardUrl || buildId ? (
              <div style={{ marginBottom: 16 }}>
                <h3 className="section-label">
                  <Globe2 size={12} strokeWidth={ICON_STROKE} /> Run target
                </h3>
                <div className="artifact-list">
                  {provider ? (
                    <div className="artifact-row">
                      <div className="artifact-row-meta">
                        <strong>Provider</strong>
                        <span>{provider}</span>
                      </div>
                    </div>
                  ) : null}
                  {deviceId ? (
                    <div className="artifact-row">
                      <div className="artifact-row-meta">
                        <strong>Device</strong>
                        <span title={deviceId}>{deviceId}</span>
                      </div>
                    </div>
                  ) : null}
                  {buildId ? (
                    <div className="artifact-row">
                      <div className="artifact-row-meta">
                        <strong>Build</strong>
                        <span>{buildId}</span>
                      </div>
                    </div>
                  ) : null}
                  {dashboardUrl ? (
                    <div className="artifact-row">
                      <div className="artifact-row-meta">
                        <strong>Cloud dashboard</strong>
                        <span title={dashboardUrl}>{dashboardUrl}</span>
                      </div>
                      <a
                        className="btn btn-sm"
                        href={dashboardUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <ExternalLink size={12} strokeWidth={ICON_STROKE} />
                        Open
                      </a>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}

            {shotPaths.length ? (
              <div>
                <h3 className="section-label">
                  <CircleAlert size={12} strokeWidth={ICON_STROKE} /> Failure screenshot
                </h3>
                <div className="shot-gallery">
                  {shotPaths.map((p) => {
                    const src = artifactUrl(p, 'screenshots')
                    return (
                      <div key={p} style={{ marginBottom: 12 }}>
                        {src ? (
                          <a href={src} target="_blank" rel="noreferrer">
                            <img
                              src={src}
                              alt="Failure screenshot"
                              className="fail-shot"
                              style={{
                                maxWidth: '100%',
                                borderRadius: 8,
                                border: '1px solid #e2e8f0',
                              }}
                            />
                          </a>
                        ) : null}
                        <div className="artifact-row" style={{ marginTop: 8 }}>
                          <div className="artifact-row-meta">
                            <strong>Screenshot</strong>
                            <span title={p}>{p}</span>
                          </div>
                          <ArtifactDownload path={p} kind="screenshots" />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : null}

            <div>
              <h3 className="section-label">
                <Video size={12} strokeWidth={ICON_STROKE} /> Execution video
              </h3>
              {videoSrc ? (
                <div className="video-block">
                  <video key={videoSrc} controls preload="metadata" className="case-video">
                    <source src={videoSrc} />
                    Your browser does not support video playback.
                  </video>
                  <div className="artifact-row" style={{ marginTop: 8 }}>
                    <div className="artifact-row-meta">
                      <strong>Video</strong>
                      <span title={videoAbs || undefined}>{videoAbs}</span>
                    </div>
                    {videoAbs ? <ArtifactDownload path={videoAbs} kind="videos" /> : null}
                  </div>
                  {typeof window !== 'undefined' && !window.location.protocol.startsWith('http') ? (
                    <p className="video-hint">
                      Tip: run <code>mobiflow serve</code> so videos and downloads work over HTTP.
                    </p>
                  ) : null}
                </div>
              ) : (
                <div className="empty" style={{ padding: 12 }}>
                  {c.mode === 'ai' ? (
                    <>
                      No video for this case yet. With <code>run.video: true</code> (default), MobiFlow
                      runs <code>maestro record --local</code> after the test on local devices. Re-run
                      the case (or <code>mobiflow test-flow</code>) to capture one.
                    </>
                  ) : (
                    <>
                      No video for this case. Keep <code>run.video: true</code> in{' '}
                      <code>mobiflow.config.yaml</code> for local <code>maestro record</code>, or use a
                      cloud provider that returns session video.
                    </>
                  )}
                </div>
              )}
            </div>

            <div>
              <h3 className="section-label">
                <FileCode2 size={12} strokeWidth={ICON_STROKE} /> Files
              </h3>
              {arts.length ? (
                <>
                  <div className="artifact-toolbar">
                    <span className="hint">{arts.length} artifact{arts.length === 1 ? '' : 's'}</span>
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => {
                        for (const a of arts) {
                          const url = artifactUrl(String(a.path))
                          const name = artifactBasename(String(a.path)) || 'artifact'
                          if (!canDownloadArtifact(url) || !url) continue
                          const link = document.createElement('a')
                          link.href = url
                          link.download = name
                          link.rel = 'noopener'
                          document.body.appendChild(link)
                          link.click()
                          link.remove()
                        }
                      }}
                      title="Download each available artifact (requires mobiflow serve)"
                    >
                      <Download size={12} strokeWidth={ICON_STROKE} />
                      Download all
                    </button>
                  </div>
                  <div className="artifact-list">
                    {arts.map((a) => (
                      <div className="artifact-row" key={a.path}>
                        <div className="artifact-row-meta">
                          <strong>{a.label}</strong>
                          <span title={a.path}>{a.path}</span>
                        </div>
                        <ArtifactDownload path={a.path} />
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty">No artifact paths recorded</div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function TestSuite({ data }: Props) {
  const cases = data.cases || []
  const [sel, setSel] = useState(cases[0]?.id || null)
  const [filter, setFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const current = useMemo(() => cases.find((c) => c.id === sel) || cases[0], [cases, sel])

  const counts = useMemo(() => {
    const passed = cases.filter((c) => isPassedStatus(c.status)).length
    const failed = cases.filter((c) => isFailedStatus(c.status)).length
    const video = cases.filter((c) => !!videoPathOf(c)).length
    return { all: cases.length, passed, failed, video }
  }, [cases])

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return cases.filter((c) => {
      if (statusFilter === 'passed' && !isPassedStatus(c.status)) return false
      if (statusFilter === 'failed' && !isFailedStatus(c.status)) return false
      if (statusFilter === 'video' && !videoPathOf(c)) return false
      if (!q) return true
      return [c.name, c.title, c.url, c.mode, c.status, ...(c.tags || [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(q)
    })
  }, [cases, filter, statusFilter])

  return (
    <div className="suite-layout">
      <div className="card suite-sidebar">
        <h2 className="card-title">
          <span className="icon">
            <Filter size={14} />
          </span>
          Suite ({visible.length})
        </h2>
        <div className="suite-search">
          <Search size={12} className="suite-search-icon" />
          <input
            className="field"
            placeholder="Search…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <div className="suite-filters">
          {(
            [
              ['all', `All ${counts.all}`],
              ['passed', `Pass ${counts.passed}`],
              ['failed', `Fail ${counts.failed}`],
              ['video', `Video ${counts.video}`],
            ] as Array<[StatusFilter, string]>
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`suite-filter${statusFilter === id ? ' active' : ''}`}
              onClick={() => setStatusFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="case-list">
          {visible.length === 0 ? (
            <div className="empty">No matching cases</div>
          ) : (
            visible.map((c) => (
              <button
                key={c.id}
                type="button"
                title={c.name}
                className={`case-item tone-${isFailedStatus(c.status) ? 'fail' : isPassedStatus(c.status) ? 'pass' : 'warn'}${
                  current?.id === c.id ? ' active' : ''
                }`}
                onClick={() => setSel(c.id)}
              >
                <StatusDot status={c.status} />
                <span className="case-name">{c.name}</span>
                {videoPathOf(c) ? (
                  <span className="case-video-badge" title="Has execution video">
                    <Video size={10} />
                  </span>
                ) : (
                  <span className="case-video-spacer" />
                )}
              </button>
            ))
          )}
        </div>
      </div>
      <CaseDetail key={current?.id || 'none'} c={current} />
    </div>
  )
}
