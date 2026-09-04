import type { HTMLAttributes } from 'react'

export default function Card({ className = '', ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={['rounded-md border border-border bg-surface', className].join(' ')}
      {...rest}
    />
  )
}
