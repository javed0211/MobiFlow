import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

type Props = {
  title: string
  subtitle?: string
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </div>
  )
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
}: {
  items: Array<{ id: T; label: string; icon?: LucideIcon }>
  value: T
  onChange: (id: T) => void
}) {
  return (
    <div className="tabbar">
      {items.map((t) => {
        const Icon = t.icon
        return (
          <button
            key={t.id}
            type="button"
            className={`tab${value === t.id ? ' active' : ''}`}
            onClick={() => onChange(t.id)}
          >
            {Icon ? <Icon size={14} /> : null}
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
