import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Bot, Coins, RefreshCw, Wand2 } from 'lucide-react'
import type { ReportPack } from '../types'
import { fmtMoney, fmtTok } from '../format'
import { KpiCard } from '../components/KpiCard'

type Props = { data: ReportPack }

export function AiAnalysis({ data }: Props) {
  const cases = data.cases || []
  const explore = cases.reduce((a, c) => a + (c.explore_usage?.cost || 0), 0)
  const codegen = cases.reduce((a, c) => a + (c.codegen_usage?.cost || 0), 0)
  const exploreTok = cases.reduce(
    (a, c) =>
      a +
      (c.explore_usage?.total_tokens ||
        (c.explore_usage?.prompt_tokens || 0) + (c.explore_usage?.completion_tokens || 0)),
    0,
  )
  const codegenTok = cases.reduce(
    (a, c) =>
      a +
      (c.codegen_usage?.total_tokens ||
        (c.codegen_usage?.prompt_tokens || 0) + (c.codegen_usage?.completion_tokens || 0)),
    0,
  )
  const healed = cases.filter((c) => (c.heal_attempts || 0) > 1)
  const byCost = [...cases].sort((a, b) => (b.total_usage?.cost || 0) - (a.total_usage?.cost || 0))

  const pie = [
    { name: 'Explore', value: Number(explore.toFixed(4)), color: '#0074bf' },
    { name: 'Codegen', value: Number(codegen.toFixed(4)), color: '#05b8b5' },
  ].filter((d) => d.value > 0)

  const bar = byCost.slice(0, 8).map((c) => ({
    name: c.name.length > 14 ? `${c.name.slice(0, 13)}…` : c.name,
    explore: Number((c.explore_usage?.cost || 0).toFixed(4)),
    codegen: Number((c.codegen_usage?.cost || 0).toFixed(4)),
  }))

  return (
    <div className="grid">
      <div className="grid kpi-row">
        <KpiCard icon={Bot} label="Explore spend" value={fmtMoney(explore)} sub={`${fmtTok(exploreTok)} tok · Discovery`} />
        <KpiCard icon={Wand2} label="Codegen spend" value={fmtMoney(codegen)} sub={`${fmtTok(codegenTok)} tok · Codegen`} />
        <KpiCard icon={RefreshCw} label="Heal retries" value={healed.length} sub="cases with >1 verify" />
        <KpiCard
          icon={Coins}
          label="Modes"
          value={`${cases.filter((c) => c.mode === 'ai').length} AI`}
          sub={`${cases.filter((c) => c.mode === 'scripted').length} scripted`}
        />
      </div>

      <div className="grid split-2">
        <div className="card chart-card">
          <h2 className="card-title">
            <span className="icon"><Coins size={15} /></span>
            Spend by phase
          </h2>
          {pie.length === 0 ? (
            <div className="empty">No AI cost data in this pack</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
                  {pie.map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 6, borderColor: '#dde1e6' }}
                  formatter={(v) => fmtMoney(Number(v))}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card chart-card">
          <h2 className="card-title">
            <span className="icon"><Bot size={15} /></span>
            Cost by case
          </h2>
          {bar.length === 0 ? (
            <div className="empty">No cases</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={bar} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid stroke="#dde1e6" strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fill: '#5b6570', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#5b6570', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6, borderColor: '#dde1e6' }} />
                <Bar dataKey="explore" stackId="a" fill="#0074bf" name="Explore" />
                <Bar dataKey="codegen" stackId="a" fill="#05b8b5" name="Codegen" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="grid split-2">
        <div className="card">
          <h2 className="card-title">
            <span className="icon"><Wand2 size={15} /></span>
            AI analysis
          </h2>
          <div className="insight-list">
            {(data.insights || []).map((ins, i) => (
              <div className={`insight ${ins.severity || ''}`} key={i}>
                <span className="insight-tag">{ins.severity || 'note'}</span>
                <h4>{ins.title}</h4>
                <p>{ins.body}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h2 className="card-title">
            <span className="icon"><Coins size={15} /></span>
            Token leaders
          </h2>
          <div className="leader-list">
            {byCost.length === 0 ? (
              <div className="empty">No token data yet</div>
            ) : (
              byCost.slice(0, 10).map((c) => (
                <div className="leader" key={c.id}>
                  <div style={{ minWidth: 0 }}>
                    <div className="n">{c.name}</div>
                    <div className="d">
                      explore {fmtMoney(c.explore_usage?.cost)} · codegen {fmtMoney(c.codegen_usage?.cost)}
                    </div>
                  </div>
                  <div className="c">{fmtMoney(c.total_usage?.cost)}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
