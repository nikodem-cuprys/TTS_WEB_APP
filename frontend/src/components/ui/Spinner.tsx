export default function Spinner({ className = '' }: { className?: string }) {
  return (
    <span
      className={['inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-text-3 border-t-accent', className].join(' ')}
      aria-label="loading"
    />
  )
}
