import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import ProgressBar from '../components/ui/ProgressBar'
import JobStatusBadge from '../components/JobStatusBadge'
import {
  cancelJob,
  downloadJobArtifactUrl,
  getJob,
  streamJobUrl,
  subscribeJobEvents,
  type ExportFormat,
  type Job as JobType,
} from '../lib/api'

const STAGE_LABELS: Record<string, string> = {
  prepare: 'Preparing text',
  synthesize: 'Synthesizing speech',
  assemble: 'Assembling audio',
  master: 'Mastering loudness',
  export: 'Exporting',
}

const ARTIFACT_LABELS: Record<ExportFormat, string> = {
  mp3: 'MP3',
  m4b: 'M4B',
  opus: 'Opus',
  flac: 'FLAC',
  wav: 'WAV',
  srt: 'SRT',
  vtt: 'VTT',
  mp4: 'MP4',
}

function elapsedSeconds(job: JobType): number | null {
  if (!job.started_at) return null
  const end = job.finished_at ? new Date(job.finished_at) : new Date()
  return (end.getTime() - new Date(job.started_at).getTime()) / 1000
}

export default function Job() {
  const { jobId } = useParams<{ jobId: string }>()
  const id = Number(jobId)
  const [job, setJob] = useState<JobType | null>(null)
  const [connectionLost, setConnectionLost] = useState(false)
  const [cancelling, setCancelling] = useState(false)
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

  if (!job) return <div className="p-8 text-sm text-text-2">Loading…</div>

  const isTerminal = job.status === 'done' || job.status === 'failed' || job.status === 'cancelled'
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

        <div className="flex gap-2">
          {!isTerminal && (
            <Button variant="danger" size="sm" onClick={handleCancel} disabled={cancelling}>
              {cancelling ? 'Cancelling…' : 'Cancel'}
            </Button>
          )}
        </div>

        {job.status === 'done' && job.artifacts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {job.artifacts.map((format) => (
              <a key={format} href={downloadJobArtifactUrl(job.id, format)} download>
                <Button size="sm" variant="secondary">
                  Download {ARTIFACT_LABELS[format]}
                </Button>
              </a>
            ))}
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
