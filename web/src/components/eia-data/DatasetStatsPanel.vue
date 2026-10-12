<template>
  <div class="stats-panel">
    <a-skeleton v-if="loading" active :paragraph="{ rows: 10 }" />

    <div v-else-if="error" class="error-state">
      <a-empty :description="error">
        <a-button type="primary" @click="fetchStats">重试</a-button>
      </a-empty>
    </div>

    <template v-else>
      <!-- 指标带：6 位核心计数 -->
      <div class="metric-strip">
        <div
          v-for="m in metricStrip"
          :key="m.label"
          class="metric-cell"
          :class="{ warn: m.warn, link: m.link }"
          :role="m.link ? 'button' : undefined"
          :tabindex="m.link ? 0 : undefined"
          :aria-label="m.link ? `${m.label} ${m.value}，进入词表管理` : undefined"
          @click="m.link && goLexicon()"
          @keyup.enter="m.link && goLexicon()"
        >
          <span class="metric-label">{{ m.label }}</span>
          <span class="metric-value">{{ m.value.toLocaleString() }}<small>{{ m.unit }}</small></span>
        </div>
      </div>

      <div class="stats-grid">
        <!-- 语料规模分布 -->
        <section class="panel-card span-7">
          <h3 class="card-title">语料规模分布</h3>
          <p class="card-sub">按报告阶段 · 案例语料库切片数与语料报告数</p>
          <div ref="corpusChartRef" class="chart chart-md"></div>
        </section>

        <!-- 省份分布 -->
        <section class="panel-card span-5">
          <h3 class="card-title">语料省份分布</h3>
          <p class="card-sub">{{ stats.corpus.reports_total }} 份语料报告的来源省份</p>
          <div ref="provinceChartRef" class="chart chart-md"></div>
        </section>

        <!-- 数据分层构成（五层价值模型） -->
        <section class="panel-card span-12">
          <h3 class="card-title">数据分层构成</h3>
          <p class="card-sub">
            五层价值模型 ·
            {{ totalLayerItems }} 个数据集块，悬停查看文件真源；
            <span class="legend-swatch swatch-main"></span>内置兜底
            <span class="legend-swatch swatch-planned"></span>本期预留
          </p>
          <div class="layer-rows">
            <div v-for="layer in stats.layers" :key="layer.layer" class="layer-row">
              <span class="layer-name">{{ layer.layer }}</span>
              <div class="layer-chips">
                <span
                  v-for="item in layer.items"
                  :key="item.key"
                  class="layer-chip"
                  :class="{ planned: item.status === 'planned', link: layerLink(item) }"
                  :title="item.file || (item.status === 'planned' ? '本期预留位' : '')"
                  :role="layerLink(item) ? 'button' : undefined"
                  :tabindex="layerLink(item) ? 0 : undefined"
                  :aria-label="layerLink(item) ? `${item.name}，进入管理页` : undefined"
                  @click="layerLink(item) && goLayer(item)"
                  @keyup.enter="layerLink(item) && goLayer(item)"
                >
                  <em>{{ item.name }}</em>
                  <b v-if="item.count !== undefined && item.count !== null">{{ formatCount(item.count) }}<i>{{ item.unit }}</i></b>
                  <b v-else-if="item.status === 'planned'" class="planned-tag">预留</b>
                </span>
              </div>
            </div>
          </div>
        </section>

        <!-- 护栏词表候选 -->
        <section class="panel-card span-7">
          <h3 class="card-title">数值护栏词表候选</h3>
          <p class="card-sub">
            比率/浓度型口径三分类 ·
            <span class="legend-swatch swatch-main"></span>A 措施效率 {{ stats.candidates.measure }}
            <span class="legend-swatch swatch-mid"></span>B 现状监测 {{ stats.candidates.site }}
            <span class="legend-swatch swatch-gray"></span>C 非护栏杂项 {{ stats.candidates.junk }}
            · 可发布区间 <b class="hl">{{ stats.candidates.range_ready }}</b> 项
            <a class="panel-link" @click.prevent="goLexicon">进入词表管理 →</a>
          </p>
          <div ref="candidatesChartRef" class="chart chart-md"></div>
        </section>

        <!-- 事实槽位覆盖 -->
        <section class="panel-card span-5">
          <h3 class="card-title">章节事实槽位覆盖</h3>
          <p class="card-sub">
            按发布档位堆叠 ·
            <template v-for="(t, i) in tierLegend" :key="t.key">
              <span v-if="i" class="legend-dot">·</span>
              {{ t.label }} {{ t.count }}
            </template>
          </p>
          <div ref="expectChartRef" class="chart chart-md"></div>
        </section>

        <!-- 数据质量体检 -->
        <section class="panel-card span-12">
          <h3 class="card-title">数据质量体检</h3>
          <p class="card-sub">客观可算项即时统计 · 启发式项已标注，修复入口在语料清洗批次</p>
          <div class="quality-grid">
            <div
              v-for="q in stats.quality"
              :key="q.key"
              class="quality-item"
              :class="{ 'is-link': q.key === 'unmapped_pool' }"
              :role="q.key === 'unmapped_pool' ? 'button' : undefined"
              :tabindex="q.key === 'unmapped_pool' ? 0 : undefined"
              :aria-label="
                q.key === 'unmapped_pool' ? `未归并量词 ${q.count} 条，查看明细` : undefined
              "
              @click="q.key === 'unmapped_pool' && openUnmapped()"
              @keyup.enter="q.key === 'unmapped_pool' && openUnmapped()"
            >
              <span class="quality-dot" :class="q.level"></span>
              <span class="quality-label">{{ q.label }}</span>
              <span class="quality-count">{{ q.count.toLocaleString() }}<small v-if="q.total !== undefined"> / {{ q.total }}</small></span>
              <span class="quality-hint" :title="q.hint">{{ q.hint }}</span>
            </div>
          </div>
        </section>
      </div>

      <p class="generated-note">统计生成于 {{ generatedAtText }} · 数据源为技能内置语料（兜底真源），页面只读</p>
    </template>

    <!-- unmapped 池明细抽屉（只读 · 词表口径 label 扩充素材） -->
    <a-drawer v-model:open="unmappedDrawer.open" title="未归并量词（unmapped 池）" width="640">
      <template #extra>
        <a-button size="small" :disabled="!unmappedDrawer.data" @click="exportUnmappedCsv"
          >导出 CSV</a-button
        >
      </template>
      <p class="drawer-sub">
        label 未命中 forms_label_map 的量词短语（5 阶段共 {{ unmappedDrawer.total }} 条）·
        只读审阅：治理动作为扩充技能词形映射后重建，不在此编辑；planning 阶段存在 200 条截断上限
      </p>
      <a-spin v-if="unmappedDrawer.loading" />
      <a-tabs
        v-else-if="unmappedDrawer.data"
        v-model:activeKey="unmappedDrawer.activeStage"
        size="small"
      >
        <a-tab-pane
          v-for="(v, stage) in unmappedDrawer.data.stages"
          :key="stage"
          :tab="`${STAGE_LABELS[stage] || stage} (${v.total})`"
        >
          <a-table
            :data-source="v.items"
            :columns="unmappedColumns"
            :pagination="{ pageSize: 20, size: 'small', showSizeChanger: false }"
            row-key="__idx"
            size="small"
          />
        </a-tab-pane>
      </a-tabs>
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import * as echarts from '@/utils/dashboardCharts'
import { eiaDataApi } from '@/apis/eia_data_api'

