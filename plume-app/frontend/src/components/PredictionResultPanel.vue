<script setup lang="ts">
import { computed } from 'vue'
import type {
  PredictionDirection,
  PredictionRecord,
} from '../types'
import {
  DIRECTION_LABELS,
  PARAMETER_LABELS,
  PARAMETER_UNITS,
} from '../prediction'

export type FieldChoice =
  | 'baseline_plume'
  | 'baseline_total'
  | 'variant_plume'
  | 'variant_total'

const props = defineProps<{
  record: PredictionRecord | null
  history: PredictionRecord[]
  fieldChoice: FieldChoice
  loadingDetail: boolean
}>()

const emit = defineEmits<{
  (e: 'select-history', id: number): void
  (e: 'choose-field', f: FieldChoice): void
  (e: 'new-question'): void
}>()

const cmp = computed(() => props.record?.comparison ?? null)
const variantComputable = computed(
  () => props.record?.variant.computable ?? false,
)

function fmt(v: number | null | undefined, d = 2) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  })
}

function shortTime(iso: string) {
  return iso.replace('T', ' ').replace('+00:00', ' UTC')
}

function verdictClass(r: PredictionRecord): 'ok' | 'bad' | 'muted' {
  if (r.comparison.prediction_correct === true) return 'ok'
  if (r.comparison.prediction_correct === false) return 'bad'
  return 'muted'
}

function dirText(d: PredictionDirection | null | undefined) {
  return d ? DIRECTION_LABELS[d] : '—'
}
</script>

