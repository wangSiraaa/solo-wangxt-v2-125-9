<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ControlPanel from './components/ControlPanel.vue'
import MapView from './components/MapView.vue'
import ResultPanel from './components/ResultPanel.vue'
import PredictionPanel from './components/PredictionPanel.vue'
import PredictionResultPanel, {
  type FieldChoice,
} from './components/PredictionResultPanel.vue'
import { api } from './api'
import { DEFAULT_FORM, type FormState } from './form'
import {
  getLocalRecord,
  loadLocalHistory,
  saveLocalRecord,
} from './prediction'
import type {
  MetRow,
  PlumeGridResponse,
  PredictionParameter,
  PredictionRecord,
  SourceRow,
} from './types'
import { legendStops } from './colors'

type Mode = 'explore' | 'predict'

const mode = ref<Mode>('explore')
const sources = ref<SourceRow[]>([])
const meteorology = ref<MetRow[]>([])
const form = ref<FormState>({ ...DEFAULT_FORM })
const result = ref<PlumeGridResponse | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)
const repo = ref<string>('…')
const showFill = ref(true)
const showIso = ref(true)
const showBg = ref(true)

// ---- 课堂预测练习状态 ----
const predictionPanel = ref<InstanceType<typeof PredictionPanel> | null>(null)
const record = ref<PredictionRecord | null>(null)
const predictError = ref<string | null>(null)
const submitting = ref(false)
const history = ref<PredictionRecord[]>([])
const loadingDetail = ref(false)
const fieldChoice = ref<FieldChoice>('baseline_plume')
const receptor = ref<[number, number] | null>(null)
const pickMode = ref(false)
const setupReceptor = ref<[number, number] | null>(null)
const setupSource = ref<[number, number] | null>(null)
const panelKey = ref(0)

const isCalm = computed(() => form.value.windSpeed < form.value.calmThreshold)

onMounted(async () => {
  try {
    const [h, s, m] = await Promise.all([
      api.health(),
      api.sources(),
      api.meteorology(),
    ])
    repo.value = h.repository
    sources.value = s
    meteorology.value = m
    applySource(s[0])
    applyMet(m[0])
    await run()
  } catch (e: any) {
    error.value = '初始化失败：' + e.message
  }
  // 历史：优先后端内存仓储；后端为空时退回本机 localStorage
  try {
    const remote = await api.predictionList()
    if (remote.items.length) history.value = remote.items
    else history.value = loadLocalHistory()
  } catch {
    history.value = loadLocalHistory()
  }
})

function applySource(s: SourceRow) {
  form.value = {
    ...form.value,
    sourceId: s.id,
    stackHeight: s.stack_height_m,
    emission: s.emission_rate_g_s,
    stackDia: s.stack_diameter_m,
    exitV: s.exit_velocity_ms,
    stackT: s.stack_temp_k,
  }
}

function applyMet(m: MetRow) {
  form.value = {
    ...form.value,
    metId: m.id,
    windFrom: m.wind_from_deg,
    windSpeed: m.wind_speed_ms,
    stability: m.stability_class,
    ambientT: m.ambient_temp_k,
    pressure: m.pressure_hpa,
    background: m.background_conc_ug_m3,
  }
}

function onSelectSource(id: number) {
  const s = sources.value.find((x) => x.id === id)
  if (s) {
    applySource(s)
    run()
  }
}
function onSelectMet(id: number) {
  const m = meteorology.value.find((x) => x.id === id)
  if (m) {
    applyMet(m)
    run()
  }
}

async function run() {
  if (isCalm.value) {
    result.value = null
    error.value =
      `静风（u=${form.value.windSpeed} m/s < 阈值 ${form.value.calmThreshold} m/s）：` +
      '定常高斯烟羽输运假设失效，模型拒绝硬算，不输出任何浓度场。'
    return
  }
  loading.value = true
  error.value = null
  const s = sources.value.find((x) => x.id === form.value.sourceId)!
  try {
    result.value = await api.plumeGrid({
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
        name: '界面情景',
        wind_from_deg: form.value.windFrom,
        wind_speed_ms: form.value.windSpeed,
        stability_class: form.value.stability,
        ambient_temp_k: form.value.ambientT,
        pressure_hpa: form.value.pressure,
        background_conc_ug_m3: form.value.background,
      },
      grid: {
        downwind_extent_m: form.value.downwindExtent,
        crosswind_extent_m: form.value.crosswindExtent,
        upwind_extent_m: form.value.upwindExtent,
        nx: form.value.nx,
        ny: form.value.ny,
      },
      plume_rise: { use_plume_rise: form.value.useRise },
      parameterization: form.value.parameterization,
      power_law:
        form.value.parameterization === 'power_law'
          ? { ay: form.value.ay, py: form.value.py, az: form.value.az, pz: form.value.pz }
          : null,
      calm_threshold_ms: form.value.calmThreshold,
    })
  } catch (e: any) {
    result.value = null
    if (e.apiError?.error === 'calm_wind') {
      error.value = e.apiError.message
    } else {
      error.value = e.message || '计算失败'
    }
  } finally {
    loading.value = false
  }
}

