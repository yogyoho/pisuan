<template>
  <div class="meta-panel">
    <!-- 指标带：总数 / 已标注 / 年份待补 / 规模待裁决 -->
    <div class="metric-strip">
      <div class="metric-cell">
        <span class="metric-label">语料报告</span>
        <span class="metric-value">{{ counts.total }}<small>份</small></span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">已人工标注</span>
        <span class="metric-value">{{ counts.annotated }}<small>份</small></span>
      </div>
      <div class="metric-cell" :class="{ warn: counts.year_missing > 0 }">
        <span class="metric-label">年份待补</span>
        <span class="metric-value">{{ counts.year_missing }}<small>份</small></span>
      </div>
      <div class="metric-cell" :class="{ warn: counts.scale_missing > 0 }">
        <span class="metric-label">规模待裁决</span>
        <span class="metric-value">{{ counts.scale_missing }}<small>份</small></span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">规模候选需复核</span>
        <span class="metric-value">{{ counts.scale_needs_review }}<small>份</small></span>
      </div>
    </div>

    <!-- 工具条 -->
    <div class="toolbar">
      <div class="filter-row">
        <a-radio-group v-model:value="filters.state" button-style="solid" @change="applyFilters">
          <a-radio-button value="">全部</a-radio-button>
          <a-radio-button value="annotated">已标注</a-radio-button>
          <a-radio-button value="todo">待标注</a-radio-button>
        </a-radio-group>
        <a-select v-model:value="filters.stage" style="width: 150px" @change="applyFilters">
          <a-select-option value="">全部阶段</a-select-option>
          <a-select-option v-for="s in STAGES" :key="s.key" :value="s.key">{{ s.label }}</a-select-option>
        </a-select>
        <a-input-search
          v-model:value="filters.q"
          placeholder="按报告 ID 搜索"
          style="width: 200px"
          allow-clear
          @search="applyFilters"
        />
      </div>
      <div class="action-row">
        <a-button :loading="importing" @click="onImport">导入存量标注</a-button>
        <a-button v-if="userStore.isAdmin" type="primary" :loading="exporting" @click="onExport">
          导出物化
        </a-button>
      </div>
    </div>

    <a-table
      v-if="filteredItems.length"
      :data-source="filteredItems"
      :columns="columns"
      :loading="loading"
      :row-key="(r) => r.report_id"
      :pagination="{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'report_id'">
          <span class="rid-cell" :title="record.report_id">{{ record.report_id }}</span>
        </template>
        <template v-else-if="column.key === 'stage'">
          {{ stageLabel(record.stage) }}
        </template>
        <template v-else-if="column.key === 'scale_candidates'">
          <span v-if="record.scale_candidates.length" class="cand-cell" :title="candidatesText(record)">
            {{ candidatesText(record) }}
          </span>
          <span v-else class="muted">—</span>
        </template>
        <template v-else-if="column.key === 'annotation'">
          <div v-if="hasAnnotation(record)" class="ann-cell">
            <span v-if="record.annotation.year_hint" class="ann-item">年份 {{ record.annotation.year_hint }}</span>
            <span v-if="record.annotation.scale_mt_a" class="ann-item">{{ record.annotation.scale_mt_a }} 万t/a</span>
            <small class="ann-by">{{ record.annotation.decided_by }}</small>
          </div>
          <span v-else class="muted">未标注</span>
        </template>
        <template v-else-if="column.key === 'flags'">
          <span v-if="record.scale_basis === 'manual'" class="flag-tag flag-manual">已核实</span>
          <span v-else class="flag-tag flag-review">候选需复核</span>
          <span v-if="record.year_missing" class="flag-tag flag-missing">缺年份</span>
          <span v-if="record.scale_missing" class="flag-tag flag-missing">缺规模</span>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a class="primary" @click="openAnnotate(record)">标注…</a>
        </template>
      </template>
    </a-table>

    <div v-else-if="!loading" class="empty-state">
      <a-empty :description="emptyDesc">
        <a-button v-if="isFiltered" @click="clearFilters">清除筛选</a-button>
      </a-empty>
    </div>

    <!-- 标注对话框 -->
    <a-modal
      v-model:open="dlg.open"
      :title="`标注 · ${dlg.record?.report_id ?? ''}`"
      :confirm-loading="dlg.submitting"
      ok-text="保存标注"
      @ok="onSubmit"
    >
      <div v-if="dlg.record" class="dlg-meta">
        <p class="dlg-line">
          {{ stageLabel(dlg.record.stage) }} · {{ dlg.record.province }} ·
          自动年份 {{ dlg.record.auto_year_hint ?? '—' }} · 自动规模 {{ dlg.record.auto_scale_mt_a ?? '—' }}
          <template v-if="dlg.record.scale_basis === 'manual'">（规模已核实）</template>
        </p>
        <div v-if="dlg.record.scale_candidates.length" class="cand-box">
          <span class="cand-title">规模候选簇（自动抽取，点击快填）：</span>
          <a-tag
            v-for="(c, i) in dlg.record.scale_candidates"
            :key="i"
            class="cand-tag"
            @click="dlg.form.scale_mt_a = c.value"
          >
            {{ c.label }} {{ c.value }}
          </a-tag>
        </div>
      </div>
      <a-form layout="vertical" class="dlg-form">
        <a-form-item label="年份 year_hint（2000–2100 整数，留空清除）">
          <a-input-number
            v-model:value="dlg.form.year_hint"
            :min="2000"
            :max="2100"
            :precision="0"
            style="width: 160px"
          />
        </a-form-item>
        <a-form-item label="规模 scale_mt_a（万吨/年，(0, 10000]，留空清除）">
          <a-input-number v-model:value="dlg.form.scale_mt_a" :min="0.1" :max="10000" :step="0.1" style="width: 160px" />
        </a-form-item>
        <a-form-item label="备注（仅平台库留档，不进物化文件）">
          <a-textarea v-model:value="dlg.form.note" :rows="2" placeholder="裁决依据，如「来自第 3 章建设规模」" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { eiaMetaApi } from '@/apis/eia_meta_api'
