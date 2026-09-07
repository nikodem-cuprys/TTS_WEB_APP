import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Select from '../components/ui/Select'
import Spinner from '../components/ui/Spinner'
import LexiconEditor from '../components/LexiconEditor'
import JobStatusBadge from '../components/JobStatusBadge'
import JobDownloads from '../components/JobDownloads'
import {
  getBook,
  getChapter,
  listBookJobs,
  updateBlock,
  updateBook,
  updateChapter,
  type BookDetail,
  type ChapterDetail,
  type ChapterSummary,
  type Job,
} from '../lib/api'

const WORDS_PER_MINUTE = 150

// The only languages actually routed to an engine ([M4-5]) — matches
// backend/app/tts/registry.py's LANGUAGE_ROUTING.
const SUPPORTED_LANGUAGES = ['en', 'pl', 'de', 'zh']

function LanguageSelector({ bookId, language, onChange }: { bookId: number; language: string; onChange: (lang: string) => void }) {
  const [saving, setSaving] = useState(false)
  const options = SUPPORTED_LANGUAGES.includes(language) ? SUPPORTED_LANGUAGES : [language, ...SUPPORTED_LANGUAGES]

  const handleChange = async (next: string) => {
    setSaving(true)
    try {
      await updateBook(bookId, { language: next })
      onChange(next)
    } finally {
      setSaving(false)
    }
  }

  return (
    <span className="inline-flex items-center gap-1">
      <Select
        value={language}
        onChange={(e) => handleChange(e.target.value)}
        disabled={saving}
        className="!py-0.5 !text-xs"
        title="Override the detected language if it's wrong"
      >
        {options.map((lang) => (
          <option key={lang} value={lang}>
            {lang}
          </option>
        ))}
      </Select>
      {saving && <Spinner />}
    </span>
  )
}

function wordCount(text: string): number {
  const trimmed = text.trim()
  return trimmed ? trimmed.split(/\s+/).length : 0
}

function formatMinutes(minutes: number): string {
  if (minutes < 1) return '<1 min'
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return h > 0 ? `${h}h ${m}m` : `${m} min`
}

