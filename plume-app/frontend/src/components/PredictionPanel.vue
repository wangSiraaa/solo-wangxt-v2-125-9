<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type {
  MetRow,
  PlumeGridRequest,
  PredictionDirection,
  PredictionParameter,
  SourceRow,
} from '../types'
import {
  DEFAULT_PREDICTION_FORM,
  DIRECTION_LABELS,
  PARAMETER_LABELS,
  PARAMETER_UNITS,
  type PredictionFormState,
} from '../prediction'

const props = defineProps<{
  sources: SourceRow[]
  meteorology: MetRow[]
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'submit', payload: {
    request: PlumeGridRequest
    receptor: [number, number]
    parameter: PredictionParameter
    variantValue: number
    prediction: PredictionDirection
    label: string | null
  }): void
  (e: 'pick-receptor', on: boolean): void
  (e: 'receptor-change', lonlat: [number, number] | null): void
  (e: 'source-change', lonlat: [number, number]): void
  (e: 'reset'): void
}>()

const form = ref<PredictionFormState>({ ...DEFAULT_PREDICTION_FORM })
// stage: setup 教师配题 -> predict 学生提交方向 -> reveal 揭晓
const stage = ref<'setup' | 'predict'>('setup')
const picking = ref(false)

function patch(p: Partial<PredictionFormState>) {
  form.value = { ...form.value, ...p }
}

function applySource(s: SourceRow) {
  patch({
    sourceId: s.id,
    stackHeight: s.stack_height_m,
    emission: s.emission_rate_g_s,
    stackDia: s.stack_diameter_m,
    exitV: s.exit_velocity_ms,
    stackT: s.stack_temp_k,
  })
}
function applyMet(m: MetRow) {
  patch({
    metId: m.id,
    windFrom: m.wind_from_deg,
    windSpeed: m.wind_speed_ms,
    stability: m.stability_class,
    ambientT: m.ambient_temp_k,
    pressure: m.pressure_hpa,
    background: m.background_conc_ug_m3,
  })
}

function onSourceChange(id: number) {
  const s = props.sources.find((x) => x.id === id)
  if (s) {
    applySource(s)
    emit('source-change', [s.lon, s.lat])
  }
}
function onMetChange(id: number) {
  const m = props.meteorology.find((x) => x.id === id)
  if (m) applyMet(m)
}

watch(
  () => [form.value.receptorLon, form.value.receptorLat],
  () => {
    if (receptorReady.value) {
      emit('receptor-change', [form.value.receptorLon!, form.value.receptorLat!])
    } else {
      emit('receptor-change', null)
    }
  },
)

const currentSource = computed(() =>
  props.sources.find((x) => x.id === form.value.sourceId) ?? null,
)
const currentMet = computed(() =>
  props.meteorology.find((x) => x.id === form.value.metId) ?? null,
)

const baselineCalm = computed(
  () => form.value.windSpeed < form.value.calmThreshold,
)

const baselineValue = computed(() => {
  if (form.value.parameter === 'stack_height_m') return form.value.stackHeight
  if (form.value.parameter === 'wind_speed_ms') return form.value.windSpeed
  return form.value.emission
})

const defaultVariantHint = computed(() => {
  if (form.value.parameter === 'emission_rate_g_s')
    return `例如取基准的 2 倍：${2 * baselineValue.value}`
  if (form.value.parameter === 'wind_speed_ms')
    return `例如取 6.0；也可取 0.3 演示静风变体`
  return `例如取 ${Math.round(baselineValue.value * 1.5)}`
})

function chooseParameter(p: PredictionParameter) {
  patch({ parameter: p, variantValue: null })
}

// 受体：下风向预设距离 -> 经纬度（与后端同一等距圆柱近似）
function presetReceptor() {
  const s = currentSource.value
  if (!s) return
  const theta = ((form.value.windFrom + 180) % 360) * (Math.PI / 180)
  const x = form.value.receptorPresetM
  const east = x * Math.sin(theta)
  const north = x * Math.cos(theta)
  const lat0 = (s.lat * Math.PI) / 180
  const lon = s.lon + (east / (6371000 * Math.cos(lat0))) * (180 / Math.PI)
  const lat = s.lat + (north / 6371000) * (180 / Math.PI)
  patch({ receptorLon: lon, receptorLat: lat })
}

function togglePick() {
  picking.value = !picking.value
  emit('pick-receptor', picking.value)
}

defineExpose({
  onMapClick(p: { lon: number; lat: number }) {
    if (!picking.value) return
    patch({ receptorLon: p.lon, receptorLat: p.lat })
    picking.value = false
    emit('pick-receptor', false)
  },
})

const receptorReady = computed(
  () =>
    form.value.receptorLon !== null &&
    form.value.receptorLat !== null &&
    Number.isFinite(form.value.receptorLon) &&
    Number.isFinite(form.value.receptorLat),
)
const variantReady = computed(
  () =>
    form.value.variantValue !== null &&
    Number.isFinite(form.value.variantValue) &&
    form.value.variantValue >= 0,
)