import { useUserStore } from '@/stores/user'

const STAGES = [
  { key: 'planning_eia', label: '规划环评' },
  { key: 'post_eia', label: '事后环评' },
  { key: 'project_eia_openpit', label: '项目环评·露天' },
  { key: 'project_eia_underground', label: '项目环评·井工' },
  { key: 'tracking_eia', label: '跟踪评价' }
]
const STAGE_LABELS = Object.fromEntries(STAGES.map((s) => [s.key, s.label]))

const userStore = useUserStore()
const route = useRoute()
const loading = ref(false)
const importing = ref(false)
const exporting = ref(false)
const items = ref([])
const counts = reactive({ total: 0, annotated: 0, year_missing: 0, scale_missing: 0, scale_needs_review: 0 })
const filters = reactive({ state: '', stage: '', q: '' })
// 深链入口：/eia-data/meta?state=todo|annotated 直落对应筛选（总览页 chip 分流）
const deepState = String(route.query.state ?? '')
if (deepState === 'todo' || deepState === 'annotated') {
  filters.state = deepState
}

const columns = [
  { title: '报告 ID', key: 'report_id', width: 200, ellipsis: true },
  { title: '阶段', key: 'stage', width: 110 },
  { title: '省份', dataIndex: 'province', key: 'province', width: 70 },
  { title: '规模候选簇', key: 'scale_candidates', ellipsis: true },
  { title: '当前标注', key: 'annotation', width: 190 },
  { title: '标志', key: 'flags', width: 180 },
  { title: '操作', key: 'actions', width: 80 }
]

const stageLabel = (k) => STAGE_LABELS[k] || k
const hasAnnotation = (r) => r.annotation && (r.annotation.year_hint != null || r.annotation.scale_mt_a != null)
const candidatesText = (r) => r.scale_candidates.map((c) => `${c.label} ${c.value}`).join('；')

const isFiltered = computed(() => Boolean(filters.state || filters.stage || filters.q))
const emptyDesc = computed(() => (isFiltered.value ? '当前筛选无匹配报告' : '语料元数据为空'))

const filteredItems = computed(() => {
  let list = items.value
  if (filters.state === 'annotated') list = list.filter((r) => hasAnnotation(r))
  if (filters.state === 'todo') list = list.filter((r) => !hasAnnotation(r))
  if (filters.stage) list = list.filter((r) => r.stage === filters.stage)
  if (filters.q) {
    const q = filters.q.toLowerCase()
    list = list.filter((r) => r.report_id.toLowerCase().includes(q))
  }
  return list
})

const applyFilters = () => {
  /* 纯前端过滤：31 条全量在内存 */
}

const clearFilters = () => {
  filters.state = ''
  filters.stage = ''
  filters.q = ''
}

const fetchList = async () => {
  loading.value = true
  try {
    const data = await eiaMetaApi.listReports()
    items.value = data.items
    Object.assign(counts, data.counts)
  } catch (e) {
    message.error(e?.message || '元数据加载失败')
  } finally {
    loading.value = false
  }
}

