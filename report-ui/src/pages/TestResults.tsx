import { useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Boxes, ClipboardList, Download, Filter, LayoutDashboard, Package, Share2 } from 'lucide-react'
import type { ReportPack } from '../types'
import { fmtMoney, fmtMs, shortAt } from '../format'
import { PageHeader, Tabs } from '../components/PageHeader'
import { pct, recentExecutions, trendSeries } from '../derive'
import { TestSuite } from './TestSuite'
import { SimplePage } from './SimplePage'

type Tab = 'summary' | 'tests' | 'environments' | 'artifacts'

export function TestResults({ data }: { data: ReportPack }) {
  const [tab, setTab] = useState<Tab>('summary')
  const s = data.summary
  const trends = trendSeries(data.trends || [])
  const runs = recentExecutions(data)
  const skipped = s.skipped + (s.error || 0)

  const download = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.id || 'mobiflow-report'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
    } catch {
      /* clipboard unavailable in this context */
    }
  }

  const cards = [
    { label: 'Total Cases', value: s.total.toLocaleString(), note: '', tone: '' },
    { label: 'Passed', value: s.passed.toLocaleString(), note: `${pct(s.passed, s.total)}%`, tone: 'pass' },
    { label: 'Failed', value: s.failed.toLocaleString(), note: `${pct(s.failed, s.total)}%`, tone: 'fail' },
    { label: 'Skipped', value: skipped.toLocaleString(), note: `${pct(skipped, s.total)}%`, tone: 'warn' },
    { label: 'Success Rate', value: `${s.pass_rate}%`, note: '', tone: '' },
  ]

  return (
    <>
      <PageHeader
        title="Test Execution Report"
        subtitle={`Pack ${data.id} · ${shortAt(data.generated_at)} · ${data.env.llm_provider || 'local'}`}
        actions={
          <>
            <button type="button" className="btn" onClick={share}>
              <Share2 size={14} />
              Share
            </button>
            <button type="button" className="btn" onClick={download}>
              <Download size={14} />
              Export
            </button>
          </>
        }
      />

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { id: 'summary', label: 'Summary', icon: LayoutDashboard },
          { id: 'tests', label: 'Tests', icon: ClipboardList },
          { id: 'environments', label: 'Environment', icon: Boxes },
          { id: 'artifacts', label: 'Artifacts', icon: Package },
        ]}
      />

      {tab === 'summary' ? (
        <>
          <div className="grid cols-5">
            {cards.map((c) => (
              <div className="card stat" key={c.label}>
                <div className="stat-label">{c.label}</div>
                <div className="stat-row">
                  <span className="stat-value">{c.value}</span>
                  {c.note ? <span className={`stat-note ${c.tone}`}>{c.note}</span> : null}
                </div>
              </div>
            ))}
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <div className="card-head">
              <h3 className="card-cap">Results Over Time</h3>
              <span className="chip">Last {trends.length} runs</span>
            </div>
            {trends.length ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trends} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid stroke="#e4e9f0" strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fill: '#5b6570', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis
                    yAxisId="left"
                    allowDecimals={false}
                    tick={{ fill: '#5b6570', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
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
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line yAxisId="left" type="monotone" dataKey="passed" name="Passed" stroke="#1b883c" strokeWidth={2} dot={{ r: 3 }}  isAnimationActive={false} />
                  <Line yAxisId="left" type="monotone" dataKey="failed" name="Failed" stroke="#c62828" strokeWidth={2} dot={{ r: 3 }}  isAnimationActive={false} />
                  <Line yAxisId="left" type="monotone" dataKey="skipped" name="Skipped" stroke="#e0a53f" strokeWidth={2} dot={{ r: 3 }}  isAnimationActive={false} />
                  <Line yAxisId="right" type="monotone" dataKey="pass_rate" name="Success Rate (%)" stroke="#0074bf" strokeWidth={2} dot={{ r: 3 }}  isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty">No run history yet</div>
            )}
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <div className="card-head">
              <h3 className="card-cap">Recent Executions</h3>
              <span className="chip">
                <Filter size={12} />
                {runs.length} runs
              </span>
            </div>
            <div className="table-wrap">
              {runs.length ? (
                <table className="data">
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Case</th>
                      <th>Result</th>
                      <th>Duration</th>
                      <th>Cost</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.key}>
                        <td>
                          <span className={`run-tag${r.current ? ' current' : ''}`}>
                            {r.current ? 'current' : 'previous'}
                          </span>
                        </td>
                        <td>
                          <div className="cell-name">{r.case}</div>
                        </td>
                        <td>
                          {r.passed ? (
                            <span style={{ color: 'var(--pass)', fontWeight: 700 }}>passed</span>
                          ) : (
                            <span style={{ color: 'var(--fail)', fontWeight: 700 }}>failed</span>
                          )}
                        </td>
                        <td>{fmtMs(r.duration_ms)}</td>
                        <td>{fmtMoney(r.cost)}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{shortAt(r.at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty">No previous executions recorded</div>
              )}
            </div>
          </div>
        </>
      ) : null}

      {tab === 'tests' ? <TestSuite data={data} /> : null}
      {tab === 'environments' ? (
        <SimplePage title="" subtitle="" data={data} mode="env" bare />
      ) : null}
      {tab === 'artifacts' ? (
        <SimplePage title="" subtitle="" data={data} mode="artifacts" bare />
      ) : null}
    </>
  )
}
