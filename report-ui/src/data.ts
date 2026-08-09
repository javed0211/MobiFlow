import type { ReportPack } from './types'

const DEMO: ReportPack = {
  id: 'demo',
  title: 'MobiFlow Regression Pack',
  generated_at: new Date().toISOString(),
  env: {
    python: '3.12.11',
    platform: 'Darwin arm64',
    mobiflow_version: '0.2.0',
    maestro: '1.39.0',
    llm_provider: 'azure',
    stack_tool: 'maestro',
    stack_language: 'yaml+js',
    stack_runner: 'maestro',
    repo_path: '/demo/repo',
    device: 'iPhone 16 Pro',
    app_id: 'org.wikimedia.wikipedia',
    mobile_platform: 'ios',
    device_provider: 'local',
  },
  summary: {
    total: 2,
    passed: 2,
    failed: 0,
    skipped: 0,
    error: 0,
    duration_ms: 18000,
    prompt_tokens: 12000,
    completion_tokens: 800,
    total_tokens: 12800,
    cost: 0.12,
    pass_rate: 100,
  },
  cases: [],
  trends: [
    { label: '1', pass_rate: 80, duration_ms: 20000, cost: 0.2, total: 2, passed: 1, failed: 1, at: '2026-07-20T10:00:00Z' },
    { label: '2', pass_rate: 100, duration_ms: 16000, cost: 0.1, total: 2, passed: 2, failed: 0, at: '2026-07-22T10:00:00Z' },
    { label: 'now', pass_rate: 100, duration_ms: 18000, cost: 0.12, total: 2, passed: 2, failed: 0, at: new Date().toISOString() },
  ],
  insights: [
    { severity: 'pass', title: 'Pass rate 100%', body: 'All cases passed in this pack.' },
  ],
}

export function loadReport(): ReportPack {
  return window.__MOBIFLOW_REPORT__ ?? DEMO
}
