import { useState } from 'react'
import {
  CircleAlert,
  Clock3,
  Copy,
  ExternalLink,
  Filter,
  Flame,
  Globe2,
  Lightbulb,
  ListChecks,
  OctagonAlert,
  RefreshCw,
  Search,
  Ticket,
  TriangleAlert,
} from 'lucide-react'
import type { ReportPack } from '../types'
import { shortAt } from '../format'
import { PageHeader } from '../components/PageHeader'
import { failureCards, failureCategories } from '../derive'
import { artifactUrl } from '../artifacts'

function ConfidenceRing({ value, tone }: { value: number; tone: string }) {
  const r = 18
  const circ = 2 * Math.PI * r
  const color = tone === 'Critical' ? '#c62828' : tone === 'Regression' ? '#c45c12' : '#0074bf'
  return (
    <svg width="52" height="52" viewBox="0 0 44 44" className="conf-ring">
      <circle cx="22" cy="22" r={r} fill="none" stroke="#eef1f5" strokeWidth="4" />
      <circle
        cx="22"
        cy="22"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="4"
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={circ - (circ * value) / 100}
        transform="rotate(-90 22 22)"
      />
      <text x="22" y="26" textAnchor="middle" fontSize="11" fontWeight="700" fill="#0d1846">
        {value}%
      </text>
    </svg>
  )
}

function SeverityIcon({ severity }: { severity: string }) {
  if (severity === 'Critical') return <OctagonAlert size={12} />
  if (severity === 'Flaky') return <RefreshCw size={12} />
  return <TriangleAlert size={12} />
}

function CategoryIcon({ id }: { id: string }) {
  if (id === 'Critical') return <Flame size={14} />
  if (id === 'Regression') return <TriangleAlert size={14} />
  if (id === 'Flaky') return <RefreshCw size={14} />
  return <CircleAlert size={14} />
}

function openTrace(tracePath: string | null) {
  if (!tracePath) return
  const name = tracePath.split(/[/\\]/).pop()
  if (!name) return
  const candidate = `${window.location.origin}/traces/${name}`
  if (window.location.protocol.startsWith('http')) {
    window.open(`https://maestro.mobile.dev/?trace=${encodeURIComponent(candidate)}`, '_blank')
    return
  }
  const cmd = `maestro "${tracePath}"`
  navigator.clipboard?.writeText(cmd)
  alert(`Trace command copied:\n${cmd}\n\nOr run: mobiflow serve`)
}

function copyIssuePayload(
  f: {
    name: string
    reason?: string
    evidence: string[]
    recommendation: string
    tracePath: string | null
  },
  packId: string,
) {
  const text = [
    `[MobiFlow] ${f.name} failed`,
    `Pack: ${packId}`,
    '',
    `Root cause: ${f.reason || 'See evidence'}`,
    '',
    'Evidence:',
    ...f.evidence.map((e) => `- ${e}`),
    '',
    `Recommendation: ${f.recommendation}`,
    f.tracePath ? `Trace: ${f.tracePath}` : '',
    '',
    '# Track in your issue tracker --provider jira --case <id>',
    '         or: mobiflow issue --provider azure-devops --case <id>',
  ]
    .filter(Boolean)
    .join('\n')
  navigator.clipboard?.writeText(text)
}

