export interface FormState {
  sourceId: number
  metId: number
  stackHeight: number
  emission: number
  stackDia: number
  exitV: number
  stackT: number
  windFrom: number
  windSpeed: number
  stability: 'A' | 'B' | 'C' | 'D' | 'E' | 'F'
  ambientT: number
  pressure: number
  background: number
  useRise: boolean
  parameterization: 'briggs_rural' | 'power_law'
  ay: number
  py: number
  az: number
  pz: number
  downwindExtent: number
  crosswindExtent: number
  upwindExtent: number
  nx: number
  ny: number
  calmThreshold: number
}

import type { MeteorologyInput, SourceInput, SourceRow } from './types'

/** 由面板表单 + 源记录组装模型输入（主计算与预测练习共用，保证基准一致）。 */
export function scenarioFromForm(
  form: FormState,
  s: SourceRow,
): {
  source: SourceInput
  meteorology: MeteorologyInput
  plume_rise: { use_plume_rise: boolean }
  parameterization: 'briggs_rural' | 'power_law'
  power_law: { ay: number; py: number; az: number; pz: number } | null
  calm_threshold_ms: number
} {
  return {
    source: {
      name: s.name,
      lon: s.lon,
      lat: s.lat,
      stack_height_m: form.stackHeight,
      emission_rate_g_s: form.emission,
      stack_diameter_m: form.stackDia,
      exit_velocity_ms: form.exitV,
      stack_temp_k: form.stackT,
      pollutant: s.pollutant,
    },
    meteorology: {
      name: '界面情景',
      wind_from_deg: form.windFrom,
      wind_speed_ms: form.windSpeed,
      stability_class: form.stability,
      ambient_temp_k: form.ambientT,
      pressure_hpa: form.pressure,
      background_conc_ug_m3: form.background,
    },
    plume_rise: { use_plume_rise: form.useRise },
    parameterization: form.parameterization,
    power_law:
      form.parameterization === 'power_law'
        ? { ay: form.ay, py: form.py, az: form.az, pz: form.pz }
        : null,
    calm_threshold_ms: form.calmThreshold,
  }
}

export const DEFAULT_FORM: FormState = {
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
  downwindExtent: 6000,
  crosswindExtent: 2000,
  upwindExtent: 300,
  nx: 121,
  ny: 81,
  calmThreshold: 1,
}
