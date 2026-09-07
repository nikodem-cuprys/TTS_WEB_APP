import { useEffect, useState } from 'react'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import { formatBytes } from '../lib/format'
import {
  getDiskUsage,
  getModelStatus,
  getSettings,
  updateSettings,
  type DiskUsage,
  type ModelStatus,
  type SettingsValues,
} from '../lib/api'

export default function Settings() {
  const [settings, setSettings] = useState<SettingsValues | null>(null)
  const [draft, setDraft] = useState<SettingsValues | null>(null)
  const [diskUsage, setDiskUsage] = useState<DiskUsage | null>(null)
  const [models, setModels] = useState<ModelStatus[] | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const load = () => {
    getSettings().then((s) => {
      setSettings(s)
      setDraft(s)
    })
    getDiskUsage().then(setDiskUsage)
    getModelStatus().then(setModels)
  }

  useEffect(load, [])

  const handleSave = async () => {
    if (!draft) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const updated = await updateSettings({
        tts_workers: draft.tts_workers,
        loudness_target_i: draft.loudness_target_i,
        loudness_target_tp: draft.loudness_target_tp,
        loudness_target_lra: draft.loudness_target_lra,
        mp4_part_limit_s: draft.mp4_part_limit_s,
      })
      setSettings(updated)
      setDraft(updated)
      setSaved(true)
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setSaving(false)
    }
  }

  const missingModels = models?.filter((m) => !m.present) ?? []
  const dirty = settings && draft && JSON.stringify(settings) !== JSON.stringify(draft)

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h2 className="mb-6 text-lg font-semibold text-text">Settings</h2>

      <div className="flex flex-col gap-6">
        <Card className="flex flex-col gap-4 p-5">
          <h3 className="text-sm font-medium text-text">Rendering</h3>
          {draft && (
            <>
              <label className="flex items-center justify-between gap-4">
                <span className="text-sm text-text-2">Worker processes</span>
                <input
                  type="number"
                  min={1}
                  max={16}
                  value={draft.tts_workers}
                  onChange={(e) => setDraft({ ...draft, tts_workers: Number(e.target.value) })}
                  className="w-20 rounded border border-border bg-elevated px-2 py-1 text-right text-sm text-text"
                />
              </label>
              <label className="flex items-center justify-between gap-4">
                <span className="text-sm text-text-2">Loudness target (LUFS)</span>
                <input
                  type="number"
                  step={0.5}
                  value={draft.loudness_target_i}
                  onChange={(e) => setDraft({ ...draft, loudness_target_i: Number(e.target.value) })}
                  className="w-20 rounded border border-border bg-elevated px-2 py-1 text-right text-sm text-text"
                />
              </label>
              <label className="flex items-center justify-between gap-4">
                <span className="text-sm text-text-2">True peak ceiling (dBTP)</span>
                <input
                  type="number"
                  step={0.5}
                  value={draft.loudness_target_tp}
                  onChange={(e) => setDraft({ ...draft, loudness_target_tp: Number(e.target.value) })}
                  className="w-20 rounded border border-border bg-elevated px-2 py-1 text-right text-sm text-text"
                />
              </label>
              <label className="flex items-center justify-between gap-4">
                <span className="text-sm text-text-2">Loudness range (LU)</span>
                <input
                  type="number"
                  step={0.5}
                  value={draft.loudness_target_lra}
                  onChange={(e) => setDraft({ ...draft, loudness_target_lra: Number(e.target.value) })}
                  className="w-20 rounded border border-border bg-elevated px-2 py-1 text-right text-sm text-text"
                />
              </label>
              <label className="flex items-center justify-between gap-4">
                <span className="text-sm text-text-2">MP4 part limit (hours)</span>
                <input
                  type="number"
                  min={0.25}
                  step={0.25}
                  value={Math.round((draft.mp4_part_limit_s / 3600) * 100) / 100}
                  onChange={(e) => setDraft({ ...draft, mp4_part_limit_s: Number(e.target.value) * 3600 })}
                  className="w-20 rounded border border-border bg-elevated px-2 py-1 text-right text-sm text-text"
                />
              </label>

              <div className="flex items-center gap-2 border-t border-border pt-3 text-xs text-text-3">
                <span>Output directory: {settings?.output_dir}</span>
              </div>

              {error && <p className="text-sm text-danger">{error}</p>}
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={handleSave} disabled={!dirty || saving}>
                  {saving ? 'Saving…' : 'Save'}
                </Button>
                {saved && !dirty && <span className="text-xs text-accent">Saved</span>}
              </div>
            </>
          )}
        </Card>

        <Card className="flex flex-col gap-3 p-5">
          <h3 className="text-sm font-medium text-text">Disk usage</h3>
          {diskUsage ? (
            <div className="grid grid-cols-2 gap-y-1.5 text-sm">
              <span className="text-text-2">Chunk cache</span>
              <span className="text-right font-mono-tabular text-text">{formatBytes(diskUsage.cache_bytes)}</span>
              <span className="text-text-2">Rendered output</span>
              <span className="text-right font-mono-tabular text-text">{formatBytes(diskUsage.output_bytes)}</span>
              <span className="text-text-2">Models</span>
              <span className="text-right font-mono-tabular text-text">{formatBytes(diskUsage.models_bytes)}</span>
              <span className="text-text-2">Free disk space</span>
              <span className="text-right font-mono-tabular text-text">{formatBytes(diskUsage.free_bytes)}</span>
            </div>
          ) : (
            <p className="text-sm text-text-2">Loading…</p>
          )}
        </Card>

        <Card className="flex flex-col gap-3 p-5">
          <h3 className="text-sm font-medium text-text">Models</h3>
          {models ? (
            <>
              <div className="flex flex-col gap-1.5">
                {models.map((m) => (
                  <div key={m.dest} className="flex items-center justify-between text-sm">
                    <span className="text-text-2">{m.dest}</span>
                    <Badge tone={m.present ? 'accent' : 'warn'}>{m.present ? 'present' : 'missing'}</Badge>
                  </div>
                ))}
              </div>
              {missingModels.length > 0 && (
                <p className="rounded border border-warn/30 bg-warn/10 p-2 text-xs text-warn">
                  Run <code>python scripts/fetch_models.py</code> from the repo root to download the
                  {' '}
                  {missingModels.length} missing model file{missingModels.length === 1 ? '' : 's'}.
                </p>
              )}
            </>
          ) : (
            <p className="text-sm text-text-2">Loading…</p>
          )}
        </Card>
      </div>
    </div>
  )
}
