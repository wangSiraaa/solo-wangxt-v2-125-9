<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { scenarioFromForm, type FormState } from '../form'
import type {
  DirectionChoice,
  PredictionRecord,
  SourceRow,
  VariableParam,
} from '../types'

const props = defineProps<{
  form: FormState
  sources: SourceRow[]
}>()

const PARAMS: { key: VariableParam; label: string; unit: string }[] = [
  { key: 'stack_height_m', label: '烟囱高度 H', unit: 'm' },
  { key: 'wind_speed_ms', label: '风速 u', unit: 'm/s' },
  { key: 'emission_rate_g_s', label: '排放率 Q', unit: 'g/s' },
]

const DIRECTIONS: { key: DirectionChoice; label: string }[] = [
  { key: 'increase', label: '升高' },
  { key: 'decrease', label: '降低' },
  { key: 'unchanged', label: '基本不变' },
]

// ---- 出题（教师）：固定受体 + 一项可变参数；基准输入 = 左侧面板当前值 ----
const receptorX = ref(1500)
const receptorY = ref(0)
const variableParam = ref<VariableParam>('stack_height_m')
const variantValue = ref(200)
const prediction = ref<DirectionChoice | null>(null)

const current = ref<PredictionRecord | null>(null)
const history = ref<PredictionRecord[]>([])
const expandedId = ref<number | null>(null)
const busy = ref(false)
const error = ref('')

const paramMeta = computed(
  () => PARAMS.find((p) => p.key === variableParam.value)!,
)

const baselineValue = computed(() => {
  switch (variableParam.value) {
    case 'stack_height_m':
      return props.form.stackHeight
    case 'wind_speed_ms':
      return props.form.windSpeed
    case 'emission_rate_g_s':
      return props.form.emission
  }
})

const calmWarning = computed(
  () =>
    variableParam.value === 'wind_speed_ms' &&
    variantValue.value < props.form.calmThreshold,
)

function dirLabel(d: DirectionChoice | null): string {
  return DIRECTIONS.find((x) => x.key === d)?.label ?? '—'
}

function fmt(v: number | null | undefined, d = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  })
}

async function submit() {
  if (!prediction.value) return
  const s = props.sources.find((x) => x.id === props.form.sourceId)
  if (!s) {
    error.value = '未找到排放源记录'
    return
  }
  busy.value = true
  error.value = ''
  try {
    // 提交预测后服务器才返回两次实算结果；此前本面板不显示任何浓度
    current.value = await api.createPrediction({
      ...scenarioFromForm(props.form, s),
      receptor: {
        downwind_m: receptorX.value,
        crosswind_m: receptorY.value,
      },
      variable_param: variableParam.value,
      variant_value: variantValue.value,
      prediction: prediction.value,
    })
    await loadHistory()
    expandedId.value = null
  } catch (e: any) {
    error.value = e.message || '提交失败'
  } finally {
    busy.value = false
  }
}

function newExercise() {
  current.value = null
  prediction.value = null
  error.value = ''
}

async function loadHistory() {
  try {
    history.value = await api.predictions()
  } catch (e: any) {
    error.value = e.message || '历史题次加载失败'
  }
}

