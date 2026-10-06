import type {
  PredictionDirection,
  PredictionParameter,
  PredictionRecord,
  StabilityClass,
} from './types'

export interface PredictionFormState {
  // 基准输入（教师设定，学生预测阶段不可变）
  sourceId: number
  metId: number
  stackHeight: number
  emission: number
  stackDia: number
  exitV: number
  stackT: number
  windFrom: number
  windSpeed: number
  stability: StabilityClass
  ambientT: number
  pressure: number
  background: number
  useRise: boolean
  parameterization: 'briggs_rural' | 'power_law'
  ay: number
  py: number
  az: number
  pz: number
  calmThreshold: number
  // 固定受体
  receptorLon: number | null
  receptorLat: number | null
  receptorPresetM: number
  // 可变参数
  parameter: PredictionParameter
  variantValue: number | null
  // 学生预测（提交前不触发任何计算展示）
  prediction: PredictionDirection | null
  label: string
}

export const DEFAULT_PREDICTION_FORM: PredictionFormState = {
  sourceId: 1,
  metId: 1,
  stackHeight: 120,
  emission: 50,
  stackDia: 4,
  exitV: 18,
  stackT: 410,
  windFrom: 270,
  windSpeed: 6,
  stability: 'D',
  ambientT: 293.15,
  pressure: 1013,
  background: 15,
  useRise: false,
  parameterization: 'briggs_rural',
  ay: 0.22,
  py: 1,
  az: 0.16,
  pz: 1,
  calmThreshold: 1,
  receptorLon: null,
  receptorLat: null,
  receptorPresetM: 1000,
  parameter: 'emission_rate_g_s',
  variantValue: null,
  prediction: null,
  label: '',
}

export const PARAMETER_LABELS: Record<PredictionParameter, string> = {
  stack_height_m: '烟囱几何高度 H',
  wind_speed_ms: '风速 u',
  emission_rate_g_s: '排放率 Q',
}

export const PARAMETER_UNITS: Record<PredictionParameter, string> = {
  stack_height_m: 'm',
  wind_speed_ms: 'm/s',
  emission_rate_g_s: 'g/s',
}

export const DIRECTION_LABELS: Record<PredictionDirection, string> = {
  up: '升高 ↑',
  down: '降低 ↓',
  same: '基本不变 ≈',
}

// ---- 历史题次本地镜像（后端内存仓储重启/离线时仍可复看）----

const LS_KEY = 'plume-prediction-history-v1'
const LS_MAX = 200

export function loadLocalHistory(): PredictionRecord[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? (arr as PredictionRecord[]) : []
  } catch {
    return []
  }
}

export function saveLocalRecord(record: PredictionRecord): PredictionRecord[] {
  const all = loadLocalHistory().filter((r) => r.id !== record.id)
  all.push(record)
  const trimmed = all.slice(-LS_MAX)
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(trimmed))
  } catch {
    /* 存储满/不可用：忽略，不影响题次提交 */
  }
  return trimmed
}

export function getLocalRecord(id: number): PredictionRecord | null {
  return loadLocalHistory().find((r) => r.id === id) ?? null
}
