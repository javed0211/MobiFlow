import type { ReactNode } from 'react'

type Props = { status?: string; children?: ReactNode }

export function Badge({ status = 'info', children }: Props) {
  return <span className={`badge ${status}`}>{children ?? status}</span>
}
