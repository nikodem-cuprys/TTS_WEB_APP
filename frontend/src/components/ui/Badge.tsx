import type { ReactNode } from 'react'

type Tone = 'neutral' | 'accent' | 'danger' | 'warn'

const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'bg-elevated text-text-2 border-border',
  accent: 'bg-accent-dim/30 text-accent border-accent-dim',
  danger: 'bg-danger/10 text-danger border-danger/30',
  warn: 'bg-warn/10 text-warn border-warn/30',
}

export default function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={[
        'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none',
        TONE_CLASSES[tone],
      ].join(' ')}
    >
      {children}
    </span>
  )
}
