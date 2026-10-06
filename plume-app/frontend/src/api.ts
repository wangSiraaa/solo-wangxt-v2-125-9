import type {
  ChecksReport,
  MetRow,
  PlumeGridRequest,
  PlumeGridResponse,
  PredictionExerciseRequest,
  PredictionRecord,
  SourceRow,
} from './types'

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let body: any = null
    try {
      body = await resp.json()
    } catch {
      /* ignore */
    }
    const err = new Error(
      body?.message || `请求失败：HTTP ${resp.status}`,
    ) as Error & { status: number; apiError?: any }
    err.status = resp.status
    err.apiError = body
    throw err
  }
  return resp.json() as Promise<T>
}

export const api = {
  health: () => fetch('/api/health').then((r) => jsonOrThrow<any>(r)),
  meta: () => fetch('/api/meta').then((r) => jsonOrThrow<any>(r)),
  sources: () => fetch('/api/sources').then((r) => jsonOrThrow<SourceRow[]>(r)),
  meteorology: () =>
    fetch('/api/meteorology').then((r) => jsonOrThrow<MetRow[]>(r)),
  plumeGrid: (req: PlumeGridRequest) =>
    fetch('/api/plume/grid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }).then((r) => jsonOrThrow<PlumeGridResponse>(r)),
  windCheck: (windFromDeg: number) =>
    fetch(
      `/api/plume/wind-check?wind_from_deg=${encodeURIComponent(windFromDeg)}`,
    ).then((r) => jsonOrThrow<any>(r)),
  checks: () => fetch('/api/checks').then((r) => jsonOrThrow<ChecksReport>(r)),
  createPrediction: (req: PredictionExerciseRequest) =>
    fetch('/api/predictions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }).then((r) => jsonOrThrow<PredictionRecord>(r)),
  predictions: () =>
    fetch('/api/predictions').then((r) => jsonOrThrow<PredictionRecord[]>(r)),
  prediction: (id: number) =>
    fetch(`/api/predictions/${id}`).then((r) => jsonOrThrow<PredictionRecord>(r)),
}
