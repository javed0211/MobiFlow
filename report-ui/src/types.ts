export type TokenUsage = {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost: number
}

export type StepRecord = {
  index: number
  action: string
  status: string
  raw?: string
  detail?: string
  duration_ms?: number
  screenshot?: string | null
  url?: string | null
  value?: string | null
  locator?: string | null
}

export type PhaseStatus = {
  name: string
  status: string
  detail?: string
  duration_ms?: number
  usage?: TokenUsage
}

export type CaseRecord = {
  id: string
  name: string
  status: string
  mode: string
  url?: string
  tags?: string[]
  title?: string | null
  started_at?: string
  finished_at?: string
  duration_ms?: number
  phases?: PhaseStatus[]
  steps?: StepRecord[]
  explore_usage?: TokenUsage
  codegen_usage?: TokenUsage
  total_usage?: TokenUsage
  files_generated?: string[]
  heal_attempts?: number
  failure_output?: string
  errors?: string[]
  artifacts?: Record<string, unknown>
  source_case?: string | null
  /** Original test-case file text or explore prompt. */
  prompt?: string | null
}

export type EnvInfo = {
  generated_at?: string
  python?: string
  /** Host OS (Darwin / Linux / Windows). */
  platform?: string
  mobiflow_version?: string
  maestro?: string
  llm_provider?: string
  stack_tool?: string
  stack_language?: string
  stack_runner?: string
  repo_path?: string
  /** Device / simulator id or label. */
  device?: string
  /** Maestro appId. */
  app_id?: string
  /** ios | android */
  mobile_platform?: string
  /** local | browserstack | testmu | maestro */
  device_provider?: string
  explore_model?: string
  codegen_model?: string
  azure_endpoint?: string | null
}

export type PackSummary = {
  total: number
  passed: number
  failed: number
  skipped: number
  error: number
  duration_ms: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost: number
  pass_rate: number
}

export type TrendPoint = {
  label: string
  pass_rate: number
  duration_ms: number
  cost: number
  total: number
  passed: number
  failed: number
  at: string
  total_tokens?: number
  prompt_tokens?: number
  completion_tokens?: number
}

export type Insight = {
  severity: string
  title: string
  body: string
}

export type ReportPack = {
  id: string
  title: string
  generated_at: string
  env: EnvInfo
  summary: PackSummary
  cases: CaseRecord[]
  trends: TrendPoint[]
  insights: Insight[]
}

declare global {
  interface Window {
    __MOBIFLOW_REPORT__?: ReportPack | null
  }
}

export {}
