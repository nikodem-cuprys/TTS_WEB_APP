import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import Select from '../components/ui/Select'
import Slider from '../components/ui/Slider'
import {
  createJob,
  getBook,
  listVoices,
  previewVoice,
  EXPORT_FORMATS,
  VIDEO_STYLES,
  type BookDetail,
  type ExportFormat,
  type VideoStyle,
  type VoiceInfo,
} from '../lib/api'

const FORMAT_LABELS: Record<ExportFormat, string> = {
  mp3: 'MP3',
  m4b: 'M4B (chaptered audiobook)',
  opus: 'Opus',
  flac: 'FLAC',
  wav: 'WAV',
  srt: 'SRT subtitles',
  vtt: 'VTT subtitles',
  mp4: 'MP4 (video)',
  chapters: 'YouTube chapters + description',
}

const VIDEO_STYLE_LABELS: Record<VideoStyle, string> = {
  static: 'Static cover',
  waveform: 'Waveform overlay',
  kenburns: 'Ken Burns pan/zoom',
}

export default function Render() {
  const { bookId } = useParams<{ bookId: string }>()
  const id = Number(bookId)
  const navigate = useNavigate()

  const [book, setBook] = useState<BookDetail | null>(null)
  const [voices, setVoices] = useState<VoiceInfo[] | null>(null)
  const [voice, setVoice] = useState('')
  const [speed, setSpeed] = useState(1.0)
  const [formats, setFormats] = useState<ExportFormat[]>(['mp3'])
  const [videoStyle, setVideoStyle] = useState<VideoStyle>('static')
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

  const toggleFormat = (format: ExportFormat) => {
    setFormats((prev) =>
      prev.includes(format) ? prev.filter((f) => f !== format) : [...prev, format],
    )
  }

  const handleStart = async () => {
    if (!voice || formats.length === 0) return
    setStarting(true)
    setError(null)
    try {
      const job = await createJob(id, voice, speed, formats, videoStyle)
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

            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text-2">Output formats</span>
              <div className="grid grid-cols-2 gap-1.5">
                {EXPORT_FORMATS.map((format) => (
                  <label key={format} className="flex items-center gap-2 text-sm text-text-2">
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      checked={formats.includes(format)}
                      onChange={() => toggleFormat(format)}
                    />
                    {FORMAT_LABELS[format]}
                  </label>
                ))}
              </div>
              {formats.length === 0 && <p className="text-xs text-danger">Select at least one format.</p>}
            </div>

            {formats.includes('mp4') && (
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-text-2">Video style</span>
                <Select value={videoStyle} onChange={(e) => setVideoStyle(e.target.value as VideoStyle)}>
                  {VIDEO_STYLES.map((style) => (
                    <option key={style} value={style}>
                      {VIDEO_STYLE_LABELS[style]}
                    </option>
                  ))}
                </Select>
              </label>
            )}
          </>
        )}

        {error && <p className="text-sm text-danger">{error}</p>}

        <Button
          onClick={handleStart}
          disabled={unsupportedLanguage || starting || enabledChapters === 0 || formats.length === 0}
        >
          {starting ? 'Starting…' : 'Start Render'}
        </Button>
      </Card>
    </div>
  )
}
