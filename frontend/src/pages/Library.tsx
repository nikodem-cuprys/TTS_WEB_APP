import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'
import { listBooks, listFormats, uploadBook, type BookSummary, type FormatInfo } from '../lib/api'

function acceptAttr(formats: FormatInfo[]): string {
  return formats
    .filter((f) => f.available)
    .map((f) => `.${f.extension}`)
    .join(',')
}

export default function Library() {
  const [books, setBooks] = useState<BookSummary[] | null>(null)
  const [formats, setFormats] = useState<FormatInfo[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(() => {
    listBooks().then(setBooks).catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    refresh()
    listFormats().then(setFormats).catch(() => {})
  }, [refresh])

  const handleFile = useCallback(
    async (file: File) => {
      setError(null)
      setUploading(true)
      setUploadProgress(0)
      try {
        await uploadBook(file, setUploadProgress)
        refresh()
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e))
      } finally {
        setUploading(false)
      }
    },
    [refresh],
  )

  const unavailable = formats.filter((f) => !f.available)

  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">Library</h2>
      </div>

      <Card
        className={[
          'mb-8 flex flex-col items-center justify-center gap-2 border-dashed p-8 text-center transition-colors',
          dragOver ? 'border-accent bg-elevated' : '',
        ].join(' ')}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          const file = e.dataTransfer.files?.[0]
          if (file) handleFile(file)
        }}
      >
        {uploading ? (
          <>
            <Spinner />
            <p className="text-sm text-text-2">Uploading… {Math.round(uploadProgress * 100)}%</p>
          </>
        ) : (
          <>
            <p className="text-sm text-text-2">Drag a book file here, or</p>
            <Button size="sm" onClick={() => fileInputRef.current?.click()}>
              Choose file
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept={acceptAttr(formats)}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleFile(file)
                e.target.value = ''
              }}
            />
            {unavailable.length > 0 && (
              <p className="mt-1 text-xs text-text-3">
                {unavailable.map((f) => f.extension).join(', ')} need Calibre installed — see the README.
              </p>
            )}
          </>
        )}
      </Card>

      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      {books === null ? (
        <p className="text-sm text-text-2">Loading…</p>
      ) : books.length === 0 ? (
        <p className="text-sm text-text-2">No books yet — upload one above.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {books.map((book) => (
            <Link key={book.id} to={`/books/${book.id}`}>
              <Card className="flex h-full flex-col gap-2 p-4 transition-colors hover:border-text-3">
                <div className="flex aspect-[2/3] items-center justify-center rounded bg-elevated text-text-3">
                  <span className="px-2 text-center text-xs">{book.title}</span>
                </div>
                <div>
                  <p className="truncate text-sm font-medium text-text" title={book.title}>
                    {book.title}
                  </p>
                  {book.author && <p className="truncate text-xs text-text-2">{book.author}</p>}
                </div>
                <div className="mt-auto flex items-center gap-1.5">
                  <Badge>{book.language}</Badge>
                  <Badge>{book.chapter_count} ch</Badge>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
