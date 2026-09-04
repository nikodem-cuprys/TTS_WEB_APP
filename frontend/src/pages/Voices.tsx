import { useEffect, useMemo, useRef, useState } from 'react'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { listVoices, previewVoice, type VoiceInfo } from '../lib/api'

// Matches backend/app/tts/registry.py's LANGUAGE_ROUTING — everything else Kokoro
// happens to catalog (es/fr/hi/it/ja/pt) has no engine routed to it yet.
const SUPPORTED_LANGUAGES = new Set(['en', 'pl', 'de', 'zh'])

export default function Voices() {
  const [voices, setVoices] = useState<VoiceInfo[] | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    listVoices()
      .then(setVoices)
      .catch((e) => setError(String(e)))
  }, [])

  const grouped = useMemo(() => {
    if (!voices) return []
    const byLanguage = new Map<string, VoiceInfo[]>()
    for (const v of voices) {
      const list = byLanguage.get(v.language) ?? []
      list.push(v)
      byLanguage.set(v.language, list)
    }
    return [...byLanguage.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [voices])

  const play = async (voiceId: string) => {
    setPlayingId(voiceId)
    setError(null)
    try {
      const blob = await previewVoice(voiceId)
      const url = URL.createObjectURL(blob)
      if (audioRef.current) {
        audioRef.current.src = url
        await audioRef.current.play()
      }
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setPlayingId(null)
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-8">
      <h2 className="mb-1 text-lg font-semibold text-text">Voices</h2>
      <p className="mb-6 text-sm text-text-2">
        English, Polish, German, and Chinese are wired up for rendering — other languages are
        catalogued (and previewable here) but not yet routed to a render.
      </p>

      {error && <p className="mb-4 text-sm text-danger">{error}</p>}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} className="hidden" />

      {voices === null ? (
        <p className="text-sm text-text-2">Loading…</p>
      ) : (
        <div className="flex flex-col gap-6">
          {grouped.map(([language, list]) => (
            <div key={language}>
              <div className="mb-2 flex items-center gap-2">
                <h3 className="text-sm font-medium text-text">{language}</h3>
                <Badge>{list.length} voices</Badge>
                {!SUPPORTED_LANGUAGES.has(language) && (
                  <Badge tone="warn">preview only, not usable yet</Badge>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {list.map((v) => (
                  <Card key={v.id} className="flex items-center justify-between gap-2 p-3">
                    <div>
                      <p className="text-sm text-text">{v.id}</p>
                      <p className="text-xs text-text-3">{v.gender ?? 'unknown'}</p>
                    </div>
                    <Button size="sm" variant="secondary" onClick={() => play(v.id)} disabled={playingId === v.id}>
                      {playingId === v.id ? '…' : '▶'}
                    </Button>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
