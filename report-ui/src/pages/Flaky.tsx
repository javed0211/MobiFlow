import { Line, LineChart, ResponsiveContainer } from 'recharts'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FlaskConical,
  Gauge,
  Globe2,
  Lightbulb,
  ListChecks,
  Percent,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReportPack } from '../types'
import { shortAt } from '../format'
import { PageHeader } from '../components/PageHeader'
import { flakyRows, flakySummary, targetOutcomes, recentCaseOutcomes, dailyPassHeatmap } from '../derive'

function outcomeColor(passRate: number, ok: boolean) {
  if (ok || passRate >= 100) return '#1b883c'
  if (passRate >= 70) return '#7cb342'
  if (passRate >= 50) return '#e0a53f'
  if (passRate > 0) return '#e2703a'
  return '#c62828' // failed — never look like "empty"
}

function dailyColor(passRate: number) {
  if (passRate >= 90) return '#1b883c'
  if (passRate >= 70) return '#7cb342'
  if (passRate >= 50) return '#e0a53f'
  if (passRate > 0) return '#e2703a'
  return '#c62828'
}

function PatternIcon({ pattern }: { pattern: string }) {
  const p = pattern.toLowerCase()
  if (p.includes('recover') || p.includes('heal')) return <CheckCircle2 size={12} />
  if (p.includes('intermitt')) return <Activity size={12} />
  return <AlertTriangle size={12} />
}

