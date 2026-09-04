import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md'

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-accent text-bg hover:bg-accent-hover disabled:bg-accent-dim disabled:text-text-3',
  secondary: 'bg-elevated text-text border border-border hover:border-text-3 disabled:opacity-50',
  danger: 'bg-transparent text-danger border border-danger/40 hover:bg-danger/10 disabled:opacity-50',
  ghost: 'bg-transparent text-text-2 hover:text-text hover:bg-elevated disabled:opacity-50',
}

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3.5 py-2 text-sm',
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
}

export default function Button({ variant = 'primary', size = 'md', className = '', ...rest }: Props) {
  return (
    <button
      className={[
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
        'disabled:cursor-not-allowed',
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      ].join(' ')}
      {...rest}
    />
  )
}
