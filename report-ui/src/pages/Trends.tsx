import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ReportPack } from '../types'
import { fmtMoney, fmtTok } from '../format'
import { PageHeader } from '../components/PageHeader'
import { failureByHour, trendSeries } from '../derive'

const AXIS = { fill: '#5b6570', fontSize: 10 }
const TIP = { fontSize: 12, borderRadius: 8, borderColor: '#d8dee6' }

function heatColor(v: number, max: number) {
  if (!v) return '#f1f4f8'
  const t = Math.min(1, v / (max || 1))
  const from = [230, 244, 252]
  const to = [198, 40, 40]
  const mix = from.map((c, i) => Math.round(c + (to[i] - c) * t))
  return `rgb(${mix.join(',')})`
}

export function Trends({ data }: { data: ReportPack }) {
  const trends = trendSeries(data.trends || [])
  const heat = failureByHour(data)
  const hours = [0, 3, 6, 9, 12, 15, 18, 21]

  if (!trends.length) {
    return (
      <>
        <PageHeader title="Trends & Analytics" subtitle="Quality and performance over time" />
        <div className="card empty-state">
          <h3>No history yet</h3>
          <p>Run more packs to build trend history in .mobiflow/history.jsonl</p>
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Trends & Analytics"
        subtitle="Track quality trends and performance over time"
        actions={<span className="chip">Last {trends.length} runs</span>}
      />

      <div className="grid cols-2">
        <div className="card">
          <h3 className="card-cap">Pass Rate Trend</h3>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={trends} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="#e4e9f0" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={AXIS} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TIP} formatter={(v) => [`${v}%`, 'Pass rate']} />
              <Line type="monotone" dataKey="pass_rate" stroke="#1b883c" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="card-cap">Failure Trend</h3>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={trends} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="#e4e9f0" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TIP} formatter={(v) => [v, 'Failed']} />
              <Line type="monotone" dataKey="failed" stroke="#c62828" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="card-cap">Cases Executed</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={trends} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="#e4e9f0" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TIP} formatter={(v) => [v, 'Cases']} />
              <Bar dataKey="total" fill="#0074bf" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="card-cap">
            Execution Time Trend <em className="cap-note">(seconds)</em>
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={trends} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="#e4e9f0" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TIP} formatter={(v) => [`${v}s`, 'Duration']} />
              <Line type="monotone" dataKey="duration_s" stroke="#5b4dc7" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3 className="card-cap">Token Usage &amp; Cost Trend</h3>
        <p style={{ margin: '0 0 8px', fontSize: 12, color: 'var(--muted)' }}>
          Bars = total tokens · line = AI cost ($)
        </p>
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={trends} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
            <CartesianGrid stroke="#e4e9f0" strokeDasharray="3 3" />
            <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
            <YAxis
              yAxisId="tokens"
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v))}
            />
            <YAxis
              yAxisId="cost"
              orientation="right"
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${Number(v).toFixed(2)}`}
            />
            <Tooltip
              contentStyle={TIP}
              formatter={(value, name) => {
                const n = Number(value)
                if (name === 'Cost') return [fmtMoney(n), name]
                if (name === 'Prompt' || name === 'Completion' || name === 'Tokens') {
                  return [fmtTok(n), name]
                }
                return [n, String(name)]
              }}
            />
            <Bar
              yAxisId="tokens"
              dataKey="prompt_tokens"
              name="Prompt"
              stackId="tok"
              fill="#0074bf"
              radius={[0, 0, 0, 0]}
              isAnimationActive={false}
            />
            <Bar
              yAxisId="tokens"
              dataKey="completion_tokens"
              name="Completion"
              stackId="tok"
              fill="#7eb8de"
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
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3 className="card-cap">Failure Distribution by Hour</h3>
        <div className="heat">
          <div className="heat-hours">
            <span />
            {hours.map((h) => (
              <span key={h}>{String(h).padStart(2, '0')}:00</span>
            ))}
          </div>
          {heat.days.map((d, di) => (
            <div className="heat-row" key={d}>
              <span className="heat-day">{d}</span>
              <div className="heat-cells">
                {heat.grid[di].map((v, hi) => (
                  <i
                    key={hi}
                    style={{ background: heatColor(v, heat.max) }}
                    title={`${d} ${String(hi).padStart(2, '0')}:00 — ${v} failure(s)`}
                  />
                ))}
              </div>
            </div>
          ))}
          <div className="heat-legend">
            <span>Low</span>
            <i style={{ background: heatColor(0, heat.max) }} />
            <i style={{ background: heatColor(heat.max * 0.33, heat.max) }} />
            <i style={{ background: heatColor(heat.max * 0.66, heat.max) }} />
            <i style={{ background: heatColor(heat.max, heat.max) }} />
            <span>High</span>
          </div>
        </div>
      </div>
    </>
  )
}
