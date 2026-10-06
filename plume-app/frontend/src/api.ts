import type {
  ChecksReport,
  MetRow,
  PlumeGridRequest,
  PlumeGridResponse,
  PredictionListResponse,
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
  predictionSubmit: (req: {
    base_request: PlumeGridRequest
    receptor_lonlat: [number, number]
    parameter: PredictionRecord['input_summary']['variable']['parameter']
    variant_value: number
    prediction: 'up' | 'down' | 'same'
    label?: string | null
  }) =>
    fetch('/api/predictions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }).then((r) => jsonOrThrow<PredictionRecord>(r)),
  predictionList: () =>
    fetch('/api/predictions').then((r) =>
      jsonOrThrow<PredictionListResponse>(r),
    ),
  predictionGet: (id: number) =>
    fetch(`/api/predictions/${id}`).then((r) =>
      jsonOrThrow<PredictionRecord>(r),
    ),
}
