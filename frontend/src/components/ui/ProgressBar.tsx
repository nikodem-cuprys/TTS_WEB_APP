type Props = {
  /** 0..1 */
  value: number
  tone?: 'accent' | 'danger'
  className?: string
}

export default function ProgressBar({ value, tone = 'accent', className = '' }: Props) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className={['h-1.5 w-full overflow-hidden rounded-full bg-elevated', className].join(' ')}>
      <div
        className={['h-full rounded-full transition-[width] duration-300', tone === 'accent' ? 'bg-accent' : 'bg-danger'].join(' ')}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
