import type { CaseRecord, ReportPack, TrendPoint } from './types'

export function pct(part: number, total: number): number {
  if (!total) return 0
  return Math.round((1000 * part) / total) / 10
}

export function deltaPct(current: number, previous: number | undefined): number | null {
  if (previous == null || previous === 0) return null
  return Math.round(((current - previous) / Math.abs(previous)) * 1000) / 10
}

export function hostOf(c: CaseRecord): string {
  const raw = (c.url || '').trim()
  if (raw && !/^(ios|android)$/i.test(raw)) {
    // Packs often store Maestro appId in `url` for compatibility.
    if (!/^https?:\/\//i.test(raw)) return raw
    try {
      return new URL(raw).hostname.replace(/^www\./, '')
    } catch {
      return raw
    }
  }
  return c.mode || c.name || 'unknown'
}

export function isFailed(c: CaseRecord): boolean {
  return c.status === 'failed' || c.status === 'error'
}

export function trendSeries(trends: TrendPoint[]) {
  return (trends || []).map((t, i, arr) => ({
    ...t,
    label:
      i === arr.length - 1
        ? 'now'
        : new Date(t.at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    skipped: Math.max(0, (t.total || 0) - (t.passed || 0) - (t.failed || 0)),
    duration_s: Math.round((t.duration_ms || 0) / 100) / 10,
    total_tokens: t.total_tokens || 0,
    prompt_tokens: t.prompt_tokens || 0,
    completion_tokens: t.completion_tokens || 0,
    cost: Number((t.cost || 0).toFixed(4)),
  }))
}

/** Pack-level explore vs codegen token/cost split (from per-case usage). */
export function usageBreakdown(pack: ReportPack) {
  const cases = pack.cases || []
  const exploreCost = cases.reduce((a, c) => a + (c.explore_usage?.cost || 0), 0)
  const codegenCost = cases.reduce((a, c) => a + (c.codegen_usage?.cost || 0), 0)
  const exploreTok = cases.reduce((a, c) => a + (c.explore_usage?.total_tokens || 0), 0)
  const codegenTok = cases.reduce((a, c) => a + (c.codegen_usage?.total_tokens || 0), 0)
  const prompt = pack.summary.prompt_tokens || 0
  const completion = pack.summary.completion_tokens || 0
  return {
    exploreCost,
    codegenCost,
    exploreTok,
    codegenTok,
    prompt,
    completion,
    totalTok: pack.summary.total_tokens || exploreTok + codegenTok,
    totalCost: pack.summary.cost || exploreCost + codegenCost,
  }
}

/* ---------- page 1: overview ---------- */

export function releaseConfidence(pack: ReportPack) {
  const s = pack.summary
  const healed = pack.cases.filter((c) => (c.heal_attempts || 0) > 1).length
  let score = s.pass_rate
  score -= s.failed * 8
  score -= (s.error || 0) * 12
  score -= healed * 4
  score = Math.max(0, Math.min(100, Math.round(score)))

  const verdict =
    score >= 85 ? 'Good to Release' : score >= 65 ? 'Release with Care' : 'Not Ready to Release'
  const tone: 'pass' | 'warn' | 'fail' = score >= 85 ? 'pass' : score >= 65 ? 'warn' : 'fail'
  return { score, verdict, tone }
}

export function aiSummaryLines(pack: ReportPack): string[] {
  const s = pack.summary
  const healed = pack.cases.filter((c) => (c.heal_attempts || 0) > 1)
  const aiCases = pack.cases.filter((c) => c.mode === 'ai').length
  const lines: string[] = []

  lines.push(
    s.failed
      ? `Execution completed with ${s.failed} failure${s.failed === 1 ? '' : 's'}.`
      : 'Execution completed with no failures.',
  )
  if (healed.length) {
    lines.push(`${healed.length} case${healed.length === 1 ? '' : 's'} needed self-heal retries.`)
  }
  lines.push(
    `${aiCases} of ${s.total} case${s.total === 1 ? '' : 's'} used AI explore and codegen.`,
  )
  lines.push(
    s.pass_rate >= 90
      ? `Overall quality is good at ${s.pass_rate}% pass rate.`
      : `Pass rate is ${s.pass_rate}% — review failing cases before promoting.`,
  )
  return lines
}

export function timelineEvents(pack: ReportPack) {
  const sorted = [...pack.cases]
    .filter((c) => c.started_at)
    .sort((a, b) => String(a.started_at).localeCompare(String(b.started_at)))
  const first = sorted[0]
  const last = [...pack.cases]
    .filter((c) => c.finished_at)
    .sort((a, b) => String(a.finished_at).localeCompare(String(b.finished_at)))
    .pop()
  const failed = pack.cases.filter(isFailed)
  const healed = pack.cases.filter((c) => (c.heal_attempts || 0) > 1)

  const events: Array<{ at?: string; title: string; detail: string; tone: string }> = []

  events.push({
    at: first?.started_at,
    title: 'Execution Started',
    detail: `${pack.summary.total} case${pack.summary.total === 1 ? '' : 's'} queued`,
    tone: 'info',
  })

  if (healed.length) {
    events.push({
      at: healed[0].started_at,
      title: 'Self-Heal Triggered',
      detail: `${healed.length} case${healed.length === 1 ? '' : 's'} retried locators`,
      tone: 'warn',
    })
  }

  if (failed.length) {
    events.push({
      at: failed[0].finished_at,
      title: 'Failure Detected',
      detail: failed[0].name,
      tone: 'fail',
    })
  } else {
    events.push({
      at: last?.finished_at,
      title: 'All Assertions Passed',
      detail: 'No failures recorded',
      tone: 'pass',
    })
  }

  events.push({
    at: last?.finished_at,
    title: 'Execution Completed',
    detail: `${pack.summary.passed}/${pack.summary.total} passed`,
    tone: 'info',
  })

  return events
}

export function riskAreas(pack: ReportPack) {
  return pack.cases
    .map((c) => {
      let level: 'High' | 'Medium' | 'Low' = 'Low'
      if (isFailed(c)) level = 'High'
      else if ((c.heal_attempts || 0) > 1) level = 'Medium'
      else if ((c.total_usage?.cost || 0) > 0.5) level = 'Medium'
      return { id: c.id, name: c.name, host: hostOf(c), level }
    })
    .sort((a, b) => {
      const rank = { High: 0, Medium: 1, Low: 2 }
      return rank[a.level] - rank[b.level]
    })
    .slice(0, 5)
}

export function environmentBreakdown(pack: ReportPack) {
  const map = new Map<string, { total: number; passed: number }>()
  for (const c of pack.cases) {
    const key = hostOf(c)
    const cur = map.get(key) || { total: 0, passed: 0 }
    cur.total += 1
    if (c.status === 'passed') cur.passed += 1
    map.set(key, cur)
  }
  const total = pack.cases.length || 1
  return [...map.entries()]
    .map(([name, v]) => ({
      name,
      total: v.total,
      passed: v.passed,
      share: pct(v.total, total),
      passRate: pct(v.passed, v.total),
    }))
    .sort((a, b) => b.total - a.total)
}

export function modeBreakdown(cases: CaseRecord[]) {
  const ai = cases.filter((c) => c.mode === 'ai').length
  const scripted = cases.filter((c) => c.mode === 'scripted').length
  const total = cases.length || 1
  return [
    { name: 'AI explore+codegen', value: ai, color: '#0074bf', pct: pct(ai, total) },
    { name: 'Scripted', value: scripted, color: '#05b8b5', pct: pct(scripted, total) },
  ].filter((d) => d.value > 0)
}

export function typeBreakdown(cases: CaseRecord[]) {
  const groups: Record<string, { passed: number; failed: number; skipped: number }> = {}
  for (const c of cases) {
    const key = c.tags?.includes('smoke')
      ? 'Smoke'
      : c.mode === 'ai'
        ? 'AI generated'
        : c.mode === 'scripted'
          ? 'Scripted'
          : 'Other'
    groups[key] = groups[key] || { passed: 0, failed: 0, skipped: 0 }
    if (c.status === 'passed') groups[key].passed += 1
    else if (isFailed(c)) groups[key].failed += 1
    else groups[key].skipped += 1
  }
  return Object.entries(groups)
    .map(([name, v]) => ({ name, ...v, total: v.passed + v.failed + v.skipped }))
    .filter((g) => g.total > 0)
}

/* ---------- page 2: test results ---------- */

export function recentExecutions(pack: ReportPack) {
  const rows = [...(pack.trends || [])].reverse().slice(0, 10)
  return rows.map((t, i) => ({
    key: `${t.at}-${t.label}-${i}`,
    at: t.at,
    case: t.label,
    total: t.total,
    passed: t.passed,
    failed: t.failed,
    passRate: t.pass_rate,
    duration_ms: t.duration_ms,
    cost: t.cost,
    current: i === 0,
  }))
}

/* ---------- page 3: failures ---------- */

function usefulFailureLines(c: CaseRecord, limit = 5): string[] {
  const lines = (c.failure_output || '')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  const prefer = lines.filter(
    (ln) =>
      ln.startsWith('ERROR:') ||
      ln.startsWith('FAILED') ||
      ln.startsWith('E ') ||
      ln.includes('AssertionError') ||
      ln.startsWith('assert ') ||
      /^[a-z_]+:\s+/i.test(ln),
  )
  const noise = [
    'test session starts',
    'platform ',
    'cachedir:',
    'rootdir:',
    'configfile:',
    'plugins:',
    'collecting ',
    '====',
    'no tests ran',
  ]
  const usable =
    prefer.length > 0
      ? prefer
      : lines.filter((ln) => !noise.some((n) => ln.toLowerCase().includes(n) || ln.toLowerCase().startsWith(n)))
  return usable.slice(0, limit)
}

function phaseMap(c: CaseRecord) {
  const map: Record<string, { status?: string; detail?: string }> = {}
  for (const p of c.phases || []) {
    map[String(p.name || '').toLowerCase()] = p
  }
  return map
}

function explainFailure(c: CaseRecord): {
  reason: string
  evidence: string[]
  recommendation: string
  failedStep?: string
} {
  const phases = phaseMap(c)
  const explore = phases.explore
  const codegen = phases.codegen
  const verify = phases.verify
  const failedStep = (c.steps || []).find((s) => s.status === 'fail' || s.status === 'soft-fail')
  const errors = (c.errors || []).filter(Boolean)
  const useful = usefulFailureLines(c)
  const evidence: string[] = []

  const pushUnique = (msg?: string | null) => {
    const t = (msg || '').trim()
    if (!t || evidence.includes(t)) return
    evidence.push(t)
  }

  pushUnique(
    explore
      ? `Explore: ${explore.status || 'unknown'}${explore.detail ? ` — ${explore.detail}` : ''}`
      : null,
  )
  pushUnique(
    codegen
      ? `Codegen: ${codegen.status || 'unknown'}${codegen.detail ? ` — ${codegen.detail}` : ''}`
      : null,
  )
  pushUnique(
    verify
      ? `Verify: ${verify.status || 'unknown'}${verify.detail ? ` — ${verify.detail}` : ''}`
      : null,
  )
  for (const e of errors.slice(0, 2)) pushUnique(e)
  for (const u of useful.slice(0, 3)) pushUnique(u)

  let reason = ''
  let recommendation =
    'Re-run with artifacts enabled and compare the hierarchy / screenshots against the generated flow.'

  if (explore && (explore.status === 'failed' || explore.status === 'error')) {
    reason =
      useful[0] ||
      errors[0] ||
      explore.detail ||
      'Explore failed — the discovery agent could not complete the scenario on device.'
    recommendation =
      'Inspect the explore steps and failure output, then tighten the case guidance or App ID before re-running.'
  } else if (codegen && (codegen.status === 'failed' || codegen.status === 'error')) {
    reason = useful[0] || errors[0] || codegen.detail || 'Codegen failed to produce a Maestro flow.'
    recommendation =
      'Check codegen logs and regenerate; confirm the flow workspace and LLM profile are valid.'
  } else if (verify && (verify.status === 'failed' || verify.status === 'error')) {
    reason =
      useful.find((l) => l.startsWith('ERROR:') || l.startsWith('FAILED') || l.includes('AssertionError')) ||
      verify.detail ||
      useful[0] ||
      errors[0] ||
      'Verify/heal failed after generating the test.'
    recommendation = failedStep?.locator
      ? `Review locator ${failedStep.locator} — it did not resolve during verify.`
      : (c.heal_attempts || 0) > 1
        ? 'Heal retries were exhausted — stabilize the failing assertion or selector, then re-run verify.'
        : 'Open the verify failure output and fix the generated Maestro flow or assertion.'
  } else if (codegen && codegen.status === 'skipped') {
    const detail = (codegen.detail || '').toLowerCase()
    if (detail.includes('explore-only') || detail.includes('codegen not run')) {
      reason =
        'Pipeline stopped after explore: codegen was not run (explore-only / codegen disabled), so no Maestro flow was generated or verified.'
      recommendation =
        'Set `codegen: true` in the case file (or remove explore-only), re-run so codegen produces a test, then verify it.'
    } else if (detail.includes('explore failed')) {
      reason = 'Codegen was skipped because explore failed earlier in the pipeline.'
      recommendation = 'Fix the explore failure first; codegen and verify only run after a successful explore.'
    } else {
      reason = codegen.detail || 'Codegen was skipped, so the case never produced a verifiable test.'
      recommendation = 'Confirm why codegen was skipped, then re-run with codegen enabled.'
    }
  } else if (verify && verify.status === 'skipped') {
    reason =
      verify.detail ||
      'Verify was skipped — no generated test was executed, so the case did not pass end-to-end.'
    recommendation =
      (verify.detail || '').toLowerCase().includes('--no-heal')
        ? 'Re-run without `--no-heal` / with heal enabled to execute the generated Maestro flow.'
        : 'Ensure codegen produced a test file, then re-run verify/heal.'
  } else {
    reason =
      useful[0] ||
      errors[0] ||
      (c.failure_output || '').trim().split('\n').find(Boolean) ||
      'Case marked failed, but no structured root-cause detail was captured.'
  }

  if (!evidence.length) evidence.push('No structured error output captured')

  return {
    reason,
    evidence: evidence.slice(0, 6),
    recommendation,
    failedStep: failedStep?.raw || failedStep?.action,
  }
}

export function failureCards(pack: ReportPack) {
  return pack.cases.filter(isFailed).map((c) => {
    const attempts = c.heal_attempts || 0
    const severity =
      c.status === 'error' ? 'Critical' : attempts > 1 ? 'Flaky' : 'Regression'

    const explained = explainFailure(c)

    const confidence =
      severity === 'Critical' ? 92 : severity === 'Regression' ? 78 : 61

    const recommendation =
      severity === 'Flaky'
        ? 'Increase wait strategy or use a more stable locator for this step.'
        : explained.recommendation

    const tracePath =
      (c.artifacts && (c.artifacts.trace_path || c.artifacts.trace)) || null
    const videoPath =
      (c.artifacts && c.artifacts.video_path) || null
    const screenshotPath =
      (c.artifacts && c.artifacts.screenshot) ||
      (Array.isArray(c.artifacts?.screenshots) ? c.artifacts?.screenshots[0] : null) ||
      null

    return {
      id: c.id,
      name: c.name,
      testId: c.source_case || c.files_generated?.[0] || c.id,
      severity,
      module: hostOf(c),
      firstOccurred: c.finished_at || c.started_at || '',
      occurrences: Math.max(1, attempts || 1),
      reason: explained.reason,
      evidence: explained.evidence,
      confidence,
      recommendation,
      failedStep: explained.failedStep,
      tracePath: tracePath ? String(tracePath) : null,
      videoPath: videoPath ? String(videoPath) : null,
      screenshotPath: screenshotPath ? String(screenshotPath) : null,
    }
  })
}

export function failureCategories(pack: ReportPack) {
  const cards = failureCards(pack)
  const count = (s: string) => cards.filter((c) => c.severity === s).length
  return [
    { id: 'all', label: 'All Failures', count: cards.length },
    { id: 'Critical', label: 'Critical', count: count('Critical') },
    { id: 'Regression', label: 'Regression', count: count('Regression') },
    { id: 'Flaky', label: 'Flaky', count: count('Flaky') },
  ]
}

/* ---------- page 4 + 5: heatmaps ---------- */

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function failureByHour(pack: ReportPack) {
  const grid: number[][] = DAYS.map(() => Array(24).fill(0))
  let max = 0

  const bump = (iso: string | undefined, weight: number) => {
    if (!iso || weight <= 0) return
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return
    const day = (d.getDay() + 6) % 7
    const hour = d.getHours()
    grid[day][hour] += weight
    max = Math.max(max, grid[day][hour])
  }

  for (const t of pack.trends || []) bump(t.at, t.failed)
  for (const c of pack.cases) if (isFailed(c)) bump(c.finished_at || c.started_at, 1)

  return { grid, max, days: DAYS }
}

export function runHeatmap(pack: ReportPack) {
  /** @deprecated use recentCaseOutcomes — kept for callers */
  return recentCaseOutcomes(pack).map((c, i) => ({
    label: `Case ${i + 1}`,
    cells: [{ value: c.passRate, at: c.at, caseName: c.label }],
  }))
}

/** One cell per recent case execution from pack trends (not fake week groups). */
export function recentCaseOutcomes(pack: ReportPack) {
  const points = [...(pack.trends || [])].slice(-24)
  return points.map((p) => {
    const total = Math.max(0, Number(p.total) || 0)
    const passed = Math.max(0, Number(p.passed) || 0)
    const failed = Math.max(0, Number(p.failed) || 0)
    let passRate = Number(p.pass_rate)
    if (!Number.isFinite(passRate) && total > 0) {
      passRate = (100 * passed) / total
    }
    if (!Number.isFinite(passRate)) passRate = 0
    return {
      label: String(p.label || 'case'),
      at: String(p.at || ''),
      passRate: Math.round(passRate),
      passed,
      failed,
      total: total || passed + failed,
      ok: passRate >= 100 || (total > 0 && failed === 0 && passed > 0),
    }
  })
}

/** Aggregate case runs by calendar day → real daily pack-like pass rates. */
export function dailyPassHeatmap(pack: ReportPack) {
  const buckets = new Map<
    string,
    { passed: number; failed: number; total: number; at: string }
  >()
  for (const p of pack.trends || []) {
    const at = String(p.at || '')
    const day = at.slice(0, 10) || 'unknown'
    const cur = buckets.get(day) || { passed: 0, failed: 0, total: 0, at }
    const passed = Math.max(0, Number(p.passed) || 0)
    const failed = Math.max(0, Number(p.failed) || 0)
    const total = Math.max(Number(p.total) || 0, passed + failed)
    cur.passed += passed
    cur.failed += failed
    cur.total += total
    cur.at = at || cur.at
    buckets.set(day, cur)
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14)
    .map(([day, b]) => ({
      day,
      at: b.at,
      passRate: b.total ? Math.round((100 * b.passed) / b.total) : 0,
      passed: b.passed,
      failed: b.failed,
      total: b.total,
    }))
}

/* ---------- page 5: flaky ---------- */

export function flakyRows(pack: ReportPack) {
  return pack.cases
    .filter((c) => (c.heal_attempts || 0) > 1 || isFailed(c))
    .map((c) => {
      const attempts = Math.max(1, c.heal_attempts || 1)
      const flakyScore = Math.min(95, 35 + attempts * 18 + (isFailed(c) ? 15 : 0))
      const passRate = c.status === 'passed' ? Math.max(40, 100 - (attempts - 1) * 15) : 30
      return {
        id: c.id,
        name: c.name,
        flakyScore,
        passRate,
        pattern: isFailed(c)
          ? 'Fails consistently'
          : attempts > 2
            ? 'Needs repeated healing'
            : 'Intermittent locator drift',
        environment: hostOf(c),
        lastFailed: c.finished_at || c.started_at || '',
        recommendation:
          attempts > 2 ? 'Pin a stable selector' : isFailed(c) ? 'Investigate real defect' : 'Increase wait time',
        spark: [passRate - 18, passRate - 4, passRate + 6, passRate - 10, passRate].map((v) =>
          Math.max(10, Math.min(100, v)),
        ),
      }
    })
    .sort((a, b) => b.flakyScore - a.flakyScore)
}

export function flakySummary(pack: ReportPack) {
  const rows = flakyRows(pack)
  const highRisk = rows.filter((r) => r.flakyScore >= 70).length
  const rate = pct(rows.length, pack.summary.total)
  const healed = pack.cases.filter((c) => (c.heal_attempts || 0) > 1 && c.status === 'passed').length
  return {
    totalFlaky: rows.length,
    flakyRate: rate,
    highRisk,
    recovered: healed,
  }
}

export function moduleBreakdown(pack: ReportPack) {
  /** @deprecated prefer targetOutcomes — count-by-host is often 1 each */
  return targetOutcomes(pack).map((t, i) => {
    const palette = ['#0074bf', '#05b8b5', '#5b4dc7', '#c45c12', '#1b883c', '#8a6cff']
    return {
      name: t.name,
      value: t.total,
      pct: t.sharePct,
      color: palette[i % palette.length],
    }
  })
}

/** Pass / fail / heal counts per target host — useful when case counts are equal. */
export function targetOutcomes(pack: ReportPack) {
  const map = new Map<
    string,
    { passed: number; failed: number; healed: number; cost: number; durationMs: number }
  >()
  for (const c of pack.cases) {
    const h = hostOf(c) || 'unknown'
    const cur = map.get(h) || { passed: 0, failed: 0, healed: 0, cost: 0, durationMs: 0 }
    if (isFailed(c)) cur.failed += 1
    else cur.passed += 1
    if ((c.heal_attempts || 0) > 1) cur.healed += 1
    cur.cost += Number(c.total_usage?.cost || 0)
    cur.durationMs += Number(c.duration_ms || 0)
    map.set(h, cur)
  }
  const totalCases = pack.cases.length || 1
  return [...map.entries()]
    .map(([name, v]) => {
      const total = v.passed + v.failed
      return {
        name,
        passed: v.passed,
        failed: v.failed,
        healed: v.healed,
        total,
        passRate: total ? Math.round((100 * v.passed) / total) : 0,
        sharePct: pct(total, totalCases),
        cost: v.cost,
        durationMs: v.durationMs,
      }
    })
    .sort((a, b) => b.failed - a.failed || b.total - a.total || a.name.localeCompare(b.name))
}

/* ---------- page 6: assistant ---------- */

export type AssistantAnswer = {
  question: string
  title: string
  bullets: string[]
  footer?: string
}

export function assistantAnswers(pack: ReportPack): AssistantAnswer[] {
  const s = pack.summary
  const conf = releaseConfidence(pack)
  const failed = pack.cases.filter(isFailed)
  const healed = pack.cases.filter((c) => (c.heal_attempts || 0) > 1)
  const costly = [...pack.cases].sort(
    (a, b) => (b.total_usage?.cost || 0) - (a.total_usage?.cost || 0),
  )[0]
  const slowest = [...pack.cases].sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0))[0]

  return [
    {
      question: 'Did anything fail in this run?',
      title: 'Failure Analysis',
      bullets: failed.length
        ? failed.map((c) => `${c.name} — ${(c.errors || [])[0] || c.status}`)
        : [`All ${s.total} cases passed.`, 'No errors or assertion failures were recorded.'],
      footer: `Pass rate: ${s.pass_rate}%`,
    },
    {
      question: 'Is this build safe to release?',
      title: 'Release Recommendation',
      bullets: [
        `Release confidence scored ${conf.score}/100 (${conf.verdict}).`,
        `${s.passed} of ${s.total} cases passed.`,
        healed.length
          ? `${healed.length} case(s) required self-heal retries — treat as a stability risk.`
          : 'No self-heal retries were needed.',
      ],
      footer: conf.verdict,
    },
    {
      question: 'Which tests are unstable?',
      title: 'Stability Review',
      bullets: healed.length
        ? healed.map((c) => `${c.name} — ${c.heal_attempts} heal attempts`)
        : ['No case needed more than one attempt.', 'Locators resolved on the first pass.'],
      footer: `${healed.length} unstable case(s)`,
    },
    {
      question: 'Where is AI spend going?',
      title: 'Token & Cost Breakdown',
      bullets: [
        `Total spend for this pack: $${(s.cost || 0).toFixed(4)}.`,
        `${s.total_tokens.toLocaleString()} tokens (${s.prompt_tokens.toLocaleString()} in / ${s.completion_tokens.toLocaleString()} out).`,
        costly
          ? `Highest cost case: ${costly.name} at $${(costly.total_usage?.cost || 0).toFixed(4)}.`
          : 'No per-case cost recorded.',
      ],
      footer: `$${(s.cost || 0).toFixed(4)} total`,
    },
    {
      question: 'What took the longest?',
      title: 'Duration Analysis',
      bullets: [
        slowest
          ? `${slowest.name} was slowest at ${Math.round((slowest.duration_ms || 0) / 1000)}s.`
          : 'No duration recorded.',
        `Pack total runtime: ${Math.round((s.duration_ms || 0) / 1000)}s across ${s.total} cases.`,
      ],
      footer: 'Sorted by wall-clock duration',
    },
    {
      question: 'What should I do next?',
      title: 'Recommended Next Steps',
      bullets: buildRecommendation(pack).actions,
      footer: buildRecommendation(pack).text,
    },
  ]
}

