import type { LucideIcon } from 'lucide-react'

type Props = {
  label: string
  value: string | number
  sub?: string
  tone?: 'pass' | 'fail' | 'warn' | ''
  icon?: LucideIcon
}

export function KpiCard({ label, value, sub, tone = '', icon: Icon }: Props) {
  return (
    <div className="card kpi">
      <div className="kpi-label">
        {Icon ? <Icon size={13} strokeWidth={1.5} /> : null}
        {label}
      </div>
      <div className={`kpi-value ${tone}`}>{value}</div>
      {sub ? <div className="kpi-sub">{sub}</div> : null}
    </div>
  )
}