function ChapterRow({
  bookId,
  summary,
  onSummaryChange,
}: {
  bookId: number
  summary: ChapterSummary
  onSummaryChange: (patch: Partial<ChapterSummary>) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState<ChapterDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState(summary.title)

  const toggleExpand = useCallback(() => {
    const next = !expanded
    setExpanded(next)
    if (next && detail === null) {
      setLoading(true)
      getChapter(bookId, summary.id)
        .then(setDetail)
        .finally(() => setLoading(false))
    }
  }, [bookId, detail, expanded, summary.id])

  const saveTitle = useCallback(() => {
    setEditingTitle(false)
    if (titleDraft.trim() && titleDraft !== summary.title) {
      updateChapter(bookId, summary.id, { title: titleDraft.trim() }).then(() =>
        onSummaryChange({ title: titleDraft.trim() }),
      )
    } else {
      setTitleDraft(summary.title)
    }
  }, [bookId, onSummaryChange, summary.id, summary.title, titleDraft])

  const toggleEnabled = useCallback(() => {
    const next = !summary.enabled
    onSummaryChange({ enabled: next })
    updateChapter(bookId, summary.id, { enabled: next }).catch(() => onSummaryChange({ enabled: !next }))
  }, [bookId, onSummaryChange, summary.enabled, summary.id])

  const words = detail ? detail.blocks.reduce((sum, b) => sum + wordCount(b.text), 0) : null

  return (
    <Card className="p-0">
      <div className="flex items-center gap-3 px-4 py-3">
        <input
          type="checkbox"
          checked={summary.enabled}
          onChange={toggleEnabled}
          title="Include this chapter in the render"
          className="h-4 w-4 accent-accent"
        />
        <button
          className="flex flex-1 items-center gap-2 text-left"
          onClick={toggleExpand}
        >
          <span className="font-mono-tabular text-xs text-text-3">{summary.index + 1}</span>
          {editingTitle ? (
            <input
              autoFocus
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={saveTitle}
              onKeyDown={(e) => {
                if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                if (e.key === 'Escape') {
                  setTitleDraft(summary.title)
                  setEditingTitle(false)
                }
              }}
              onClick={(e) => e.stopPropagation()}
              className="rounded border border-border bg-elevated px-1.5 py-0.5 text-sm text-text"
            />
          ) : (
            <span
              className={['text-sm', summary.enabled ? 'text-text' : 'text-text-3 line-through'].join(' ')}
              onClick={(e) => {
                e.stopPropagation()
                setEditingTitle(true)
              }}
            >
              {summary.title}
            </span>
          )}
        </button>
        <span className="text-xs text-text-3">{summary.block_count} blocks</span>
        <button onClick={toggleExpand} className="text-text-3 hover:text-text">
          {expanded ? '▾' : '▸'}
        </button>
      </div>

      {expanded && (
        <div className="border-t border-border px-4 py-3">
          {loading ? (
            <Spinner />
          ) : detail ? (
            <>
              <p className="mb-3 text-xs text-text-3">
                {words} words · ~{formatMinutes((words ?? 0) / WORDS_PER_MINUTE)} estimated
              </p>
              <div className="flex flex-col gap-2">
                {detail.blocks.map((block) => (
                  <BlockEditor
                    key={block.id}
                    bookId={bookId}
                    chapterId={summary.id}
                    block={block}
                  />
                ))}
              </div>
            </>
          ) : null}
        </div>
      )}
    </Card>
  )
}

function BlockEditor({
  bookId,
  chapterId,
  block,
}: {
  bookId: number
  chapterId: number
  block: { id: number; kind: string; text: string }
}) {
  const [text, setText] = useState(block.text)
  const [saving, setSaving] = useState(false)

  const save = useCallback(() => {
    if (text === block.text) return
    setSaving(true)
    updateBlock(bookId, chapterId, block.id, text).finally(() => setSaving(false))
  }, [block.id, block.text, bookId, chapterId, text])

  return (
    <div className="flex gap-2">
      <span className="mt-1.5 w-14 shrink-0 text-[10px] uppercase tracking-wide text-text-3">{block.kind}</span>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={save}
        rows={Math.min(6, Math.max(1, Math.ceil(text.length / 80)))}
        className="flex-1 resize-y rounded border border-border bg-elevated px-2 py-1 text-sm text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
      />
      {saving && <Spinner className="mt-1.5" />}
    </div>
  )
}

/** Every past render of this book — including its downloads once finished — so a
 * returning visitor never has to remember or re-find a specific Job page URL to get
 * back to a finished audiobook's exports. [M5-9] */
function RenderHistory({ bookId }: { bookId: number }) {
  const [jobs, setJobs] = useState<Job[] | null>(null)

  useEffect(() => {
    listBookJobs(bookId).then(setJobs)
  }, [bookId])

  if (jobs === null || jobs.length === 0) return null

  return (
    <Card className="mb-6 flex flex-col gap-3 p-5">
      <h3 className="text-sm font-medium text-text">Renders</h3>
      <div className="flex flex-col gap-3">
        {jobs.map((job) => (
          <div key={job.id} className="flex flex-col gap-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
            <div className="flex items-center justify-between gap-2">
              <Link to={`/jobs/${job.id}`} className="text-sm text-text hover:text-accent">
                {new Date(job.created_at).toLocaleString()} · {job.voice}
              </Link>
              <JobStatusBadge status={job.status} />
            </div>
            <JobDownloads job={job} />
          </div>
        ))}
      </div>
    </Card>
  )
}

export default function Book() {
  const { bookId } = useParams<{ bookId: string }>()
  const id = Number(bookId)
  const [book, setBook] = useState<BookDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getBook(id)
      .then(setBook)
      .catch((e) => setError(String(e)))
  }, [id])

  const patchSummary = useCallback(
    (chapterId: number, patch: Partial<ChapterSummary>) => {
      setBook((prev) =>
        prev
          ? { ...prev, chapters: prev.chapters.map((c) => (c.id === chapterId ? { ...c, ...patch } : c)) }
          : prev,
      )
    },
    [],
  )

  if (error) return <div className="p-8 text-sm text-danger">{error}</div>
  if (!book) return <div className="p-8 text-sm text-text-2">Loading…</div>

  const enabledCount = book.chapters.filter((c) => c.enabled).length

  return (
    <div className="mx-auto max-w-3xl p-8">
      <Link to="/" className="text-xs text-text-3 hover:text-text">
        ← Library
      </Link>
      <div className="mb-6 mt-2 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-text">{book.title}</h2>
          {book.author && <p className="text-sm text-text-2">{book.author}</p>}
          <div className="mt-2 flex items-center gap-1.5">
            <LanguageSelector
              bookId={book.id}
              language={book.language}
              onChange={(language) => setBook((prev) => (prev ? { ...prev, language } : prev))}
            />
            <Badge>{book.source_format}</Badge>
            <Badge>
              {enabledCount}/{book.chapters.length} chapters enabled
            </Badge>
          </div>
        </div>
        <Link to={`/books/${book.id}/render`}>
          <Button>Render Audiobook</Button>
        </Link>
      </div>

      <RenderHistory bookId={book.id} />

      <div className="mb-6 flex flex-col gap-2">
        {book.chapters.map((chapter) => (
          <ChapterRow
            key={chapter.id}
            bookId={book.id}
            summary={chapter}
            onSummaryChange={(patch) => patchSummary(chapter.id, patch)}
          />
        ))}
      </div>

      <LexiconEditor bookId={book.id} />
    </div>
  )
}