const router = useRouter()

const STAGE_LABELS = {
  planning_eia: '规划环评',
  post_eia: '事后环评',
  project_eia_openpit: '项目环评·露天',
  project_eia_underground: '项目环评·井工',
  tracking_eia: '跟踪评价'
}

const loading = ref(true)
const error = ref('')
const stats = ref(null)

const corpusChartRef = ref(null)
const provinceChartRef = ref(null)
const candidatesChartRef = ref(null)
const expectChartRef = ref(null)
let charts = []
let resizeObserver = null

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

const metricStrip = computed(() => {
  const s = stats.value
  const sections = Object.values(s.expectations).reduce((acc, e) => acc + e.sections, 0)
  const stdTotal = s.layers
    .flatMap((l) => l.items)
    .find((i) => i.key === 'standards_index')
  return [
    { label: '案例语料切片', value: s.corpus.slices_total, unit: '片' },
    { label: '语料报告', value: s.corpus.reports_total, unit: '份' },
    { label: '章节事实槽位', value: sections, unit: '节' },
    { label: '护栏词表候选', value: s.candidates.total, unit: '项', link: true },
    { label: '标准与限值', value: stdTotal?.count ?? 0, unit: '条' },
    { label: '标准待人工核实', value: warnCount('standards_verify'), unit: '条', warn: true }
  ]
})

