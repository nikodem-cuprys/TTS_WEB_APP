import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import Select from '../components/ui/Select'
import Slider from '../components/ui/Slider'
import { createJob, getBook, listVoices, previewVoice, type BookDetail, type VoiceInfo } from '../lib/api'

export default function Render() {
  const { bookId } = useParams<{ bookId: string }>()
  const id = Number(bookId)
  const navigate = useNavigate()

  const [book, setBook] = useState<BookDetail | null>(null)
  const [voices, setVoices] = useState<VoiceInfo[] | null>(null)
  const [voice, setVoice] = useState('')
  const [speed, setSpeed] = useState(1.0)
  const [previewing, setPreviewing] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    getBook(id).then(setBook).catch((e) => setError(String(e)))
    listVoices().then(setVoices).catch((e) => setError(String(e)))
  }, [id])

  const matchingVoices = useMemo(
    () => (book && voices ? voices.filter((v) => v.language === book.language) : []),
    [book, voices],
  )

  useEffect(() => {
    if (matchingVoices.length > 0 && !voice) setVoice(matchingVoices[0].id)
  }, [matchingVoices, voice])

  const handlePreview = async () => {
    if (!voice) return
    setPreviewing(true)
    setError(null)
    try {
      const blob = await previewVoice(voice)
      const url = URL.createObjectURL(blob)
      if (audioRef.current) {
        audioRef.current.src = url
        await audioRef.current.play()
      }
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setPreviewing(false)
    }
  }

  const handleStart = async () => {
    if (!voice) return
    setStarting(true)
    setError(null)
    try {
      const job = await createJob(id, voice, speed)
      navigate(`/jobs/${job.id}`)
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
      setStarting(false)
    }
  }

  if (error && !book) return <div className="p-8 text-sm text-danger">{error}</div>
  if (!book || voices === null) return <div className="p-8 text-sm text-text-2">Loading…</div>

  const enabledChapters = book.chapters.filter((c) => c.enabled).length
  const unsupportedLanguage = matchingVoices.length === 0

  return (
    <div className="mx-auto max-w-xl p-8">
      <Link to={`/books/${book.id}`} className="text-xs text-text-3 hover:text-text">
        ← {book.title}
      </Link>
      <h2 className="mb-6 mt-2 text-lg font-semibold text-text">Render Audiobook</h2>

      <Card className="flex flex-col gap-5 p-5">
        <div>
          <p className="text-sm text-text-2">
            {enabledChapters} of {book.chapters.length} chapters will be rendered.
          </p>
        </div>

        {unsupportedLanguage ? (
          <p className="text-sm text-warn">
            No voice is available yet for language "{book.language}". English, Polish, German, and
            Chinese are supported — if this book is actually one of those, fix the language on the
            book's page first.
          </p>
        ) : (
          <>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text-2">Voice</span>
              <div className="flex items-center gap-2">
                <Select value={voice} onChange={(e) => setVoice(e.target.value)} className="flex-1">
                  {matchingVoices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.id} ({v.gender ?? 'unknown'})
                    </option>
                  ))}
                </Select>
                <Button size="sm" variant="secondary" onClick={handlePreview} disabled={previewing}>
                  {previewing ? '…' : '▶ Preview'}
                </Button>
              </div>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <audio ref={audioRef} className="hidden" />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text-2">Speed: {speed.toFixed(2)}x</span>
              <Slider min={0.5} max={2.0} step={0.05} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text-2">Output format</span>
              <div className="flex items-center gap-2 text-sm text-text-2">
                <input type="checkbox" checked disabled className="h-4 w-4" />
                MP3 (more formats land in a later milestone)
              </div>
            </label>
          </>
        )}

        {error && <p className="text-sm text-danger">{error}</p>}

        <Button onClick={handleStart} disabled={unsupportedLanguage || starting || enabledChapters === 0}>
          {starting ? 'Starting…' : 'Start Render'}
        </Button>
      </Card>
    </div>
  )
}
