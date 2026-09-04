export type HealthResponse = {
  status: string
  version: string
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error(`GET /api/health -> ${res.status}`)
  return res.json()
}