export function Flaky({ data }: { data: ReportPack }) {
  const rows = flakyRows(data)
  const sum = flakySummary(data)
  const targets = targetOutcomes(data)
  const outcomes = recentCaseOutcomes(data)
  const daily = dailyPassHeatmap(data)

  const cards: Array<{ label: string; value: string | number; note: string; icon: LucideIcon }> = [
    { label: 'Flaky Cases', value: sum.totalFlaky, note: 'needed retries or failed', icon: FlaskConical },
    { label: 'Flaky Rate', value: `${sum.flakyRate}%`, note: 'of all cases in pack', icon: Percent },
    { label: 'High Risk', value: sum.highRisk, note: 'score 70 or above', icon: ShieldAlert },
    { label: 'Recovered', value: sum.recovered, note: 'passed after self-heal', icon: CheckCircle2 },
  ]

  return (
    <>
      <PageHeader
        title="Flaky Tests Intelligence"
        subtitle="Cases that needed self-healing or produced unstable results"
        actions={
          <span className="chip">
            <FlaskConical size={12} />
            {rows.length} tracked
          </span>
        }
      />

      <div className="grid cols-4">
        {cards.map((c) => {
          const Icon = c.icon
          return (
            <div className="card stat" key={c.label}>
              <div className="stat-label">
                <Icon size={12} />
                {c.label}
              </div>
              <div className="stat-row">
                <span className="stat-value">{c.value}</span>
              </div>
              <div className="stat-sub">{c.note}</div>
            </div>
          )
        })}
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3 className="card-cap">
          <ListChecks size={14} /> Flaky Cases
        </h3>
        <div className="table-wrap">
          {rows.length ? (
            <table className="data">
              <thead>
                <tr>
                  <th>Test Name</th>
                  <th>Flaky Score</th>
                  <th>Failure Pattern</th>
                  <th>Target</th>
                  <th>Last Run</th>
                  <th>Trend</th>
                  <th>Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="cell-name">
                      <span className="cell-with-icon">
                        <FlaskConical size={12} />
                        {r.name}
                      </span>
                    </td>
                    <td>
                      <span className={`score ${r.flakyScore >= 70 ? 'bad' : 'ok'}`}>
                        <Gauge size={11} />
                        {r.flakyScore}%
                      </span>
                    </td>
                    <td>
                      <span className="cell-with-icon muted">
                        <PatternIcon pattern={r.pattern} />
                        {r.pattern}
                      </span>
                    </td>
                    <td>
                      <span className="cell-with-icon muted">
                        <Globe2 size={12} />
                        {r.environment}
                      </span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="cell-with-icon muted">
                        <Clock3 size={12} />
                        {shortAt(r.lastFailed) || '—'}
                      </span>
                    </td>
                    <td>
                      <div className="spark" title="Recent pass/fail trend">
                        <ResponsiveContainer width="100%" height={28}>
                          <LineChart data={r.spark.map((v, i) => ({ i, v }))}>
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
                    <td>
                      <span className="cell-with-icon muted">
                        <Lightbulb size={12} />
                        {r.recommendation}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <FlaskConical size={24} />
              <h3>No flaky cases detected</h3>
              <p>Every case passed on its first attempt with no self-heal retries.</p>
            </div>
          )}
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <div className="card">
          <h3 className="card-cap">
            <TrendingUp size={14} /> Recent case outcomes
          </h3>
          <p className="hint-text" style={{ marginTop: 0, marginBottom: 10 }}>
            Each cell is one case run from history (pass or fail) — not a pack-level week.
          </p>
          {outcomes.length ? (
            <div className="outcome-heat">
              <div className="outcome-heat-cells">
                {outcomes.map((c, i) => (
                  <button
                    type="button"
                    className="outcome-cell"
                    key={`${c.label}-${c.at}-${i}`}
                    style={{ background: outcomeColor(c.passRate, c.ok) }}
                    title={`${c.label}\n${shortAt(c.at)} — ${c.ok ? 'passed' : 'failed'} (${c.passRate}%)`}
                  >
                    <span className="outcome-cell-label">{c.label}</span>
                  </button>
                ))}
              </div>
              <div className="heat-legend">
                <span>Failed</span>
                <i style={{ background: outcomeColor(0, false) }} />
                <i style={{ background: dailyColor(50) }} />
                <i style={{ background: dailyColor(80) }} />
                <i style={{ background: outcomeColor(100, true) }} />
                <span>Passed</span>
              </div>
            </div>
          ) : (
            <div className="empty">No case history yet — run cases to populate this.</div>
          )}

          {daily.length > 1 ? (
            <div className="daily-heat" style={{ marginTop: 16 }}>
              <h4 className="section-label" style={{ marginBottom: 8 }}>
                Pass rate by day
              </h4>
              <div className="daily-heat-row">
                {daily.map((d) => (
                  <div className="daily-heat-item" key={d.day}>
                    <i
                      style={{ background: dailyColor(d.passRate) }}
                      title={`${d.day}: ${d.passRate}% (${d.passed}/${d.total})`}
                    />
                    <span>{d.day.slice(5)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="card">
          <h3 className="card-cap">
            <Globe2 size={14} /> Outcomes by target
          </h3>
          <p className="hint-text" style={{ marginTop: 0, marginBottom: 10 }}>
            Pass / fail per site (not case-count share — that is often 1 each).
          </p>
          {targets.length ? (
            <div className="target-outcomes">
              {targets.map((t) => (
                <div className="target-outcome-row" key={t.name}>
                  <div className="target-outcome-head">
                    <span className="target-outcome-name" title={t.name}>
                      {t.name}
                    </span>
                    <strong>
                      {t.passRate}% · {t.passed} pass / {t.failed} fail
                      {t.healed ? ` · ${t.healed} healed` : ''}
                    </strong>
                  </div>
                  <div className="target-outcome-bar" title={`${t.passed} passed, ${t.failed} failed`}>
                    <i
                      className="pass"
                      style={{ width: `${t.total ? (100 * t.passed) / t.total : 0}%` }}
                    />
                    <i
                      className="fail"
                      style={{ width: `${t.total ? (100 * t.failed) / t.total : 0}%` }}
                    />
                  </div>
                </div>
              ))}
              <div className="heat-legend" style={{ marginTop: 8 }}>
                <span>Failed</span>
                <i style={{ background: '#c62828' }} />
                <i style={{ background: '#1b883c' }} />
                <span>Passed</span>
              </div>
            </div>
          ) : (
            <div className="empty">No cases in this pack</div>
          )}
        </div>
      </div>
    </>
  )
}