const canLock = computed(
  () =>
    !!currentSource.value &&
    !!currentMet.value &&
    !baselineCalm.value &&
    receptorReady.value &&
    variantReady.value,
)

function lockQuestion() {
  if (!canLock.value) return
  stage.value = 'predict'
}

function buildRequest(): PlumeGridRequest {
  const s = currentSource.value!
  return {
    source: {
      name: s.name,
      lon: s.lon,
      lat: s.lat,
      stack_height_m: form.value.stackHeight,
      emission_rate_g_s: form.value.emission,
      stack_diameter_m: form.value.stackDia,
      exit_velocity_ms: form.value.exitV,
      stack_temp_k: form.value.stackT,
      pollutant: s.pollutant,
    },
    meteorology: {
      name: currentMet.value!.name,
      wind_from_deg: form.value.windFrom,
      wind_speed_ms: form.value.windSpeed,
      stability_class: form.value.stability,
      ambient_temp_k: form.value.ambientT,
      pressure_hpa: form.value.pressure,
      background_conc_ug_m3: form.value.background,
    },
    grid: {
      downwind_extent_m: 6000,
      crosswind_extent_m: 2000,
      upwind_extent_m: 300,
      nx: 121,
      ny: 81,
    },
    plume_rise: { use_plume_rise: form.value.useRise },
    parameterization: form.value.parameterization,
    power_law:
      form.value.parameterization === 'power_law'
        ? { ay: form.value.ay, py: form.value.py, az: form.value.az, pz: form.value.pz }
        : null,
    calm_threshold_ms: form.value.calmThreshold,
  }
}

function submitPrediction(prediction: PredictionDirection) {
  if (!canLock.value) return
  emit('submit', {
    request: buildRequest(),
    receptor: [form.value.receptorLon!, form.value.receptorLat!],
    parameter: form.value.parameter,
    variantValue: form.value.variantValue!,
    prediction,
    label: form.value.label.trim() ? form.value.label.trim() : null,
  })
}
</script>

