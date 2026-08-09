import {
  Boxes,
  ClipboardList,
  FileBarChart2,
  FlaskConical,
  LayoutDashboard,
  LineChart,
  Settings,
  XCircle,
} from 'lucide-react'
import type { ReportPack } from '../types'
import { Logo } from './Logo'
import { AiMark } from './AiMark'
import { flakyRows } from '../derive'

export type NavId =
  | 'overview'
  | 'results'
  | 'trends'
  | 'failures'
  | 'flaky'
  | 'assistant'
  | 'environments'
  | 'reports'
  | 'settings'

type Props = {
  data: ReportPack
  page: NavId
  onNavigate: (id: NavId) => void
}

export function Sidebar({ data, page, onNavigate }: Props) {
  const failed = data.summary.failed + (data.summary.error || 0)
  const flaky = flakyRows(data).length

  const items: Array<{
    id: NavId
    label: string
    icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>
    badge?: number
    tone?: 'fail' | 'warn'
  }> = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'results', label: 'Test Results', icon: ClipboardList },
    { id: 'trends', label: 'Trends', icon: LineChart },
    { id: 'failures', label: 'Failures', icon: XCircle, badge: failed || undefined, tone: 'fail' },
    { id: 'flaky', label: 'Flaky Tests', icon: FlaskConical, badge: flaky || undefined, tone: 'warn' },
    { id: 'assistant', label: 'AI Insights', icon: AiMark },
    { id: 'environments', label: 'Environments', icon: Boxes },
    { id: 'reports', label: 'Reports', icon: FileBarChart2 },
    { id: 'settings', label: 'Settings', icon: Settings },
  ]

  return (
    <aside className="sidebar">
      <div className="brand-row">
        <div className="brand-mark" aria-hidden="true">
          <Logo size={32} />
        </div>
        <div className="brand-text">
          <strong className="brand-name">
            <span className="brand-web">Mobi</span>
            <span className="brand-qa">Flow</span>
          </strong>
        </div>
      </div>

      <nav className="nav-list">
        {items.map(({ id, label, icon: Icon, badge, tone }) => (
          <button
            key={id}
            type="button"
            className={`nav-item${page === id ? ' active' : ''}`}
            onClick={() => onNavigate(id)}
          >
            <Icon size={15} strokeWidth={1.6} />
            {label}
            {badge ? <span className={`badge-count ${tone || ''}`}>{badge}</span> : null}
          </button>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="foot-avatar">
          <AiMark size={14} />
        </div>
        <div className="foot-text">
          <strong>{data.env.llm_provider || 'local'}</strong>
          <span>{data.env.codegen_model || data.env.explore_model || 'no model'}</span>
        </div>
      </div>
    </aside>
  )
}
