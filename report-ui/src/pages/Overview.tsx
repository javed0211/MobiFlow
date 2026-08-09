import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Coins,
  Download,
  GitCompare,
  Share2,
  Sparkles,
  TrendingUp,
  XCircle,
  Zap,
} from 'lucide-react'
import type { ReportPack } from '../types'
import { fmtMoney, fmtMs, fmtTok, shortAt } from '../format'
import {
  buildRecommendation,
  deltaPct,
  modeBreakdown,
  pct,
  topFailures,
  trendSeries,
  typeBreakdown,
  usageBreakdown,
} from '../derive'
import { Donut } from '../components/Donut'
import { flakyRows } from '../derive'

type Props = {
  data: ReportPack
  onNavigate: (id: 'failures' | 'flaky' | 'assistant' | 'results') => void
}

function Trend({ value, invert }: { value: number | null; invert?: boolean }) {
  if (value == null) return <span className="metric-trend flat">vs last run —</span>
  const good = invert ? value < 0 : value > 0
  const cls = value === 0 ? 'flat' : good ? 'up' : 'down'
  const sign = value > 0 ? '+' : ''
  return (
    <span className={`metric-trend ${cls}`}>
      {sign}
      {value}% vs last run
    </span>
  )
}

export function Overview({ data, onNavigate }: Props) {
  const s = data.summary
  const trends = trendSeries(data.trends || [])
  const prev = trends.length > 1 ? trends[trends.length - 2] : undefined
  const failures = topFailures(data.cases)
  const flaky = flakyRows(data).slice(0, 8)
  const modes = modeBreakdown(data.cases)
  const types = typeBreakdown(data.cases)
  const reco = buildRecommendation(data)
  const usage = usageBreakdown(data)
  const maxOcc = Math.max(1, ...failures.map((f) => f.occurrences))

  const skipped = s.skipped + (s.error || 0)
  const insights = data.insights || []
  const root = insights.find((i) => /fail|error|root|auth|payment/i.test(`${i.title} ${i.body}`)) || insights[0]
  const flakyIns = insights.find((i) => /flak|heal|unstable/i.test(`${i.title} ${i.body}`)) || insights[1]
  const risk = insights.find((i) => /risk|cost|token|duration/i.test(`${i.title} ${i.body}`)) || insights[2]

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.id || 'mobiflow-report'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadMd = () => {
    const lines = [
      `# ${data.title || 'MobiFlow Execution Report'}`,
      '',
      `- Pack: \`${data.id}\``,
      `- Generated: ${data.generated_at}`,
      `- Cases: ${s.total} · Passed: ${s.passed} · Failed: ${s.failed} · Pass rate: ${s.pass_rate}%`,
      '',
      '| Case | Status | Mode |',
      '| --- | --- | --- |',
      ...data.cases.map((c) => `| ${c.name} | ${c.status} | ${c.mode} |`),
      '',
      '_Exported from MobiFlow report UI_',
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.id || 'mobiflow-report'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      alert('Report URL copied to clipboard')
    } catch {
      alert('Unable to copy link from this context')
    }
  }

  return (
    <>
      <div className="topbar">
        <div className="title-block">
          <h1>
            Test Execution Report
            <span className="ai-pill">
              <Sparkles size={12} />
              AI Powered
            </span>
          </h1>
          <p className="meta-line">
            <span>Pack {data.id}</span>
            <span>{shortAt(data.generated_at)}</span>
            <span>
              Cases: <strong>{s.total}</strong>
            </span>
            {data.env.llm_provider ? <span>LLM: {data.env.llm_provider}</span> : null}
          </p>
        </div>
        <div className="actions">
          <span className="date-chip">
            <Clock3 size={13} />
            {shortAt(data.generated_at) || '—'}
          </span>
          <button type="button" className="btn" onClick={() => onNavigate('results')}>
            <GitCompare size={14} />
            Compare
          </button>
          <button type="button" className="btn" onClick={share}>
            <Share2 size={14} />
            Share Report
          </button>
          <button type="button" className="btn" onClick={downloadMd}>
            <Download size={14} />
            Export MD
          </button>
          <button type="button" className="btn primary" onClick={downloadJson}>
            <Download size={14} />
            Download Report
          </button>
        </div>
      </div>

      <div className="grid metrics">
        <div className="card metric">
          <div className="metric-top">
            <div>
              <div className="metric-label">Recorded Cases</div>
              <div className="metric-value">{s.total.toLocaleString()}</div>
              <Trend value={deltaPct(s.total, prev?.total)} />
            </div>
            <div className="metric-icon blue">
              <ClipboardList size={18} />
            </div>
          </div>
        </div>
        <div className="card metric">
          <div className="metric-top">
            <div>
              <div className="metric-label">Passed</div>
              <div className="metric-value">
                {s.passed.toLocaleString()}
                <span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 600 }}>
                  {' '}
                  / {pct(s.passed, s.total)}%
                </span>
              </div>
              <Trend value={deltaPct(s.passed, prev?.passed)} />
            </div>
            <div className="metric-icon green">
              <CheckCircle2 size={18} />
            </div>
          </div>
        </div>
        <div className="card metric">
          <div className="metric-top">
            <div>
              <div className="metric-label">Failed</div>
              <div className="metric-value">
                {s.failed.toLocaleString()}
                <span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 600 }}>
                  {' '}
                  / {pct(s.failed, s.total)}%
                </span>
              </div>
              <Trend value={deltaPct(s.failed, prev?.failed)} invert />
            </div>
            <div className="metric-icon red">
              <XCircle size={18} />
            </div>
          </div>
        </div>
        <div className="card metric">
          <div className="metric-top">
            <div>
              <div className="metric-label">Skipped</div>
              <div className="metric-value">
                {skipped.toLocaleString()}
                <span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 600 }}>
                  {' '}
                  / {pct(skipped, s.total)}%
                </span>
              </div>
              <Trend value={null} />
            </div>
            <div className="metric-icon amber">
              <AlertTriangle size={18} />
            </div>
          </div>
        </div>
        <div className="card metric">
          <div className="metric-top">
            <div>
              <div className="metric-label">Execution Time</div>
              <div className="metric-value">{fmtMs(s.duration_ms)}</div>
              <Trend value={deltaPct(s.duration_ms, prev?.duration_ms)} invert />
            </div>
            <div className="metric-icon blue">
              <Clock3 size={18} />
            </div>
          </div>
        </div>
        <div className="card metric">
          <div className="metric-top">
            <div>
              <div className="metric-label">Success Rate</div>
              <div className="metric-value">{s.pass_rate}%</div>
              <Trend value={deltaPct(s.pass_rate, prev?.pass_rate)} />
            </div>
            <div className="metric-icon purple">
              <TrendingUp size={18} />
            </div>
          </div>
        </div>
        <div className="card metric">
          <div className="metric-top">
            <div>
              <div className="metric-label">Tokens</div>
              <div className="metric-value">{fmtTok(usage.totalTok)}</div>
              <div className="metric-trend flat">
                {fmtTok(usage.prompt)} in · {fmtTok(usage.completion)} out
              </div>
            </div>
            <div className="metric-icon blue">
              <Zap size={18} />
            </div>
          </div>
        </div>
        <div className="card metric">
          <div className="metric-top">
            <div>
              <div className="metric-label">AI Cost</div>
              <div className="metric-value">{fmtMoney(usage.totalCost)}</div>
              <div className="metric-trend flat">sum of recorded cases</div>
            </div>
            <div className="metric-icon amber">
              <Coins size={18} />
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head">
          <h2>Token Usage &amp; Cost</h2>
          <span className="sub">Explore vs codegen · last {Math.max(trends.length, 1)} runs</span>
        </div>
        <div className="usage-strip">
          <div className="usage-chip">
            <span className="k">Explore</span>
            <span className="v">{fmtMoney(usage.exploreCost)}</span>
            <span className="s">{fmtTok(usage.exploreTok)} tokens · Discovery</span>
          </div>
          <div className="usage-chip">
            <span className="k">Codegen</span>
            <span className="v">{fmtMoney(usage.codegenCost)}</span>
            <span className="s">{fmtTok(usage.codegenTok)} tokens · Codegen</span>
          </div>
          <div className="usage-chip">
            <span className="k">Prompt / completion</span>
            <span className="v">
              {fmtTok(usage.prompt)} / {fmtTok(usage.completion)}
            </span>
            <span className="s">input · output tokens</span>
          </div>
          <div className="usage-chip">
            <span className="k">Pack total</span>
            <span className="v">{fmtMoney(usage.totalCost)}</span>
            <span className="s">{fmtTok(usage.totalTok)} tokens</span>
          </div>
        </div>
        {trends.length ? (
          <ResponsiveContainer width="100%" height={220} style={{ marginTop: 12 }}>
            <ComposedChart data={trends} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#e4e9f0" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fill: '#5b6570', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                yAxisId="tokens"
                tick={{ fill: '#5b6570', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v))}
              />
              <YAxis
                yAxisId="cost"
                orientation="right"
                tick={{ fill: '#5b6570', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => `$${Number(v).toFixed(2)}`}
              />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: '#d8dee6' }}
                formatter={(value, name) => {
                  const n = Number(value)
                  if (name === 'Cost') return [fmtMoney(n), name]
                  return [fmtTok(n), name]
                }}
              />
              <Bar
                yAxisId="tokens"
                dataKey="total_tokens"
                name="Tokens"
                fill="#0074bf"
                radius={[3, 3, 0, 0]}
                isAnimationActive={false}
              />
              <Line
                yAxisId="cost"
                type="monotone"
                dataKey="cost"
                name="Cost"
                stroke="#05b8b5"
                strokeWidth={2.5}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty" style={{ marginTop: 12 }}>
            No token/cost history yet — run more packs to build the trend
          </div>
        )}
      </div>

      <div className="grid mid" style={{ marginTop: 14 }}>
        <div className="card">
          <div className="card-head">
            <h2>Test Execution Trends</h2>
            <span className="sub">Last {Math.max(trends.length, 1)} runs</span>
          </div>
          {trends.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={trends} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#e4e9f0" strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fill: '#5b6570', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis
                  yAxisId="left"
                  tick={{ fill: '#5b6570', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[0, 100]}
                  tick={{ fill: '#5b6570', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: '#d8dee6' }} />
                <Area
                  yAxisId="right"
                  type="monotone"
                  dataKey="pass_rate"
                  name="Success Rate"
                  stroke="#0074bf"
                  fill="#0074bf22"
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="passed"
                  name="Passed"
                  stroke="#1b883c"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="failed"
                  name="Failed"
                  stroke="#c62828"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="skipped"
                  name="Skipped"
                  stroke="#c45c12"
                  strokeWidth={2}
                  strokeDasharray="4 3"
                  dot={{ r: 3 }}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty">No trend history yet</div>
          )}
        </div>

        <div className="card">
          <div className="card-head">
            <h2>AI Insights</h2>
            <span className="beta">BETA</span>
          </div>
          <div className="insight-list">
            <div className="insight-item">
              <div className="insight-icon root">
                <AlertTriangle size={16} />
              </div>
              <div>
                <h4>Root Cause Analysis</h4>
                <p>
                  {root ? (
                    <>
                      <strong>{root.title}.</strong> {root.body}
                    </>
                  ) : (
                    <>No root-cause signals in this pack.</>
                  )}
                </p>
                <button type="button" className="link" onClick={() => onNavigate('failures')}>
                  View failures →
                </button>
              </div>
            </div>
            <div className="insight-item">
              <div className="insight-icon flaky">
                <Sparkles size={16} />
              </div>
              <div>
                <h4>Flaky Test Detection</h4>
                <p>
                  {flakyIns ? (
                    <>
                      <strong>{flakyIns.title}.</strong> {flakyIns.body}
                    </>
                  ) : (
                    <>
                      <strong>{flaky.length} cases</strong> show heal retries or unstable pass patterns.
                    </>
                  )}
                </p>
                <button type="button" className="link" onClick={() => onNavigate('flaky')}>
                  View flaky →
                </button>
              </div>
            </div>
            <div className="insight-item">
              <div className="insight-icon risk">
                <TrendingUp size={16} />
              </div>
              <div>
                <h4>Risk Prediction</h4>
                <p>
                  {risk ? (
                    <>
                      <strong>{risk.title}.</strong> {risk.body}
                    </>
                  ) : (
                    <>
                      Success rate is <strong>{s.pass_rate}%</strong> with AI cost{' '}
                      <strong>${(s.cost || 0).toFixed(4)}</strong>.
                    </>
                  )}
                </p>
                <button type="button" className="link" onClick={() => onNavigate('assistant')}>
                  View AI analysis →
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid bottom" style={{ marginTop: 14 }}>
        <div className="card">
          <div className="card-head">
            <h3>Top Failures</h3>
          </div>
          <div className="table-wrap">
            {failures.length ? (
              <table className="data">
                <thead>
                  <tr>
                    <th>Test Name</th>
                    <th>Failure Reason</th>
                    <th>Since</th>
                    <th>Occ.</th>
                  </tr>
                </thead>
                <tbody>
                  {failures.map((f) => (
                    <tr key={f.id}>
                      <td>
                        <div className="cell-name">{f.name}</div>
                        <div className="cell-path">{f.path}</div>
                      </td>
                      <td>{f.reason}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{shortAt(f.since) || '—'}</td>
                      <td>
                        <div className="occ-bar" title={String(f.occurrences)}>
                          <i style={{ width: `${(f.occurrences / maxOcc) * 100}%` }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty">No failures in this pack</div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Top Flaky Tests</h3>
          </div>
          <div className="table-wrap">
            {flaky.length ? (
              <table className="data">
                <thead>
                  <tr>
                    <th>Test Name</th>
                    <th>Flaky</th>
                    <th>Pass</th>
                    <th>Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {flaky.map((f) => (
                    <tr key={f.id}>
                      <td>
                        <div className="cell-name">{f.name}</div>
                      </td>
                      <td>
                        <span className={`score ${f.flakyScore >= 50 ? 'bad' : 'ok'}`}>
                          {f.flakyScore}%
                        </span>
                      </td>
                      <td>
                        <span className={`score ${f.passRate >= 70 ? 'ok' : 'bad'}`}>{f.passRate}%</span>
                      </td>
                      <td>
                        <div className="spark">
                          <ResponsiveContainer width="100%" height={28}>
                            <LineChart data={f.spark.map((v, i) => ({ i, v }))}>
                              <Line
                                type="monotone"
                                dataKey="v"
                                stroke="#c62828"
                                strokeWidth={1.5}
                                dot={false}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty">No flaky signals detected</div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Results by Mode</h3>
          </div>
          {modes.length ? (
            <div className="donut-wrap">
              <Donut data={modes.map((m) => ({ name: m.name, value: m.value, color: m.color }))} />
              <div className="legend">
                {modes.map((m) => (
                  <div className="legend-row" key={m.name}>
                    <span className="legend-dot" style={{ background: m.color }} />
                    {m.name}
                    <strong>
                      {m.value} · {m.pct}%
                    </strong>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty">No mode data</div>
          )}

          <h3 className="section-label" style={{ marginTop: 12 }}>
            Results by Test Type
          </h3>
          <div className="type-bars">
            {types.map((t) => (
              <div className="type-row" key={t.name}>
                <div className="label">
                  <span>{t.name}</span>
                  <span>{t.total}</span>
                </div>
                <div className="stack">
                  <span style={{ width: `${pct(t.passed, t.total)}%`, background: '#1b883c' }} />
                  <span style={{ width: `${pct(t.failed, t.total)}%`, background: '#c62828' }} />
                  <span style={{ width: `${pct(t.skipped, t.total)}%`, background: '#c45c12' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="reco">
        <div className="reco-left">
          <div className="reco-bot">
            <Bot size={22} />
          </div>
          <div>
            <h3>
              AI Recommendation{' '}
              <span
                className="ai-pill"
                style={{ background: 'rgba(255,255,255,0.15)', color: '#fff', borderColor: 'transparent' }}
              >
                BETA
              </span>
            </h3>
            <p>{reco.text}</p>
          </div>
        </div>
        <div className="reco-actions">
          <h4>Recommended Actions</h4>
          <ol>
            {reco.actions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ol>
        </div>
        <button type="button" className="btn primary" onClick={() => onNavigate('failures')}>
          Review Failures
        </button>
      </div>
    </>
  )
}
