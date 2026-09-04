import { useEffect, useState } from 'react'
import Button from './ui/Button'
import Card from './ui/Card'
import {
  createLexiconEntry,
  deleteLexiconEntry,
  listLexicon,
  updateLexiconEntry,
  type LexiconEntry,
} from '../lib/api'

export default function LexiconEditor({ bookId }: { bookId: number }) {
  const [entries, setEntries] = useState<LexiconEntry[] | null>(null)
  const [pattern, setPattern] = useState('')
  const [replacement, setReplacement] = useState('')
  const [isRegex, setIsRegex] = useState(false)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = () => {
    listLexicon(bookId).then(setEntries).catch((e) => setError(String(e)))
  }

  useEffect(refresh, [bookId])

  const handleAdd = async () => {
    if (!pattern.trim() || !replacement.trim()) return
    setAdding(true)
    setError(null)
    try {
      await createLexiconEntry(bookId, { pattern, replacement, is_regex: isRegex })
      setPattern('')
      setReplacement('')
      setIsRegex(false)
      refresh()
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setAdding(false)
    }
  }

  const toggleEnabled = async (entry: LexiconEntry) => {
    setEntries((prev) => prev?.map((e) => (e.id === entry.id ? { ...e, enabled: !e.enabled } : e)) ?? prev)
    try {
      await updateLexiconEntry(bookId, entry.id, { enabled: !entry.enabled })
    } catch {
      refresh() // revert the optimistic update on failure
    }
  }

  const handleDelete = async (entryId: number) => {
    setEntries((prev) => prev?.filter((e) => e.id !== entryId) ?? prev)
    await deleteLexiconEntry(bookId, entryId).catch(refresh)
  }

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div>
        <h3 className="text-sm font-medium text-text">Pronunciation lexicon</h3>
        <p className="text-xs text-text-2">
          Fix names or invented words the voice mispronounces. Editing an entry only re-renders the
          chunks that contain it.
        </p>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {entries === null ? (
        <p className="text-sm text-text-2">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-text-3">No entries yet.</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {entries.map((entry) => (
            <div key={entry.id} className="flex items-center gap-2 rounded border border-border px-2 py-1.5">
              <input
                type="checkbox"
                checked={entry.enabled}
                onChange={() => toggleEnabled(entry)}
                className="h-4 w-4 accent-accent"
                title="Enabled"
              />
              <span className={['flex-1 truncate text-sm', entry.enabled ? 'text-text' : 'text-text-3 line-through'].join(' ')}>
                <span className="font-mono-tabular">{entry.pattern}</span>
                <span className="text-text-3"> → </span>
                <span className="font-mono-tabular">{entry.replacement}</span>
                {entry.is_regex && <span className="ml-1.5 text-[10px] uppercase text-text-3">regex</span>}
              </span>
              <button
                onClick={() => handleDelete(entry.id)}
                className="text-xs text-text-3 hover:text-danger"
                title="Delete"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <div className="flex gap-2">
          <input
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            placeholder="pattern (e.g. a name)"
            className="flex-1 rounded border border-border bg-elevated px-2 py-1 text-sm text-text"
          />
          <input
            value={replacement}
            onChange={(e) => setReplacement(e.target.value)}
            placeholder="replacement (phonetic spelling)"
            className="flex-1 rounded border border-border bg-elevated px-2 py-1 text-sm text-text"
          />
        </div>
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-1.5 text-xs text-text-2">
            <input
              type="checkbox"
              checked={isRegex}
              onChange={(e) => setIsRegex(e.target.checked)}
              className="h-3.5 w-3.5 accent-accent"
            />
            Regex pattern
          </label>
          <Button size="sm" onClick={handleAdd} disabled={adding || !pattern.trim() || !replacement.trim()}>
            {adding ? 'Adding…' : 'Add entry'}
          </Button>
        </div>
      </div>
    </Card>
  )
}