/* ---------- shared ---------- */

export function topFailures(cases: CaseRecord[]) {
  return cases
    .filter(isFailed)
    .map((c) => {
      const reason =
        (c.failure_output || '').split('\n').find(Boolean) ||
        (c.errors || [])[0] ||
        'Failure recorded during verify/heal'
      return {
        id: c.id,
        name: c.name,
        path: c.source_case || c.files_generated?.[0] || c.url || c.mode,
        reason: reason.slice(0, 140),
        since: c.finished_at || c.started_at || '',
        occurrences: Math.max(1, c.heal_attempts || 1),
      }
    })
    .sort((a, b) => b.occurrences - a.occurrences)
    .slice(0, 8)
}

export function buildRecommendation(pack: ReportPack) {
  const failed = pack.summary.failed
  const costly = [...pack.cases].sort(
    (a, b) => (b.total_usage?.cost || 0) - (a.total_usage?.cost || 0),
  )[0]
  const healed = pack.cases.filter((c) => (c.heal_attempts || 0) > 1).length
  const actions: string[] = []
  if (failed) actions.push(`Fix ${failed} failing case${failed === 1 ? '' : 's'} before next pack`)
  if (healed) actions.push(`Stabilize ${healed} case${healed === 1 ? '' : 's'} that needed heal retries`)
  if (costly && (costly.total_usage?.cost || 0) > 0) {
    actions.push(`Review token spend on ${costly.name} ($${costly.total_usage!.cost.toFixed(4)})`)
  }
  if (!actions.length) actions.push('Pack is green — archive report and promote generated tests')

  const text =
    failed > 0
      ? `Prioritize failing cases first. ${costly ? `${costly.name} is the highest-cost run in this pack.` : ''}`
      : `All cases passed. ${healed ? `${healed} still needed self-heal retries — tighten locators there next.` : 'No heal retries required.'}`

  return { text: text.trim(), actions: actions.slice(0, 3) }
}