// ---- 预测练习 ----

const predictionMapResult = computed<PlumeGridResponse | null>(() => {
  const r = record.value
  if (!r) return null
  if (fieldChoice.value.startsWith('baseline')) return r.baseline.grid_response
  if (r.variant.computable) return r.variant.grid_response
  return r.baseline.grid_response
})

// 预测模式下地图背景层的显隐：看“总量”场时才叠加背景
const predictShowBg = computed(() => fieldChoice.value.endsWith('_total'))
const predictShowFill = computed(() => true)
const predictShowIso = computed(() => true)

function switchMode(m: Mode) {
  mode.value = m
  if (m === 'explore') {
    pickMode.value = false
  }
}

function onPredictionPick(on: boolean) {
  pickMode.value = on
}

function onSetupReceptorChange(lonlat: [number, number] | null) {
  setupReceptor.value = lonlat
}

function onSetupSourceChange(lonlat: [number, number]) {
  setupSource.value = lonlat
}

function onMapClick(p: { lon: number; lat: number }) {
  predictionPanel.value?.onMapClick(p)
}

async function onPredictionSubmit(payload: {
  request: import('./types').PlumeGridRequest
  receptor: [number, number]
  parameter: PredictionParameter
  variantValue: number
  prediction: 'up' | 'down' | 'same'
  label: string | null
}) {
  submitting.value = true
  predictError.value = null
  try {
    const saved = await api.predictionSubmit({
      base_request: payload.request,
      receptor_lonlat: payload.receptor,
      parameter: payload.parameter,
      variant_value: payload.variantValue,
      prediction: payload.prediction,
      label: payload.label,
    })
    record.value = saved
    history.value = saveLocalRecord(saved)
    receptor.value = payload.receptor
    fieldChoice.value = 'baseline_plume'
  } catch (e: any) {
    // 基准静风/非法输入才会进入这里；题次未生成
    predictError.value =
      e.apiError?.message || e.message || '题目提交失败（基准情景必须可计算）'
  } finally {
    submitting.value = false
  }
}

function onChooseField(f: FieldChoice) {
  fieldChoice.value = f
}

async function onSelectHistory(id: number) {
  loadingDetail.value = true
  predictError.value = null
  try {
    // 先尝试后端详情（含完整网格场）
    const full = await api.predictionGet(id)
    record.value = full
  } catch {
    // 后端已重启/不可用：localStorage 镜像中保存了完整题次
    const local = getLocalRecord(id)
    if (local) record.value = local
    else predictError.value = '该题次在本机与后端均找不到。'
  } finally {
    loadingDetail.value = false
  }
  if (record.value) {
    receptor.value = record.value.input_summary.receptor_lonlat
    fieldChoice.value = 'baseline_plume'
  }
}

function onNewQuestion() {
  record.value = null
  predictError.value = null
  fieldChoice.value = 'baseline_plume'
  receptor.value = null
  setupReceptor.value = null
  pickMode.value = false
  panelKey.value += 1
}

function onPredictionReset() {
  receptor.value = null
  setupReceptor.value = null
  record.value = null
  predictError.value = null
}

const mapResult = computed(() =>
  mode.value === 'explore' ? result.value : predictionMapResult.value,
)
const mapSource = computed<[number, number] | null>(() => {
  if (mode.value === 'explore' && result.value) return result.value.source_lonlat
  if (record.value) return record.value.input_summary.source.lonlat
  if (mode.value === 'predict') {
    return (
      setupSource.value ??
      (sources.value[0] ? [sources.value[0].lon, sources.value[0].lat] : null)
    )
  }
  return null
})

const mapReceptor = computed<[number, number] | null>(() => {
  if (mode.value !== 'predict') return null
  return receptor.value ?? setupReceptor.value
})

const mapFieldMode = computed<'plume' | 'total'>(() =>
  fieldChoice.value.endsWith('_total') ? 'total' : 'plume',
)

