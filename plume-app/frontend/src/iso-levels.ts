/**
 * 由场最大值生成 1-2-5 ×10^k 友好等值级。
 * 与后端 services.iso_levels 同一算法，供“总量场”显示使用；
 * 烟羽场仍使用后端返回的 iso_levels_ug_m3（保持单一数据源）。
 */
export function isoLevels(maxValue: number, nLevels = 8): number[] {
  if (!(maxValue > 0) || !Number.isFinite(maxValue)) return []
  const hiExp = Math.floor(Math.log10(maxValue))
  const mantissas = [1, 2, 5]
  const raw: number[] = []
  for (let e = hiExp - 4; e <= hiExp; e += 1) {
    for (const m of mantissas) {
      const v = m * 10 ** e
      if (v < maxValue) raw.push(v)
    }
  }
  const out: number[] = []
  for (const v of raw) {
    if (!out.length || Math.abs(v - out[out.length - 1]) / v > 1e-9) out.push(v)
  }
  return out.slice(-nLevels)
}
