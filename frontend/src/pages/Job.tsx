import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import ProgressBar from '../components/ui/ProgressBar'
import JobStatusBadge from '../components/JobStatusBadge'
import JobDownloads from '../components/JobDownloads'
import { cancelJob, getJob, retryJob, streamJobUrl, subscribeJobEvents, type Job as JobType } from '../lib/api'

const STAGE_LABELS: Record<string, string> = {
  prepare: 'Preparing text',
  synthesize: 'Synthesizing speech',
  assemble: 'Assembling audio',
  master: 'Mastering loudness',
  export: 'Exporting',
}

function elapsedSeconds(job: JobType): number | null {
  if (!job.started_at) return null
  const end = job.finished_at ? new Date(job.finished_at) : new Date()
  return (end.getTime() - new Date(job.started_at).getTime()) / 1000
}

export default function Job() {
  const { jobId } = useParams<{ jobId: string }>()
  const id = Number(jobId)
  const navigate = useNavigate()
  const [job, setJob] = useState<JobType | null>(null)
  const [connectionLost, setConnectionLost] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState<string | null>(null)
  const startedAtLoad = useRef(false)

  useEffect(() => {
    getJob(id)
      .then(setJob)
      .catch(() => {})
      .finally(() => {
        startedAtLoad.current = true
      })

    const unsubscribe = subscribeJobEvents(
      id,
      (updated) => {
        setJob(updated)
        setConnectionLost(false)
      },
      () => setConnectionLost(true),
    )
    return unsubscribe
  }, [id])

  const handleCancel = async () => {
    setCancelling(true)
    try {
      const updated = await cancelJob(id)
      setJob(updated)
    } finally {
      setCancelling(false)
    }
  }

  const handleRetry = async () => {
    setRetrying(true)
    setRetryError(null)
    try {
      const retried = await retryJob(id)
      navigate(`/jobs/${retried.id}`)
    } catch (e) {
      setRetryError(String(e instanceof Error ? e.message : e))
      setRetrying(false)
    }
  }

  if (!job) return <div className="p-8 text-sm text-text-2">Loading…</div>

  const isTerminal = job.status === 'done' || job.status === 'failed' || job.status === 'cancelled'
  const canRetry = job.status === 'failed' || job.status === 'cancelled'
  const elapsed = elapsedSeconds(job)

  return (
    <div className="mx-auto max-w-xl p-8">
      <Link to={`/books/${job.book_id}`} className="text-xs text-text-3 hover:text-text">
        ← Book
      </Link>
      <div className="mb-6 mt-2 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">Render Job #{job.id}</h2>
        <JobStatusBadge status={job.status} />
      </div>

      {connectionLost && !isTerminal && (
        <p className="mb-4 text-xs text-warn">Live connection lost — status shown may be stale.</p>
      )}

      <Card className="flex flex-col gap-4 p-5">
        <div className="flex items-center justify-between text-xs text-text-3">
          <span>Voice: {job.voice}</span>
          {elapsed !== null && <span className="font-mono-tabular">{elapsed.toFixed(0)}s elapsed</span>}
        </div>

        <div className="flex flex-col gap-3">
          {Object.entries(STAGE_LABELS).map(([name, label]) => {
            const stage = job.stages.find((s) => s.name === name)
            const status = stage?.status ?? 'queued'
            const progress = stage?.progress ?? 0
            return (
              <div key={name}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className={status === 'queued' ? 'text-text-3' : 'text-text-2'}>{label}</span>
                  <span className="text-text-3">
                    {status === 'done' ? '✓' : status === 'failed' ? '✕' : status === 'running' ? `${Math.round(progress * 100)}%` : ''}
                  </span>
                </div>
                <ProgressBar
                  value={status === 'done' ? 1 : status === 'running' ? Math.max(progress, 0.05) : 0}
                  tone={status === 'failed' ? 'danger' : 'accent'}
                />
              </div>
            )
          })}
        </div>

        {job.error && (
          <p className="rounded border border-danger/30 bg-danger/10 p-2 text-xs text-danger">{job.error}</p>
        )}
        {retryError && <p className="text-xs text-danger">Retry failed: {retryError}</p>}

        <div className="flex items-center gap-2">
          {!isTerminal && (
            <Button variant="danger" size="sm" onClick={handleCancel} disabled={cancelling}>
              {cancelling ? 'Cancelling…' : 'Cancel'}
            </Button>
          )}
          {canRetry && (
            <>
              <Button size="sm" onClick={handleRetry} disabled={retrying}>
                {retrying ? 'Starting…' : 'Retry'}
              </Button>
              <span className="text-xs text-text-3">
                Starts a new render with the same settings — already-synthesized chunks are reused.
              </span>
            </>
          )}
        </div>

        {job.status === 'done' && job.artifacts.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-text-2">Downloads</span>
            <JobDownloads job={job} />
          </div>
        )}

        {job.status === 'done' && (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <audio controls src={streamJobUrl(job.id)} className="w-full" />
        )}
      </Card>
    </div>
  )
}