export function Failures({ data }: { data: ReportPack }) {
  const cards = failureCards(data)
  const cats = failureCategories(data)
  const [cat, setCat] = useState('all')

  const visible = cat === 'all' ? cards : cards.filter((c) => c.severity === cat)

  const copyAll = async () => {
    const text = cards
      .map((c) => `${c.severity} · ${c.name}\nRoot cause: ${c.reason}\n${c.evidence.join('\n')}`)
      .join('\n\n')
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <>
      <PageHeader
        title="Failures & Root Cause Analysis"
        subtitle="Failure investigation and categorisation from run artifacts"
        actions={
          <button type="button" className="btn" onClick={copyAll} disabled={!cards.length}>
            <Copy size={14} />
            Copy all
          </button>
        }
      />

      <div className="card cat-bar">
        {cats.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`cat${cat === c.id ? ' active' : ''}`}
            onClick={() => setCat(c.id)}
          >
            <span className="cat-icon">
              <CategoryIcon id={c.id} />
            </span>
            <span className="cat-count">{c.count}</span>
            <span className="cat-label">{c.label}</span>
          </button>
        ))}
      </div>

      <div key={cat} className="tab-pane">
      {visible.length === 0 ? (
        <div className="card empty-state">
          <CircleAlert size={26} />
          <h3>No failures in this pack</h3>
          <p>
            All {data.summary.total} cases passed. Root cause analysis appears here when a case fails
            or errors.
          </p>
        </div>
      ) : (
        visible.map((f) => (
          <div className="card fail-card" key={f.id}>
            <div className="fail-main">
              <span className={`sev ${f.severity.toLowerCase()}`}>
                <SeverityIcon severity={f.severity} />
                {f.severity}
              </span>
              <h3 className="fail-name">{f.name}</h3>
              <div className="fail-id">{f.testId}</div>

              <div className="fail-meta">
                <div>
                  <span>
                    <Globe2 size={11} /> Target
                  </span>
                  <strong>{f.module}</strong>
                </div>
                <div>
                  <span>
                    <Clock3 size={11} /> First occurred
                  </span>
                  <strong>{shortAt(f.firstOccurred) || '—'}</strong>
                </div>
                <div>
                  <span>
                    <RefreshCw size={11} /> Attempts
                  </span>
                  <strong>{f.occurrences}</strong>
                </div>
              </div>

              <div className="fail-reason">
                <span>
                  <Search size={12} /> Why it failed
                </span>
                <p>{f.reason}</p>
              </div>

              <div className="fail-evidence">
                <span>
                  <ListChecks size={12} /> Evidence
                </span>
                <ul>
                  {f.evidence.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="fail-conf">
              <span>Confidence</span>
              <ConfidenceRing value={f.confidence} tone={f.severity} />
            </div>

            <div className="fail-action">
              <h4>
                <Lightbulb size={13} /> Recommended Action
              </h4>
              <p>{f.recommendation}</p>
              {f.failedStep ? <div className="fail-step">{f.failedStep}</div> : null}
              {f.screenshotPath && artifactUrl(f.screenshotPath, 'screenshots') ? (
                <a
                  href={artifactUrl(f.screenshotPath, 'screenshots') || undefined}
                  target="_blank"
                  rel="noreferrer"
                  title={f.screenshotPath}
                >
                  <img
                    key={f.screenshotPath}
                    className="fail-shot"
                    alt="Failure screenshot"
                    src={artifactUrl(f.screenshotPath, 'screenshots') || undefined}
                    style={{
                      width: '100%',
                      maxHeight: 220,
                      objectFit: 'cover',
                      borderRadius: 8,
                      border: '1px solid #e2e8f0',
                      marginBottom: 8,
                    }}
                  />
                </a>
              ) : null}
              {f.videoPath && artifactUrl(f.videoPath, 'videos') ? (
                <video
                  key={f.videoPath}
                  controls
                  preload="metadata"
                  className="fail-video"
                  src={artifactUrl(f.videoPath, 'videos') || undefined}
                />
              ) : null}
              <button
                type="button"
                className="btn soft"
                onClick={() =>
                  navigator.clipboard?.writeText(
                    [`Root cause: ${f.reason}`, ...f.evidence].join('\n'),
                  )
                }
              >
                <Copy size={13} />
                Copy evidence
              </button>
              <button
                type="button"
                className="btn soft"
                disabled={!f.tracePath}
                title={f.tracePath || 'No trace recorded'}
                onClick={() => openTrace(f.tracePath)}
              >
                <ExternalLink size={13} />
                Open trace
              </button>
              <button
                type="button"
                className="btn soft"
                onClick={() => copyIssuePayload(f, data.id)}
              >
                <Ticket size={13} />
                Copy issue draft
              </button>
            </div>
          </div>
        ))
      )}
      </div>

      {cards.length ? (
        <div className="foot-note">
          <Filter size={12} />
          Showing {visible.length} of {cards.length} failures · serve traces with{' '}
          <code>mobiflow serve</code>
        </div>
      ) : null}
    </>
  )
}