<template>
  <div class="panel">
    <!-- ============ 阶段一：教师配题 ============ -->
    <template v-if="stage === 'setup'">
      <div class="section">
        <h2>课堂预测练习 · 第 1 步：教师配题</h2>
        <div class="notice info">
          先固定受体与基准输入，只改变<b>一项</b>参数；学生先提交方向预测，
          系统才运行两次实际计算。方向以受体处实际浓度判定，
          不使用“风速越大必然降低”等经验口诀。
        </div>
      </div>

      <div class="section">
        <h2>基准情景</h2>
        <label class="field">
          <span class="lbl">排放源</span>
          <select
            class="num"
            :value="form.sourceId"
            @change="onSourceChange(Number(($event.target as HTMLSelectElement).value))"
          >
            <option v-for="s in sources" :key="s.id" :value="s.id">
              {{ s.name }}（{{ s.pollutant }}）
            </option>
          </select>
        </label>
        <label class="field">
          <span class="lbl">气象情景</span>
          <select
            class="num"
            :value="form.metId"
            @change="onMetChange(Number(($event.target as HTMLSelectElement).value))"
          >
            <option v-for="m in meteorology" :key="m.id" :value="m.id">
              {{ m.name }}
            </option>
          </select>
        </label>
        <div class="row2">
          <label class="field">
            <span class="lbl">烟囱高 H（m）<b>{{ form.stackHeight }}</b></span>
            <input type="range" min="5" max="250" step="1" :value="form.stackHeight"
              @input="patch({ stackHeight: Number(($event.target as HTMLInputElement).value) })" />
          </label>
          <label class="field">
            <span class="lbl">排放率 Q（g/s）<b>{{ form.emission }}</b></span>
            <input type="range" min="0.5" max="200" step="0.5" :value="form.emission"
              @input="patch({ emission: Number(($event.target as HTMLInputElement).value) })" />
          </label>
          <label class="field">
            <span class="lbl">风速 u（m/s）<b>{{ form.windSpeed }}</b></span>
            <input type="range" min="0" max="12" step="0.1" :value="form.windSpeed"
              @input="patch({ windSpeed: Number(($event.target as HTMLInputElement).value) })" />
          </label>
          <label class="field">
            <span class="lbl">风向（来向角）<b>{{ form.windFrom }}°</b></span>
            <input type="range" min="0" max="359" step="1" :value="form.windFrom"
              @input="patch({ windFrom: Number(($event.target as HTMLInputElement).value) })" />
          </label>
        </div>
        <div class="row2">
          <label class="field"><span class="lbl">稳定度</span>
            <select class="num" :value="form.stability"
              @change="patch({ stability: ($event.target as HTMLSelectElement).value as PredictionFormState['stability'] })">
              <option v-for="c in ['A','B','C','D','E','F']" :key="c" :value="c">{{ c }}</option>
            </select></label>
          <label class="field"><span class="lbl">背景（μg/m³）<b>{{ form.background }}</b></span>
            <input type="range" min="0" max="100" step="0.5" :value="form.background"
              @input="patch({ background: Number(($event.target as HTMLInputElement).value) })" /></label>
        </div>
        <div class="toggle">
          <input type="checkbox" :checked="form.useRise"
            @change="patch({ useRise: ($event.target as HTMLInputElement).checked })" />
          叠加 Holland 抬升 Δh（开启后风速还会改变 Δh，方向更不能凭口诀）
        </div>
        <div v-if="baselineCalm" class="notice err">
          基准情景为静风（u={{ form.windSpeed }} &lt; {{ form.calmThreshold }}），
          题目不成立：基准必须可计算。要演示静风请把静风设为<b>变体</b>取值。
        </div>
      </div>

      <div class="section">
        <h2>固定受体</h2>
        <div class="row2">
          <label class="field"><span class="lbl">下风向预设距离（m）</span>
            <input class="num" type="number" step="50" min="50" :value="form.receptorPresetM"
              @input="patch({ receptorPresetM: Number(($event.target as HTMLInputElement).value) })" /></label>
          <label class="field"><span class="lbl">&nbsp;</span>
            <button class="ghost" type="button" @click="presetReceptor">放到下风向该距离</button></label>
        </div>
        <button class="ghost" type="button" @click="togglePick">
          {{ picking ? '取消点选' : '在地图上点选受体' }}
        </button>
        <div v-if="receptorReady" class="notice info" style="margin-top:6px">
          受体经纬度：{{ form.receptorLon!.toFixed(5) }}, {{ form.receptorLat!.toFixed(5) }}
        </div>
      </div>

      <div class="section">
        <h2>唯一可变参数</h2>
        <div class="param-grid">
          <button
            v-for="p in (['emission_rate_g_s','wind_speed_ms','stack_height_m'] as PredictionParameter[])"
            :key="p"
            type="button"
            class="ghost param-btn"
            :class="{ active: form.parameter === p }"
            @click="chooseParameter(p)"
          >
            {{ PARAMETER_LABELS[p] }}
          </button>
        </div>
        <label class="field" style="margin-top:8px">
          <span class="lbl">
            基准值 <b>{{ baselineValue }} {{ PARAMETER_UNITS[form.parameter] }}</b>
            → 变体取值（{{ PARAMETER_UNITS[form.parameter] }}）
          </span>
          <input class="num" type="number" min="0" step="0.1" :value="form.variantValue ?? ''"
            placeholder="由教师填入变体取值"
            @input="patch({ variantValue: Number(($event.target as HTMLInputElement).value) })" />
          <span class="muted" style="font-size:11px">{{ defaultVariantHint }}</span>
        </label>
        <label class="field">
          <span class="lbl">题次备注（可选）</span>
          <input class="num" type="text" maxlength="80" v-model="form.label" />
        </label>
      </div>

      <button :disabled="!canLock" @click="lockQuestion">锁定题目，进入学生预测</button>
    </template>

    <!-- ============ 阶段二：学生预测（不显示任何结果） ============ -->
    <template v-else>
      <div class="section">
        <h2>第 2 步：学生预测</h2>
        <div class="notice info">
          下列输入改变后，固定受体处的<b>总浓度</b>会怎样变化？
          请先凭物理分析选择方向；提交前不展示任何计算结果。
        </div>
      </div>

      <div class="section">
        <h2>题目摘要</h2>
        <dl class="kv">
          <dt>固定受体</dt>
          <dd>{{ form.receptorLon!.toFixed(4) }}, {{ form.receptorLat!.toFixed(4) }}</dd>
          <dt>受体距源预设</dt>
          <dd>{{ form.receptorPresetM }} m（下风向）</dd>
          <dt>基准 {{ PARAMETER_LABELS[form.parameter] }}</dt>
          <dd><b>{{ baselineValue }} {{ PARAMETER_UNITS[form.parameter] }}</b></dd>
          <dt>变体取值</dt>
          <dd><b>{{ form.variantValue }} {{ PARAMETER_UNITS[form.parameter] }}</b></dd>
          <dt>基准风速 / 烟囱高 / Q</dt>
          <dd>{{ form.windSpeed }} m/s · {{ form.stackHeight }} m · {{ form.emission }} g/s</dd>
          <dt>稳定度 / 背景</dt>
          <dd>{{ form.stability }} / {{ form.background }} μg/m³</dd>
          <dt>Holland 抬升</dt>
          <dd>{{ form.useRise ? '开启' : '关闭' }}</dd>
        </dl>
        <div class="muted" style="font-size:11px;margin-top:4px">
          其它输入保持完全相同；两次计算使用同一个现有高斯烟羽模型。
        </div>
      </div>

      <div class="section">
        <h2>我的预测</h2>
        <div class="predict-grid">
          <button
            v-for="d in (['up','down','same'] as PredictionDirection[])"
            :key="d"
            type="button"
            :disabled="loading"
            @click="submitPrediction(d)"
          >
            {{ DIRECTION_LABELS[d] }}
          </button>
        </div>
        <button class="ghost" style="margin-top:10px" @click="stage = 'setup'">
          返回修改题目
        </button>
      </div>
    </template>
  </div>
</template>
