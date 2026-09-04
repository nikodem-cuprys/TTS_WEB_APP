import type { SelectHTMLAttributes } from 'react'

export default function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={[
        'rounded-md border border-border bg-elevated px-2.5 py-1.5 text-sm text-text',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </select>
  )
}