<template>
  <div class="panel right">
    <div class="tabs">
      <button :class="{ active: true }">揭晓与判定</button>
      <button @click="emit('new-question')">新题次</button>
    </div>

    <template v-if="!record">
      <div class="section">
        <h2>课堂预测练习</h2>
        <p class="muted" style="font-size:12px;line-height:1.7">
          教师在左侧固定受体与基准输入、选择一项可变参数；
          学生提交方向预测后，这里才会展示两次实际计算的
          <b>烟羽 / 背景 / 总量</b>受体浓度与差值。
        </p>
        <p class="muted" style="font-size:12px;line-height:1.7">
          方向一律以受体处两次实际计算结果比较得出，
          不内置“风速越大处处降低”“烟囱越高越低”等口诀；
          静风变体显示不可计算并保留原预测，不生成虚假浓度。
        </p>
      </div>
    </template>

    <template v-else>
      <!-- 判定横幅 -->
      <div class="section">
        <h2>题次 #{{ record.sequence }}<span class="muted" style="font-size:10px;margin-left:6px">{{ shortTime(record.created_at) }}</span></h2>
        <div v-if="variantComputable && cmp" class="notice" :class="cmp.prediction_correct ? 'okbox' : 'err'">
          <template v-if="cmp.prediction_correct">
            ✅ 预测正确：你预测「{{ dirText(cmp.prediction) }}」，受体实际「{{ dirText(cmp.actual_direction) }}」。
          </template>
          <template v-else>
            ❌ 预测不符：你预测「{{ dirText(cmp.prediction) }}」，受体实际「{{ dirText(cmp.actual_direction) }}」。
          </template>
          <div class="muted" style="margin-top:4px;font-size:11px;color:inherit">
            判定依据：{{ cmp.judged_on }}
          </div>
        </div>
        <div v-else-if="!variantComputable && cmp" class="notice warn">
          🌫️ 变体静风（u={{ record.variant.computable ? '' : record.variant.wind_speed_ms }}
          &lt; {{ record.variant.computable ? '' : record.variant.calm_threshold_ms }} m/s）：
          定常高斯烟羽模型<b>不可计算</b>，未执行除法、未生成任何浓度。
          原预测「{{ dirText(cmp.prediction) }}」已保留，不判对错。
        </div>
      </div>

      <!-- 受体浓度对比：烟羽/背景/总量 + 差值 -->
      <div class="section">
        <h2>固定受体处浓度（μg/m³）</h2>
        <table v-if="cmp" class="meta-tbl cmp-tbl">
          <tr>
            <th></th>
            <th>基准</th>
            <th>变体</th>
            <th>差值（变−基）</th>
          </tr>
          <tr>
            <td>烟羽贡献</td>
            <td class="mono">{{ fmt(record.baseline.receptor.plume_conc_ug_m3) }}</td>
            <td class="mono">
              {{ variantComputable ? fmt(record.variant.computable ? record.variant.receptor.plume_conc_ug_m3 : null) : '不可计算' }}
            </td>
            <td class="mono" :class="variantComputable && cmp.delta && cmp.delta.plume_conc_ug_m3 > 0 ? 'up' : variantComputable && cmp.delta && cmp.delta.plume_conc_ug_m3 < 0 ? 'down' : ''">
              {{ variantComputable && cmp.delta ? fmt(cmp.delta.plume_conc_ug_m3) : '—' }}
            </td>
          </tr>
          <tr>
            <td>背景浓度</td>
            <td class="mono">{{ fmt(record.baseline.receptor.background_conc_ug_m3) }}</td>
            <td class="mono">
              {{ variantComputable && record.variant.computable ? fmt(record.variant.receptor.background_conc_ug_m3) : '不可计算' }}
            </td>
            <td class="mono">
              {{ variantComputable && cmp.delta ? fmt(cmp.delta.background_conc_ug_m3) : '—' }}
            </td>
          </tr>
          <tr>
            <td><b>总量</b></td>
            <td class="mono"><b>{{ fmt(record.baseline.receptor.total_conc_ug_m3) }}</b></td>
            <td class="mono">
              <b>{{ variantComputable && record.variant.computable ? fmt(record.variant.receptor.total_conc_ug_m3) : '不可计算' }}</b>
            </td>
            <td class="mono" :class="cmp.delta && cmp.delta.total_conc_ug_m3 > 0 ? 'up' : cmp.delta && cmp.delta.total_conc_ug_m3 < 0 ? 'down' : ''">
              <b>{{ variantComputable && cmp.delta ? fmt(cmp.delta.total_conc_ug_m3) : '—' }}</b>
            </td>
          </tr>
        </table>
        <dl class="kv" style="margin-top:6px">
          <dt>受体烟羽坐标 (x, y)</dt>
          <dd>
            {{ fmt(record.baseline.receptor.downwind_crosswind_m[0], 0) }},
            {{ fmt(record.baseline.receptor.downwind_crosswind_m[1], 0) }} m
          </dd>
        </dl>
        <div v-if="variantComputable && cmp" class="muted" style="font-size:11px;margin-top:4px">
          烟羽方向：{{ dirText(cmp.actual_plume_direction) }}；
          背景为空间常数且本题未改变，故背景差值为 0，总量方向与烟羽一致。
        </div>
      </div>

      <!-- 地图场切换 -->
      <div class="section">
        <h2>地图场显示（两次实际计算）</h2>
        <div class="field-grid">
          <button class="ghost" :class="{ active: fieldChoice === 'baseline_plume' }"
            @click="emit('choose-field', 'baseline_plume')">基准·烟羽</button>
          <button class="ghost" :class="{ active: fieldChoice === 'baseline_total' }"
            @click="emit('choose-field', 'baseline_total')">基准·总量</button>
          <button class="ghost" :disabled="!variantComputable"
            :class="{ active: fieldChoice === 'variant_plume' }"
            @click="emit('choose-field', 'variant_plume')">变体·烟羽</button>
          <button class="ghost" :disabled="!variantComputable"
            :class="{ active: fieldChoice === 'variant_total' }"
            @click="emit('choose-field', 'variant_total')">变体·总量</button>
        </div>
        <div class="muted" style="font-size:11px;margin-top:4px">
          变体静风时无可展示浓度场，按钮停用，地图保留基准场与受体标记。
        </div>
      </div>

      <!-- 输入摘要 -->
      <div class="section">
        <h2>输入摘要</h2>
        <dl class="kv">
          <dt>可变参数</dt>
          <dd>
            {{ PARAMETER_LABELS[record.input_summary.variable.parameter] }}
            {{ record.input_summary.variable.baseline_value }}
            → {{ record.input_summary.variable.variant_value }}
            {{ PARAMETER_UNITS[record.input_summary.variable.parameter] }}
          </dd>
          <dt>烟囱高 / Q / u</dt>
          <dd>
            {{ record.input_summary.source.stack_height_m }} m ·
            {{ record.input_summary.source.emission_rate_g_s }} g/s ·
            {{ record.input_summary.meteorology.wind_speed_ms }} m/s
          </dd>
          <dt>风向 / 稳定度</dt>
          <dd>
            {{ record.input_summary.meteorology.wind_from_deg }}° /
            {{ record.input_summary.meteorology.stability_class }}
          </dd>
          <dt>Holland 抬升 / 参数化</dt>
          <dd>
            {{ record.input_summary.plume_rise_enabled ? '开启' : '关闭' }} ·
            {{ record.input_summary.parameterization === 'power_law' ? '幂律' : 'Briggs 乡村' }}
          </dd>
          <dt>有效源高（基准→变体）</dt>
          <dd>
            {{ fmt(record.baseline.effective_stack_height_m, 1) }} →
            {{ variantComputable && record.variant.computable ? fmt(record.variant.effective_stack_height_m, 1) : '不可计算' }} m
          </dd>
          <dt>受体经纬度</dt>
          <dd>
            {{ record.input_summary.receptor_lonlat[0].toFixed(4) }},
            {{ record.input_summary.receptor_lonlat[1].toFixed(4) }}
          </dd>
        </dl>
        <div v-if="record.label" class="notice info" style="margin-top:6px">
          备注：{{ record.label }}
        </div>
      </div>
    </template>

    <!-- 历史题次 -->
    <div class="section">
      <h2>历史题次（{{ history.length }}）</h2>
      <div v-if="loadingDetail" class="muted" style="font-size:11px">载入中…</div>
      <div v-if="!history.length" class="muted" style="font-size:11px">
        还没有题次。本机历史同时存于浏览器 localStorage，离线可复看。
      </div>
      <div
        v-for="h in history"
        :key="h.id"
        class="hist-item"
        :class="{ active: record && h.id === record.id }"
        @click="emit('select-history', h.id)"
      >
        <div class="hist-top">
          <span class="hist-id">#{{ h.sequence }}</span>
          <span class="muted" style="font-size:10px">{{ shortTime(h.created_at) }}</span>
          <span
            class="badge"
            :class="verdictClass(h) === 'ok' ? 'ok' : verdictClass(h) === 'bad' ? 'bad' : ''"
          >
            <template v-if="h.comparison.prediction_correct === true">✓ 正确</template>
            <template v-else-if="h.comparison.prediction_correct === false">✗ 不符</template>
            <template v-else>静风</template>
          </span>
        </div>
        <div class="hist-d">
          {{ PARAMETER_LABELS[h.input_summary.variable.parameter] }}
          {{ h.input_summary.variable.baseline_value }}
          → {{ h.input_summary.variable.variant_value }}
          {{ PARAMETER_UNITS[h.input_summary.variable.parameter] }}
        </div>
        <div class="hist-d muted">
          预测 {{ dirText(h.prediction) }} ·
          实际 {{ h.variant.computable ? dirText(h.comparison.actual_direction) : '不可计算' }}
        </div>
      </div>
    </div>
  </div>
</template>