const stops = computed(() =>
  mapResult.value ? legendStops(mapResult.value.iso_levels_ug_m3) : [],
)
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <h1>离线高斯烟羽情景演示</h1>
      <span class="sub">平坦地形 · 稳态风 · 显式参数化 · 环境课程教学</span>
      <div class="mode-switch">
        <button :class="{ active: mode === 'explore' }" @click="switchMode('explore')">
          自由探究
        </button>
        <button :class="{ active: mode === 'predict' }" @click="switchMode('predict')">
          课堂预测练习
        </button>
      </div>
      <span class="spacer" />
      <span class="repo">数据后端：{{ repo === 'postgis' ? 'PostgreSQL/PostGIS' : '内存虚构数据（PostGIS 未连接时回退）' }}</span>
    </header>

    <!-- 自由探究：原有控制台 -->
    <ControlPanel
      v-if="mode === 'explore'"
      :sources="sources"
      :meteorology="meteorology"
      v-model:form="form"
      :loading="loading"
      @select-source="onSelectSource"
      @select-met="onSelectMet"
      @run="run"
    />
    <!-- 预测练习：教师配题 + 学生预测 -->
    <PredictionPanel
      v-else
      :key="`pred-panel-${panelKey}`"
      ref="predictionPanel"
      :sources="sources"
      :meteorology="meteorology"
      :loading="submitting"
      @submit="onPredictionSubmit"
      @pick-receptor="onPredictionPick"
      @receptor-change="onSetupReceptorChange"
      @source-change="onSetupSourceChange"
      @reset="onPredictionReset"
    />

    <div class="map-wrap">
      <MapView
        :result="mapResult"
        :show-fill="mode === 'explore' ? showFill : predictShowFill"
        :show-iso="mode === 'explore' ? showIso : predictShowIso"
        :show-bg="mode === 'explore' ? showBg : predictShowBg"
        :receptor="mode === 'predict' ? mapReceptor : null"
        :pick-mode="mode === 'predict' && pickMode"
        :source-lon-lat="mapSource"
        :field-mode="mode === 'predict' ? mapFieldMode : 'plume'"
        @map-click="onMapClick"
      />
      <template v-if="mode === 'explore'">
        <div
          v-if="result && stops.length"
          class="legend"
          style="left:12px;bottom:12px"
        >
          <div>
            <b>烟羽贡献浓度</b>（μg/m³，不含背景）
          </div>
          <div class="bar">
            <span
              v-for="s in stops"
              :key="s.level"
              :style="{ flex: 1, background: s.color }"
            />
          </div>
          <div class="labels">
            <span>{{ stops[0].level }}</span>
            <span>{{ stops[stops.length - 1].level }}</span>
          </div>
          <div class="bgrow">
            <label class="toggle" style="margin:4px 0 2px">
              <input type="checkbox" v-model="showFill" /> 烟羽贡献等值区
            </label>
            <label class="toggle" style="margin:2px 0">
              <input type="checkbox" v-model="showIso" /> 烟羽贡献等值线
            </label>
            <label class="toggle" style="margin:2px 0">
              <input type="checkbox" v-model="showBg" />
              背景值叠加（均匀 {{ result.background_conc_ug_m3 }} μg/m³）
            </label>
            <div class="muted" style="font-size:10px;margin-top:2px">
              总浓度＝烟羽贡献＋背景值，见右侧结果分解与悬停读数
            </div>
          </div>
        </div>
        <div v-if="isCalm" class="notice err" style="position:absolute;top:12px;left:50%;transform:translateX(-50%);z-index:6;max-width:560px">
          {{ error }}
        </div>
      </template>
      <template v-else>
        <div v-if="predictError" class="notice err pickhint">
          {{ predictError }}
        </div>
        <div v-if="record" class="legend" style="left:12px;bottom:12px;max-width:300px">
          <div>
            <b>{{
              fieldChoice.startsWith('baseline') ? '基准' : '变体'
            }}·{{ fieldChoice.endsWith('_total') ? '总量场' : '烟羽场' }}</b>
            （μg/m³）
          </div>
          <div v-if="fieldChoice.endsWith('_total')" class="muted" style="font-size:10px;margin-top:2px">
            总量＝烟羽＋背景（背景层已叠加）；切到“烟羽”场可单独看烟羽贡献。
          </div>
          <div v-else class="muted" style="font-size:10px;margin-top:2px">
            仅烟羽贡献，不含背景；受体浓度与差值见右侧揭晓面板。
          </div>
        </div>
      </template>
      <div class="disclaimer-foot">
        教学模型：不得用于真实事故预警或法规达标判定
      </div>
    </div>

    <!-- 自由探究结果 -->
    <ResultPanel v-if="mode === 'explore'" :result="result" :error="error" />
    <!-- 预测揭晓 + 历史题次 -->
    <PredictionResultPanel
      v-else
      :record="record"
      :history="history"
      :field-choice="fieldChoice"
      :loading-detail="loadingDetail"
      @select-history="onSelectHistory"
      @choose-field="onChooseField"
      @new-question="onNewQuestion"
    />
  </div>
</template>
