import Badge from './ui/Badge'
import type { JobStatus } from '../lib/api'

const CONFIG: Record<JobStatus, { label: string; tone: 'neutral' | 'accent' | 'danger' | 'warn' }> = {
  queued: { label: 'Queued', tone: 'neutral' },
  running: { label: 'Rendering', tone: 'warn' },
  done: { label: 'Done', tone: 'accent' },
  failed: { label: 'Failed', tone: 'danger' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}

export default function JobStatusBadge({ status }: { status: JobStatus }) {
  const { label, tone } = CONFIG[status]
  return <Badge tone={tone}>{label}</Badge>
}