const onImport = async () => {
  importing.value = true
  try {
    const r = await eiaMetaApi.importAnnotations()
    if (r.skipped_unknown > 0) {
      message.warning(`导入完成：新增 ${r.added} 条；${r.skipped_unknown} 条 rid 不在语料清单，已跳过（请核对人工层文件）`)
    } else {
      message.success(`导入完成：文件 ${r.scanned} 条，新增 ${r.added} 条`)
    }
    await fetchList()
  } catch (e) {
    message.error(e?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

const onExport = async () => {
  exporting.value = true
  message.loading({ content: '正在物化…', key: 'meta-export', duration: 0 })
  try {
    const r = await eiaMetaApi.exportAnnotations()
    message.success({ content: `已重写人工层文件（${r.materialized} 条）`, key: 'meta-export' })
  } catch (e) {
    message.error({ content: e?.message || '导出失败', key: 'meta-export' })
  } finally {
    exporting.value = false
  }
}

// ── 标注对话框 ──────────────────────────────────────────

const dlg = reactive({ open: false, submitting: false, record: null, form: { year_hint: null, scale_mt_a: null, note: '' } })

const openAnnotate = (record) => {
  dlg.record = record
  dlg.form.year_hint = record.annotation?.year_hint ?? null
  dlg.form.scale_mt_a = record.annotation?.scale_mt_a ?? null
  dlg.form.note = record.annotation?.note || ''
  dlg.open = true
}

const onSubmit = async () => {
  const { year_hint, scale_mt_a, note } = dlg.form
  if (year_hint == null && scale_mt_a == null && !hasAnnotation(dlg.record)) {
    message.warning('年份与规模至少标注一项（或留空保存以清除标注）')
    return
  }
  dlg.submitting = true
  try {
    await eiaMetaApi.setAnnotation(dlg.record.report_id, {
      annotations: Object.fromEntries(
        [
          ['year_hint', year_hint],
          ['scale_mt_a', scale_mt_a]
        ].filter(([, v]) => v != null)
      ),
      note: note || null
    })
    message.success(`「${dlg.record.report_id}」标注已保存`)
    dlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '标注保存失败')
  } finally {
    dlg.submitting = false
  }
}

onMounted(fetchList)
</script>

<style lang="less" scoped>
.meta-panel {
  --hairline: var(--gray-200);
}

/* ── 指标带 ─────────────────────────────────────────── */
.metric-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  background: var(--main-0);
  border: 1px solid var(--hairline);
  border-radius: 6px;
  margin-bottom: 12px;
}

.metric-cell {
  padding: 12px 16px;
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
    font-size: 20px;
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
}

/* ── 工具条 ─────────────────────────────────────────── */
.toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── 表格单元格 ─────────────────────────────────────── */
.rid-cell {
  font-weight: 600;
  color: var(--gray-800);
  font-size: 12px;
}

.muted {
  color: var(--gray-400);
}

.cand-cell {
  font-size: 12px;
  color: var(--gray-500);
  cursor: help;
}

.ann-cell {
  display: flex;
  flex-direction: column;

  .ann-item {
    font-size: 13px;
    font-weight: 600;
    color: var(--main-600);
    font-variant-numeric: tabular-nums;
  }

  .ann-by {
    font-size: 11px;
    color: var(--gray-400);
  }
}

.flag-tag {
  display: inline-block;
  margin-right: 4px;
  margin-bottom: 2px;
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 18px;
}

.flag-manual {
  color: var(--main-600);
  border: 1px solid var(--main-600);
  background: var(--main-0);
}

.flag-review {
  color: var(--second-600);
  border: 1px solid var(--second-600);
  background: var(--main-0);
}

.flag-missing {
  color: var(--gray-500);
  border: 1px dashed var(--gray-300);
  background: var(--gray-50);
}

a.primary {
  color: var(--main-600);
  font-weight: 600;
}

/* ── 空态 ───────────────────────────────────────────── */
.empty-state {
  padding: 48px 0;
  background: var(--main-0);
  border: 1px solid var(--hairline);
  border-radius: 6px;
  text-align: center;
}

/* ── 标注对话框 ─────────────────────────────────────── */
.dlg-meta {
  margin-bottom: 12px;
}

.dlg-line {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--gray-600);
}

.cand-box {
  padding: 8px 10px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  background: var(--gray-50);

  .cand-title {
    display: block;
    margin-bottom: 6px;
    font-size: 12px;
    color: var(--gray-500);
  }

  .cand-tag {
    cursor: pointer;

    &:hover {
      color: var(--main-600);
      border-color: var(--main-600);
    }
  }
}

.dlg-form {
  margin-top: 4px;
}

/* ── 响应式 ─────────────────────────────────────────── */
@media (max-width: 1200px) {
  .metric-strip {
    grid-template-columns: repeat(3, 1fr);
  }

  .metric-cell:nth-child(n + 4) {
    border-top: 1px solid var(--hairline);
  }

  .metric-cell:nth-child(4) {
    border-left: none;
  }
}
</style>