const warnCount = (key) => stats.value.quality.find((q) => q.key === key)?.count ?? 0

const goLexicon = () => router.push('/domain-factory/eia-data/lexicon')

// 可管理数据层的 chip 点击直达对应管理页（人工标注带待办深链，两 chip 落点各有语义）
const LAYER_LINKS = {
  corpus_meta: '/domain-factory/eia-data/meta',
  meta_annotations: '/domain-factory/eia-data/meta?state=todo',
  curated_lexicon: '/domain-factory/eia-data/lexicon',
  standards_index: '/domain-factory/eia-data/standards',
  section_expectations: '/domain-factory/eia-data/sections',
  data_expectations: '/domain-factory/eia-data/expectations'
}
const layerLink = (item) => LAYER_LINKS[item.key]
const goLayer = (item) => router.push(LAYER_LINKS[item.key])

const totalLayerItems = computed(() => stats.value.layers.reduce((acc, l) => acc + l.items.length, 0))

const tierLegend = computed(() => {
  const totals = {}
  const order = []
  Object.values(stats.value.expectations).forEach((e) => {
    Object.entries(e.tiers).forEach(([k, v]) => {
      if (!(k in totals)) order.push(k)
      totals[k] = (totals[k] || 0) + v
    })
  })
  const LABELS = { required: '必备', optional: '可选', contextual: '情境' }
  return order.map((k) => ({ key: k, label: LABELS[k] || k, count: totals[k] }))
})

const generatedAtText = computed(() => {
  const d = new Date(stats.value.generated_at)
  return isNaN(d.getTime()) ? stats.value.generated_at : d.toLocaleString('zh-CN', { hour12: false })
})

const formatCount = (n) => (typeof n === 'number' ? n.toLocaleString() : n)

const baseAxis = () => ({
  axisLine: { lineStyle: { color: cssVar('--gray-200') } },
  axisTick: { show: false },
  axisLabel: { color: cssVar('--gray-600'), fontSize: 11 },
  splitLine: { lineStyle: { color: cssVar('--gray-100'), type: 'dashed' } }
})

const renderChart = (el, option) => {
  const chart = echarts.init(el)
  chart.setOption(option)
  charts.push(chart)
  return chart
}

