// Thin typed wrapper around the backend REST API. Every function throws on a non-2xx
// response so callers can just try/catch (or let an ErrorBoundary-less page show the
// message directly — this app is small enough not to need one).

export type BlockKind = 'heading' | 'para' | 'quote' | 'verse' | 'skip'

export type FormatInfo = {
  extension: string
  available: boolean
  note: string | null
}

export type BookSummary = {
  id: number
  title: string
  author: string | null
  language: string
  source_format: string
  has_cover: boolean
  chapter_count: number
  created_at: string
}

export type ChapterSummary = {
  id: number
  index: number
  title: string
  enabled: boolean
  block_count: number
}

export type BookDetail = BookSummary & { chapters: ChapterSummary[] }

export type Block = {
  id: number
  index: number
  kind: BlockKind
  text: string
}

export type ChapterDetail = {
  id: number
  index: number
  title: string
  enabled: boolean
  blocks: Block[]
}

export type VoiceInfo = {
  id: string
  engine: string
  language: string
  gender: string | null
  sample_rate: number
  quality: string | null
}

export type JobStageInfo = {
  name: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  progress: number
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export type Job = {
  id: number
  book_id: number
  status: JobStatus
  voice: string
  speed: number
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  stages: JobStageInfo[]
}

export type SettingsValues = {
  tts_workers: number
  loudness_target_i: number
  loudness_target_tp: number
  loudness_target_lra: number
  output_dir: string
  models_dir: string
}

export type DiskUsage = {
  cache_bytes: number
  output_bytes: number
  models_bytes: number
  free_bytes: number
}

export type ModelStatus = {
  dest: string
  size_bytes: number
  present: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      // response wasn't JSON — keep the status line
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

function json(body: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

// --- health -------------------------------------------------------------------

export function getHealth() {
  return request<{ status: string; version: string }>('/api/health')
}

// --- books ----------------------------------------------------------------------

export function listFormats() {
  return request<FormatInfo[]>('/api/formats')
}

export function listBooks() {
  return request<BookSummary[]>('/api/books')
}

export function getBook(bookId: number) {
  return request<BookDetail>(`/api/books/${bookId}`)
}

export function getChapter(bookId: number, chapterId: number) {
  return request<ChapterDetail>(`/api/books/${bookId}/chapters/${chapterId}`)
}

export function updateChapter(bookId: number, chapterId: number, patch: { title?: string; enabled?: boolean }) {
  return request<ChapterDetail>(`/api/books/${bookId}/chapters/${chapterId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function updateBlock(bookId: number, chapterId: number, blockId: number, text: string) {
  return request<Block>(`/api/books/${bookId}/chapters/${chapterId}/blocks/${blockId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

export function uploadBook(file: File, onProgress?: (fraction: number) => void): Promise<BookSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/books')
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total)
    }
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText)
        if (xhr.status >= 200 && xhr.status < 300) resolve(body)
        else reject(new Error(body?.detail || `${xhr.status} ${xhr.statusText}`))
      } catch {
        reject(new Error(`${xhr.status} ${xhr.statusText}`))
      }
    }
    xhr.onerror = () => reject(new Error('network error during upload'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

// --- voices ---------------------------------------------------------------------

export function listVoices() {
  return request<VoiceInfo[]>('/api/voices')
}

export async function previewVoice(voiceId: string): Promise<Blob> {
  const res = await fetch(`/api/voices/${encodeURIComponent(voiceId)}/preview`, { method: 'POST' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.blob()
}

// --- jobs -----------------------------------------------------------------------

export function createJob(bookId: number, voice: string, speed: number) {
  return request<Job>(`/api/books/${bookId}/jobs`, json({ voice, speed }))
}

export function getJob(jobId: number) {
  return request<Job>(`/api/jobs/${jobId}`)
}

export function listBookJobs(bookId: number) {
  return request<Job[]>(`/api/books/${bookId}/jobs`)
}

export function cancelJob(jobId: number) {
  return request<Job>(`/api/jobs/${jobId}/cancel`, { method: 'POST' })
}

export function downloadJobUrl(jobId: number) {
  return `/api/jobs/${jobId}/download`
}

/** For an <audio> element's src — unlike downloadJobUrl, this has no Content-Disposition:
 * attachment, so the browser treats it as inline playable media (shows duration, allows
 * seeking) instead of trying to save it. */
export function streamJobUrl(jobId: number) {
  return `/api/jobs/${jobId}/stream`
}

/** Subscribes to live job progress over SSE. Returns an unsubscribe function. */
export function subscribeJobEvents(jobId: number, onUpdate: (job: Job) => void, onError?: () => void): () => void {
  const source = new EventSource(`/api/jobs/${jobId}/events`)
  source.addEventListener('update', (e) => {
    try {
      onUpdate(JSON.parse((e as MessageEvent).data))
    } catch {
      // ignore malformed event
    }
  })
  source.onerror = () => {
    onError?.()
  }
  return () => source.close()
}

// --- settings -------------------------------------------------------------------

export function getSettings() {
  return request<SettingsValues>('/api/settings')
}

export function updateSettings(patch: Partial<Omit<SettingsValues, 'output_dir' | 'models_dir'>>) {
  return request<SettingsValues>('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function getDiskUsage() {
  return request<DiskUsage>('/api/settings/disk-usage')
}

export function getModelStatus() {
  return request<ModelStatus[]>('/api/settings/models')
}