function toggle(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

onMounted(loadHistory)
</script>

<template>
  <div>
    <div class="section">
      <h2>① 出题（教师）</h2>
      <div class="muted" style="font-size:11px;margin-bottom:6px">
        基准输入＝左侧控制面板当前值（H={{ form.stackHeight }} m，
        Q={{ form.emission }} g/s，u={{ form.windSpeed }} m/s，
        {{ form.stability }} 类，背景 {{ form.background }} μg/m³{{
          form.useRise ? '，含抬升' : ''
        }}）。
      </div>
      <div class="row2">
        <label class="field">
          <span class="lbl">受体：下风向 x（m）</span>
          <input class="num" type="number" min="1" step="100" v-model.number="receptorX" />
        </label>
        <label class="field">
          <span class="lbl">受体：横风向 y（m）</span>
          <input class="num" type="number" step="50" v-model.number="receptorY" />
        </label>
      </div>
      <label class="field">
        <span class="lbl">可变参数（其余保持基准值）</span>
        <select class="num" v-model="variableParam">
          <option v-for="p in PARAMS" :key="p.key" :value="p.key">
            {{ p.label }}（{{ p.unit }}）
          </option>
        </select>
      </label>
      <label class="field">
        <span class="lbl">
          {{ paramMeta.label }}：{{ baselineValue }} → 新值（{{ paramMeta.unit }}）
        </span>
        <input class="num" type="number" min="0" step="1" v-model.number="variantValue" />
      </label>
      <div v-if="calmWarning" class="notice warn">
        新风速低于静风阈值 {{ form.calmThreshold }} m/s：变体将判定为
        <b>不可计算</b>，系统保留预测记录但不给出浓度。
      </div>
    </div>

    <div class="section" v-if="!current">
      <h2>② 学生预测（提交前不显示任何计算结果）</h2>
      <div class="muted" style="font-size:11px;margin-bottom:6px">
        {{ paramMeta.label }} 由 {{ baselineValue }} 变为 {{ variantValue }}
        {{ paramMeta.unit }} 后，受体（x={{ receptorX }} m, y={{ receptorY }} m）
        的总浓度会：
      </div>
      <div class="pred-radios">
        <label v-for="d in DIRECTIONS" :key="d.key" class="toggle">
          <input type="radio" name="prediction" :value="d.key" v-model="prediction" />
          {{ d.label }}
        </label>
      </div>
      <button data-test="prediction-submit" @click="submit" :disabled="!prediction || busy">
        {{ busy ? '计算中…' : '提交预测并揭示两次实算结果' }}
      </button>
      <div v-if="error" class="notice err" style="margin-top:8px">{{ error }}</div>
    </div>

    <div class="section" v-if="current">
      <h2>
        ③ 本题结果（题次 #{{ current.id }}）
        <span
          v-if="current.computable"
          :class="['badge', current.correct ? 'ok' : 'bad']"
        >
          {{ current.correct ? '预测正确' : '预测不符' }}
        </span>
        <span v-else class="badge bad">不可计算</span>
      </h2>
      <div v-if="!current.computable" class="notice warn">
        {{ current.not_computable_reason }}
        <br />已保留你的预测（{{ dirLabel(current.prediction) }}），
        未生成任何浓度数值。
      </div>
      <table class="meta-tbl">
        <tr>
          <th>受体处（μg/m³）</th>
          <th>烟羽贡献</th>
          <th>背景</th>
          <th>总量</th>
        </tr>
        <tr v-if="current.baseline_result">
          <td>
            基准（{{ current.input_summary.variable_param_label }}={{ current.baseline_value }}）
          </td>
          <td class="mono">{{ fmt(current.baseline_result.concentration.plume_conc_ug_m3) }}</td>
          <td class="mono">{{ fmt(current.baseline_result.concentration.background_conc_ug_m3) }}</td>
          <td class="mono"><b>{{ fmt(current.baseline_result.concentration.total_conc_ug_m3) }}</b></td>
        </tr>
        <tr v-if="current.variant_result">
          <td>
            变体（{{ current.input_summary.variable_param_label }}={{ current.variant_value }}）
          </td>
          <td class="mono">{{ fmt(current.variant_result.concentration.plume_conc_ug_m3) }}</td>
          <td class="mono">{{ fmt(current.variant_result.concentration.background_conc_ug_m3) }}</td>
          <td class="mono"><b>{{ fmt(current.variant_result.concentration.total_conc_ug_m3) }}</b></td>
        </tr>
        <tr v-else>
          <td>变体（{{ current.input_summary.variable_param_label }}={{ current.variant_value }}）</td>
          <td colspan="3" class="muted">不可计算（静风），无浓度输出</td>
        </tr>
        <tr v-if="current.computable">
          <td>差值（变体−基准）</td>
          <td class="mono">{{ fmt(current.delta_plume_ug_m3) }}</td>
          <td class="mono">0.000</td>
          <td class="mono"><b>{{ fmt(current.delta_total_ug_m3) }}</b></td>
        </tr>
      </table>
      <dl class="kv" style="margin-top:8px">
        <template v-if="current.baseline_result">
          <dt>有效源高 基准→变体</dt>
          <dd>
            {{ fmt(current.baseline_result.effective_stack_height_m, 1) }} →
            {{ current.variant_result ? fmt(current.variant_result.effective_stack_height_m, 1) : '—' }} m
          </dd>
        </template>
        <dt>你的预测</dt>
        <dd>{{ dirLabel(current.prediction) }}</dd>
        <dt>实际方向（按受体总量差判定）</dt>
        <dd><b>{{ current.computable ? dirLabel(current.actual_direction) : '不可计算' }}</b></dd>
      </dl>
      <div class="notice info" style="margin-top:6px">{{ current.direction_note }}</div>
      <button class="ghost" @click="newExercise">再出一题</button>
    </div>

    <div class="section">
      <h2>
        历史题次
        <span class="badge ok">{{ history.length }}</span>
        <button class="ghost" style="float:right;padding:1px 8px" @click="loadHistory">
          刷新
        </button>
      </h2>
      <div v-if="!history.length" class="muted" style="font-size:11px">
        暂无记录。提交一次预测后在此复看。
      </div>
      <div
        v-for="r in history"
        :key="r.id"
        :class="['check-item', { fail: r.computable && r.correct === false }]"
      >
        <div class="t" style="cursor:pointer" @click="toggle(r.id)">
          <span v-if="!r.computable">🚫</span>
          <span v-else-if="r.correct">✅</span>
          <span v-else>❌</span>
          #{{ r.id }} {{ r.input_summary.variable_param_label }}
          {{ r.baseline_value }}→{{ r.variant_value }}
          {{ r.input_summary.variable_param_unit }}
          <span class="muted" style="font-weight:400">
            （{{ r.created_at.replace('T', ' ').slice(5, 19) }}）
          </span>
        </div>
        <div class="d">
          受体 x={{ r.receptor.downwind_m }} m, y={{ r.receptor.crosswind_m }} m；
          预测 {{ dirLabel(r.prediction) }} → 实际
          {{ r.computable ? dirLabel(r.actual_direction) : '不可计算' }}
        </div>
        <template v-if="expandedId === r.id">
          <div class="d">
            基准输入：{{ r.input_summary.source_name }}（{{ r.input_summary.pollutant }}），
            H={{ r.input_summary.stack_height_m }} m，
            Q={{ r.input_summary.emission_rate_g_s }} g/s，
            u={{ r.input_summary.wind_speed_ms }} m/s，
            风向 {{ r.input_summary.wind_from_deg }}°，
            {{ r.input_summary.stability_class }} 类，
            背景 {{ r.input_summary.background_conc_ug_m3 }} μg/m³，
            {{ r.input_summary.use_plume_rise ? '含抬升' : '不含抬升' }}，
            {{ r.input_summary.parameterization }}
          </div>
          <table v-if="r.computable" class="meta-tbl" style="margin-top:4px">
            <tr>
              <th>受体处（μg/m³）</th><th>烟羽贡献</th><th>背景</th><th>总量</th>
            </tr>
            <tr>
              <td>基准</td>
              <td class="mono">{{ fmt(r.baseline_result!.concentration.plume_conc_ug_m3) }}</td>
              <td class="mono">{{ fmt(r.baseline_result!.concentration.background_conc_ug_m3) }}</td>
              <td class="mono">{{ fmt(r.baseline_result!.concentration.total_conc_ug_m3) }}</td>
            </tr>
            <tr>
              <td>变体</td>
              <td class="mono">{{ fmt(r.variant_result!.concentration.plume_conc_ug_m3) }}</td>
              <td class="mono">{{ fmt(r.variant_result!.concentration.background_conc_ug_m3) }}</td>
              <td class="mono">{{ fmt(r.variant_result!.concentration.total_conc_ug_m3) }}</td>
            </tr>
            <tr>
              <td>差值</td>
              <td class="mono">{{ fmt(r.delta_plume_ug_m3) }}</td>
              <td class="mono">0.000</td>
              <td class="mono">{{ fmt(r.delta_total_ug_m3) }}</td>
            </tr>
          </table>
          <div v-else class="notice warn" style="margin-top:4px">
            {{ r.not_computable_reason }}（保留原预测，未生成浓度）
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
