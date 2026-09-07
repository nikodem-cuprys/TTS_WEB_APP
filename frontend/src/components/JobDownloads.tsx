import { useState } from 'react'
import Button from './ui/Button'
import { downloadJobArtifactUrl, type ExportFormat, type Job, type JobArtifactInfo } from '../lib/api'

const ARTIFACT_LABELS: Record<ExportFormat, string> = {
  mp3: 'MP3',
  m4b: 'M4B',
  opus: 'Opus',
  flac: 'FLAC',
  wav: 'WAV',
  srt: 'SRT',
  vtt: 'VTT',
  mp4: 'MP4',
  chapters: 'YouTube chapters',
}

function groupByFormat(artifacts: JobArtifactInfo[]): Map<ExportFormat, JobArtifactInfo[]> {
  const groups = new Map<ExportFormat, JobArtifactInfo[]>()
  for (const artifact of artifacts) {
    const existing = groups.get(artifact.format)
    if (existing) existing.push(artifact)
    else groups.set(artifact.format, [artifact])
  }
  return groups
}

/** Every downloadable artifact for one finished job — a format [M5-8] split into
 * several parts (currently only ever mp4) gets one button per part; the YouTube
 * "chapters" text also gets a one-click "Copy" button, matching its "ready to paste"
 * purpose. Shared between the Job page (a single render's full detail) and the Book
 * page (a compact list across every past render of that book), so a finished book's
 * exports are always reachable from either place. */
export default function JobDownloads({ job }: { job: Job }) {
  const [copied, setCopied] = useState(false)

  if (job.status !== 'done' || job.artifacts.length === 0) return null

  const handleCopyChapters = async () => {
    const res = await fetch(downloadJobArtifactUrl(job.id, 'chapters'))
    const text = await res.text()
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex flex-wrap gap-2">
      {[...groupByFormat(job.artifacts)].map(([format, parts]) =>
        parts.length > 1
          ? parts.map((part) => (
              <a
                key={`${format}-${part.part_index}`}
                href={downloadJobArtifactUrl(job.id, format, part.part_index ?? undefined)}
                download
              >
                <Button size="sm" variant="secondary">
                  {ARTIFACT_LABELS[format]} – Part {part.part_index} of {part.part_total}
                </Button>
              </a>
            ))
          : (
              <a key={format} href={downloadJobArtifactUrl(job.id, format)} download>
                <Button size="sm" variant="secondary">
                  Download {ARTIFACT_LABELS[format]}
                </Button>
              </a>
            ),
      )}
      {job.artifacts.some((a) => a.format === 'chapters') && (
        <Button size="sm" variant="secondary" onClick={handleCopyChapters}>
          {copied ? 'Copied!' : 'Copy chapters text'}
        </Button>
      )}
    </div>
  )
}