const renderCorpusChart = () => {
  const stages = [...stats.value.stages].reverse()
  renderChart(corpusChartRef.value, {
    grid: { top: 8, left: 8, right: 40, bottom: 0, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', ...baseAxis() },
    yAxis: {
      type: 'category',
      data: stages.map((s) => STAGE_LABELS[s] || s),
      splitLine: { show: false },
      axisLine: { lineStyle: { color: cssVar('--gray-200') } },
      axisTick: { show: false },
      axisLabel: { color: cssVar('--gray-700'), fontSize: 12 }
    },
    series: [
      {
        type: 'bar',
        data: stages.map((s) => stats.value.corpus.per_stage[s]?.slices ?? 0),
        barWidth: 14,
        itemStyle: { color: cssVar('--main-600'), borderRadius: [0, 3, 3, 0] },
        label: {
          show: true,
          position: 'right',
          color: cssVar('--gray-600'),
          fontSize: 11,
          formatter: (p) => {
            const reports = stats.value.corpus.per_stage[stages[p.dataIndex]]?.reports
            return `${p.value} 片 / ${reports ?? 0} 份`
          }
        }
      }
    ]
  })
}

const renderProvinceChart = () => {
  const entries = Object.entries(stats.value.corpus.by_province).sort((a, b) => b[1] - a[1])
  renderChart(provinceChartRef.value, {
    grid: { top: 8, left: 8, right: 32, bottom: 0, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', ...baseAxis(), splitNumber: 3 },
    yAxis: {
      type: 'category',
      data: entries.map(([p]) => p).reverse(),
      splitLine: { show: false },
      axisLine: { lineStyle: { color: cssVar('--gray-200') } },
      axisTick: { show: false },
      axisLabel: { color: cssVar('--gray-700'), fontSize: 12 }
    },
    series: [
      {
        type: 'bar',
        data: entries.map(([, v]) => v).reverse(),
        barWidth: 12,
        itemStyle: { color: cssVar('--main-400'), borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', color: cssVar('--gray-600'), fontSize: 11 }
      }
    ]
  })
}

const renderCandidatesChart = () => {
  const stages = stats.value.stages
  const SERIES = [
    { key: 'measure', label: 'A 措施效率', color: '--main-600' },
    { key: 'site', label: 'B 现状监测', color: '--main-300' },
    { key: 'junk', label: 'C 非护栏杂项', color: '--gray-200' }
  ]
  renderChart(candidatesChartRef.value, {
    grid: { top: 28, left: 8, right: 8, bottom: 0, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, left: 'right', itemWidth: 10, itemHeight: 10, textStyle: { color: cssVar('--gray-600'), fontSize: 11 } },
    xAxis: { type: 'category', data: stages.map((s) => STAGE_LABELS[s] || s), ...baseAxis(), splitLine: { show: false } },
    yAxis: { type: 'value', ...baseAxis(), splitNumber: 3 },
    series: SERIES.map((ser) => ({
      name: ser.label,
      type: 'bar',
      stack: 'candidates',
      barWidth: 26,
      data: stages.map((s) => stats.value.candidates.per_stage[s]?.[ser.key] ?? 0),
      itemStyle: { color: cssVar(ser.color) }
    }))
  })
}

const renderExpectChart = () => {
  const stages = stats.value.stages
  const tierKeys = tierLegend.value.map((t) => t.key)
  const shades = { required: '--main-600', optional: '--main-400', contextual: '--main-200' }
  const fallbackShades = ['--main-500', '--main-300', '--gray-300']
  renderChart(expectChartRef.value, {
    grid: { top: 28, left: 8, right: 8, bottom: 0, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, left: 'right', itemWidth: 10, itemHeight: 10, textStyle: { color: cssVar('--gray-600'), fontSize: 11 } },
    xAxis: { type: 'category', data: stages.map((s) => STAGE_LABELS[s] || s), ...baseAxis(), splitLine: { show: false } },
    yAxis: { type: 'value', ...baseAxis(), splitNumber: 3 },
    series: tierKeys.map((k, i) => ({
      name: tierLegend.value[i].label,
      type: 'bar',
      stack: 'tiers',
      barWidth: 22,
      data: stages.map((s) => stats.value.expectations[s]?.tiers?.[k] ?? 0),
      itemStyle: { color: cssVar(shades[k] || fallbackShades[i % fallbackShades.length]) }
    }))
  })
}

const disposeCharts = () => {
  charts.forEach((c) => c?.dispose())
  charts = []
}

// unmapped 池明细抽屉（只读；条目无唯一键，装载时打 __idx 供 row-key）
const unmappedDrawer = reactive({
  open: false,
  loading: false,
  data: null,
  total: 0,
  activeStage: ''
})
const unmappedColumns = [
  { title: '口径短语', dataIndex: 'caliber', key: 'caliber', ellipsis: true },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
  { title: '节', dataIndex: 'section', key: 'section', width: 80 },
  { title: '首见样例', dataIndex: 'sample', key: 'sample', width: 90 },
  { title: '示例值', dataIndex: 'value', key: 'value', width: 100 }
]

const openUnmapped = async () => {
  unmappedDrawer.open = true
  if (unmappedDrawer.data) return
  unmappedDrawer.loading = true
  try {
    const data = await eiaDataApi.getUnmapped()
    Object.values(data.stages).forEach((v) => {
      v.items = v.items.map((it, i) => ({ ...it, __idx: i }))
    })
    unmappedDrawer.data = data
    unmappedDrawer.total = data.total
    unmappedDrawer.activeStage = Object.keys(data.stages)[0] || ''
  } catch (e) {
    message.error(e?.message || '获取 unmapped 明细失败')
    unmappedDrawer.open = false
  } finally {
    unmappedDrawer.loading = false
  }
}

const exportUnmappedCsv = () => {
  const rows = [['stage', 'caliber', 'unit', 'section', 'sample', 'value']]
  Object.entries(unmappedDrawer.data?.stages || {}).forEach(([stage, v]) => {
    v.items.forEach((it) =>
      rows.push([stage, it.caliber, it.unit, it.section, it.sample, it.value])
    )
  })
  const esc = (c) => {
    const s = c === undefined || c === null ? '' : String(c)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = '﻿' + rows.map((r) => r.map(esc).join(',')).join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `unmapped_pool_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

const fetchStats = async () => {
  loading.value = true
  error.value = ''
  disposeCharts()
  try {
    stats.value = await eiaDataApi.getSkillStats()
    // 先撤 loading 让 v-else 图表容器挂载（ref 就绪），再初始化 echarts
    loading.value = false
    await nextTick()
    renderCorpusChart()
    renderProvinceChart()
    renderCandidatesChart()
    renderExpectChart()
    charts.forEach((c) => resizeObserver?.observe(c.getDom()))
  } catch (e) {
    error.value = e?.message || '统计接口不可用'
    loading.value = false
  }
}

onMounted(() => {
  resizeObserver = new ResizeObserver(() => charts.forEach((c) => c?.resize()))
  fetchStats()
})

const cleanup = () => {
  resizeObserver?.disconnect()
  disposeCharts()
}

onBeforeUnmount(cleanup)
</script>

<style lang="less" scoped>
.stats-panel {
  --hairline: var(--gray-200);
}

.error-state {
  padding: 60px 0;
}

/* ── 指标带 ─────────────────────────────────────────── */
.metric-strip {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  background: var(--main-0);
  border: 1px solid var(--hairline);
  border-radius: 6px;
  margin-bottom: 12px;
}

.metric-cell {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;

  & + & {
    border-left: 1px solid var(--hairline);
  }

  .metric-label {
    font-size: 12px;
    color: var(--gray-500);
  }

  .metric-value {
    font-size: 22px;
    font-weight: 700;
    color: var(--gray-800);
    font-variant-numeric: tabular-nums;
    line-height: 1.1;

    small {
      margin-left: 4px;
      font-size: 12px;
      font-weight: 400;
      color: var(--gray-500);
    }
  }

  &.warn .metric-value {
    color: var(--second-600);
  }

  &.link {
    cursor: pointer;
    transition: background 0.2s;

    &:hover {
      background: var(--gray-50);

      .metric-value {
        color: var(--main-600);
      }
    }

    &:focus-visible {
      outline: 2px solid var(--main-600);
      outline-offset: -2px;
    }
  }
}

/* ── 网格与卡片 ─────────────────────────────────────── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 12px;
}

.span-5 {
  grid-column: span 5;
}

.span-7 {
  grid-column: span 7;
}

.span-12 {
  grid-column: span 12;
}

.panel-card {
  background: var(--main-0);
  border: 1px solid var(--hairline);
  border-radius: 6px;
  padding: 16px 18px;
  min-width: 0;
}

.card-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--gray-800);
}

.card-sub {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--gray-500);

  .hl {
    color: var(--main-600);
    font-variant-numeric: tabular-nums;
  }

  .panel-link {
    margin-left: 10px;
    color: var(--main-600);
    white-space: nowrap;

    &:hover {
      text-decoration: underline;
    }
  }
}

.chart {
  width: 100%;
}

.chart-md {
  height: 200px;
}

/* ── 图例点 ─────────────────────────────────────────── */
.legend-swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin: 0 4px 0 10px;
  vertical-align: baseline;
}

.swatch-main {
  background: var(--main-600);
}

.swatch-mid {
  background: var(--main-300);
}

.swatch-gray {
  background: var(--gray-200);
}

.swatch-planned {
  background: none;
  border: 1px dashed var(--gray-400);
}

.legend-dot {
  margin: 0 2px;
  color: var(--gray-400);
}

/* ── 数据分层构成 ───────────────────────────────────── */
.layer-rows {
  display: flex;
  flex-direction: column;
}

.layer-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;

  & + & {
    border-top: 1px solid var(--gray-100);
  }
}

.layer-name {
  flex: 0 0 76px;
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-700);
  line-height: 26px;
}

.layer-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.layer-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--hairline);
  border-radius: 4px;
  background: var(--gray-50);
  cursor: default;

  &.link {
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;

    &:hover,
    &:focus-visible {
      border-color: var(--main-600);
      background: var(--main-0);

      em {
        color: var(--main-600);
      }
    }
  }

  em {
    font-style: normal;
    font-size: 12px;
    color: var(--gray-700);
  }

  b {
    font-size: 13px;
    font-weight: 700;
    color: var(--main-600);
    font-variant-numeric: tabular-nums;

    i {
      margin-left: 2px;
      font-style: normal;
      font-size: 11px;
      font-weight: 400;
      color: var(--gray-500);
    }
  }

  .planned-tag {
    color: var(--gray-400);
    font-weight: 400;
    font-size: 11px;
  }

  &.planned {
    border-style: dashed;
    background: transparent;

    em {
      color: var(--gray-400);
    }
  }
}

/* ── 数据质量体检 ───────────────────────────────────── */
.quality-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 32px;
}

.quality-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 9px 0;
  border-bottom: 1px solid var(--gray-100);
  min-width: 0;

  &.is-link {
    cursor: pointer;
    transition: background 0.2s;

    &:hover,
    &:focus-visible {
      background: var(--main-0);

      .quality-count {
        color: var(--main-600);
      }
    }
  }
}

.drawer-sub {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--gray-600);
  line-height: 1.6;
}

.quality-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  align-self: center;

  &.warn {
    background: var(--second-600);
  }

  &.info {
    background: var(--gray-400);
  }
}

.quality-label {
  flex: none;
  font-size: 13px;
  color: var(--gray-700);
}

.quality-count {
  font-size: 15px;
  font-weight: 700;
  color: var(--gray-800);
  font-variant-numeric: tabular-nums;

  small {
    font-size: 12px;
    font-weight: 400;
    color: var(--gray-500);
  }
}

.quality-hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--gray-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: help;
}

.generated-note {
  margin: 10px 2px 0;
  font-size: 12px;
  color: var(--gray-400);
}

/* ── 响应式 ─────────────────────────────────────────── */
@media (max-width: 1200px) {
  .span-5,
  .span-7 {
    grid-column: span 12;
  }

  .metric-strip {
    grid-template-columns: repeat(3, 1fr);
  }

  .metric-cell:nth-child(n + 4) {
    border-top: 1px solid var(--hairline);
  }

  .metric-cell:nth-child(4) {
    border-left: none;
  }

  .quality-grid {
    grid-template-columns: 1fr;
  }
}
</style>
