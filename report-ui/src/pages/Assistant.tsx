import { useRef, useEffect, useState } from 'react'
import { Copy, Send, SquarePen } from 'lucide-react'
import type { ReportPack } from '../types'
import { PageHeader } from '../components/PageHeader'
import { AiMark } from '../components/AiMark'
import { assistantAnswers, type AssistantAnswer } from '../derive'

type Turn = { role: 'user'; text: string } | { role: 'ai'; answer: AssistantAnswer }

const SHORTCUTS: Array<{ label: string; match: RegExp }> = [
  { label: 'Risk', match: /fail|release|safe|risk/i },
  { label: 'Cost', match: /spend|cost|token/i },
  { label: 'Stability', match: /unstable|flaky|heal/i },
  { label: 'Next steps', match: /next|should i do/i },
]

export function Assistant({ data }: { data: ReportPack }) {
  const answers = assistantAnswers(data)
  const [turns, setTurns] = useState<Turn[]>([{ role: 'ai', answer: answers[0] }])
  const [draft, setDraft] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns])

  const ask = (a: AssistantAnswer) => {
    setTurns((t) => [...t, { role: 'user', text: a.question }, { role: 'ai', answer: a }])
  }

  const askShortcut = (label: string) => {
    const rule = SHORTCUTS.find((s) => s.label === label)
    const match = answers.find((a) => rule?.match.test(`${a.question} ${a.title}`))
    if (match) ask(match)
  }

  const submit = () => {
    const q = draft.trim()
    if (!q) return
    const needle = q.toLowerCase()
    const match =
      answers.find((a) => a.question.toLowerCase() === needle) ||
      answers.find((a) =>
        needle
          .split(/\s+/)
          .filter((w) => w.length > 3)
          .some((w) => a.question.toLowerCase().includes(w) || a.title.toLowerCase().includes(w)),
      )

    setTurns((t) => [
      ...t,
      { role: 'user', text: q },
      {
        role: 'ai',
        answer:
          match ?? {
            question: q,
            title: 'No precomputed answer',
            bullets: [
              'This report is a static file, so answers are precomputed from the pack data.',
              'Try one of the suggested questions above for a data-backed response.',
            ],
            footer: 'Offline report',
          },
      },
    ])
    setDraft('')
  }

  return (
    <div className="ai-page">
      <PageHeader
        title="AI Insights"
        subtitle="Answers computed from this pack's execution data"
        actions={
          <button
            type="button"
            className="btn"
            onClick={() => setTurns([{ role: 'ai', answer: answers[0] }])}
          >
            <SquarePen size={14} />
            Reset
          </button>
        }
      />

      <div className="ai-prompts">
        <div className="ai-prompt-row">
          {answers.map((a) => (
            <button key={a.question} type="button" className="ai-chip" onClick={() => ask(a)}>
              {a.question}
            </button>
          ))}
        </div>
        <div className="ai-shortcut-row">
          {SHORTCUTS.map((s) => (
            <button
              key={s.label}
              type="button"
              className="ai-shortcut"
              onClick={() => askShortcut(s.label)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="card ai-chat">
        <div className="ai-chat-scroll" ref={scrollRef}>
          {turns.map((t, i) =>
            t.role === 'user' ? (
              <div className="bubble-user" key={i}>
                {t.text}
              </div>
            ) : (
              <div className="bubble-ai" key={i}>
                <div className="bubble-head">
                  <span className="ai-avatar">
                    <AiMark size={14} />
                  </span>
                  {t.answer.title}
                </div>
                <ul>
                  {t.answer.bullets.map((b, bi) => (
                    <li key={bi}>{b}</li>
                  ))}
                </ul>
                {t.answer.footer ? <div className="bubble-foot">{t.answer.footer}</div> : null}
                <button
                  type="button"
                  className="bubble-copy"
                  onClick={() =>
                    navigator.clipboard?.writeText(
                      `${t.answer.title}\n${t.answer.bullets.join('\n')}`,
                    )
                  }
                >
                  <Copy size={12} />
                  Copy
                </button>
              </div>
            ),
          )}
        </div>

        <div className="chat-input">
          <input
            value={draft}
            placeholder="Ask about this execution…"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submit()
            }}
          />
          <button type="button" className="btn primary" onClick={submit} aria-label="Send">
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}
