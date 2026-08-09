import { useState } from 'react'
import type { ReportPack } from './types'
import { Sidebar, type NavId } from './components/Sidebar'
import { Overview } from './pages/Overview'
import { TestResults } from './pages/TestResults'
import { Failures } from './pages/Failures'
import { Trends } from './pages/Trends'
import { Flaky } from './pages/Flaky'
import { Assistant } from './pages/Assistant'
import { SimplePage } from './pages/SimplePage'

export default function App({ data }: { data: ReportPack }) {
  const [page, setPage] = useState<NavId>('overview')

  return (
    <div className="shell">
      <Sidebar data={data} page={page} onNavigate={setPage} />
      <main className="main">
        {page === 'overview' ? <Overview data={data} onNavigate={setPage} /> : null}
        {page === 'results' ? <TestResults data={data} /> : null}
        {page === 'trends' ? <Trends data={data} /> : null}
        {page === 'failures' ? <Failures data={data} /> : null}
        {page === 'flaky' ? <Flaky data={data} /> : null}
        {page === 'assistant' ? <Assistant data={data} /> : null}
        {page === 'environments' ? (
          <SimplePage title="Environments" subtitle="Device, runtime and Maestro stack" data={data} mode="env" />
        ) : null}
        {page === 'reports' ? (
          <SimplePage title="Reports" subtitle="Current pack export" data={data} mode="reports" />
        ) : null}
        {page === 'settings' ? (
          <SimplePage title="Settings" subtitle="Report generation details" data={data} mode="settings" />
        ) : null}
      </main>
    </div>
  )
}
