import type { InputHTMLAttributes } from 'react'

export default function Slider({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="range"
      className={[
        'h-1.5 w-full cursor-pointer appearance-none rounded-full bg-elevated accent-accent',
        className,
      ].join(' ')}
      {...rest}
    />
  )
}
