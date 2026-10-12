<template>
  <div class="standards-panel">
    <!-- 指标带：标准总数 / 文件待核实 / 已核实裁决 / 限值表待录入 -->
    <div class="metric-strip">
      <div class="metric-cell">
        <span class="metric-label">标准总数</span>
        <span class="metric-value">{{ counts.total }}<small>条</small></span>
      </div>
      <div class="metric-cell" :class="{ warn: counts.needs_verification > 0 }">
        <span class="metric-label">文件待核实</span>
        <span class="metric-value">{{ counts.needs_verification }}<small>条</small></span>
      </div>
      <div class="metric-cell">
        <span class="metric-label">已核实裁决</span>
        <span class="metric-value">{{ counts.confirmed }}<small>条</small></span>
      </div>
      <div class="metric-cell" :class="{ warn: counts.limit_tables_pending > 0 }">
        <span class="metric-label">限值表待录入</span>
        <span class="metric-value">{{ counts.limit_tables_pending }}<small>张</small></span>
      </div>
    </div>

    <!-- 工具条 -->
    <div class="toolbar">
      <div class="filter-row">
        <a-radio-group v-model:value="filters.state" button-style="solid">
          <a-radio-button value="">全部</a-radio-button>
          <a-radio-button value="todo">待核实</a-radio-button>
          <a-radio-button value="done">已核实</a-radio-button>
        </a-radio-group>
        <a-select v-model:value="filters.tier" style="width: 140px">
          <a-select-option value="">全部层级</a-select-option>
          <a-select-option v-for="t in TIERS" :key="t.key" :value="t.key">{{ t.label }}</a-select-option>
        </a-select>
        <a-input-search v-model:value="filters.q" placeholder="按编号/名称搜索" style="width: 220px" allow-clear />
      </div>
      <div class="action-row">
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
      :row-key="(r) => r.code"
      :pagination="{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'code'">
          <span class="code-cell" :title="record.code">{{ record.code }}</span>
        </template>
        <template v-else-if="column.key === 'title'">
          <!-- 主行名称 + 副行写作作用（role）：写手按 role 决定该标准在报告中的用法 -->
          <div class="title-cell">
            <span class="title-main" :title="record.title">{{ record.title }}</span>
            <span v-if="record.role" class="title-role" :title="record.role">{{
              record.role
            }}</span>
          </div>
        </template>
        <template v-else-if="column.key === 'tier'">
          {{ tierLabel(record.tier) }}
        </template>
        <template v-else-if="column.key === 'chapters'">
          <!-- chapters 实况为分号分隔字符串（62/62），非数组 -->
          <span v-if="record.chapters" class="muted">{{ record.chapters }}</span>
          <span v-else class="muted">—</span>
        </template>
        <template v-else-if="column.key === 'cited_count'">
          <span :class="record.cited_count > 0 ? 'cited' : 'muted'">{{ record.cited_count }}</span>
        </template>
        <template v-else-if="column.key === 'flags'">
          <span v-if="!record.needs_verification" class="flag-tag flag-ok">已核实</span>
          <span v-else-if="record.review.action" class="flag-tag flag-pending">已裁决·待导出</span>
          <span v-else class="flag-tag flag-todo">待核实</span>
        </template>
        <template v-else-if="column.key === 'review'">
          <div v-if="record.review.action" class="review-cell">
            <span class="review-by">{{ record.review.decided_by }}</span>
            <small v-if="record.review.note" class="review-note" :title="record.review.note">{{ record.review.note }}</small>
          </div>
          <span v-else class="muted">—</span>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a class="primary" @click="openReview(record)">{{ record.needs_verification || !record.review.action ? '核实…' : '查看…' }}</a>
        </template>
      </template>
    </a-table>

    <div v-else-if="!loading" class="empty-state">
      <a-empty :description="emptyDesc">
        <a-button v-if="isFiltered" @click="clearFilters">清除筛选</a-button>
      </a-empty>
    </div>

    <!-- 门 1 体检卡（P2-3 只读）：规则规格 + 注册表自检（code 对 allowed_patterns），不伪造违规明细 -->
    <div v-if="gate1" class="gate1-card">
      <div class="gate1-hd">
        <div class="gate1-badge"><ShieldCheck :size="16" /></div>
        <div>
          <h3>门 1 · 标准号体检</h3>
          <div class="hd-sub" :title="gate1.desc">gate1_code_checks · 写作前标准引用合法性规则与当前命中</div>
        </div>
        <div class="hd-right">
          <span v-if="gate1.registry_check.violations.length" class="pill-warn-tag">
            {{ gate1.registry_check.violations.length }} 项待修正
          </span>
          <span v-else class="pill-ok-tag">全部通过</span>
        </div>
      </div>
      <div class="gate1-metrics">
        <div class="gate1-m">
          <span class="v num">{{ gate1.registry_check.total }}</span>
          <span class="l">在册标准</span>
          <span class="h">standards[].code</span>
        </div>
        <div class="gate1-m">
          <span class="v num">{{ gate1.allowed_patterns.length }}</span>
          <span class="l">引用模式</span>
          <span class="h">allowed_patterns</span>
        </div>
        <div class="gate1-m">
          <span class="v num" :class="gate1.registry_check.violations.length ? 'hot' : 'zero'">
            {{ gate1.registry_check.violations.length }}
          </span>
          <span class="l">命不上模式</span>
          <span class="h">需人工核对登记</span>
        </div>
      </div>
      <div class="gate1-body">
        <div class="gate1-patterns">
          <span class="pl-label">引用模式</span>
          <code v-for="p in gate1.allowed_patterns" :key="p" class="k">{{ p }}</code>
        </div>
        <ol class="gate1-rules">
          <li v-for="(r, i) in gate1.rules" :key="i">{{ r }}</li>
        </ol>
        <template v-if="gate1.registry_check.violations.length">
          <div class="gate1-viol">
            <span class="pl-label">命不上模式的在册编号</span>
            <code v-for="c in gate1.registry_check.violations" :key="c" class="k viol">{{ c }}</code>
          </div>
        </template>
      </div>
    </div>

    <!-- 限值查找表：人工录入（整表替换，DB 真源）→ 导出物化翻转两标志 -->
    <div class="limits-section">
      <div class="limits-header">
        <div class="limits-header-main">
          <div>
            <h3>限值查找表</h3>
            <p class="limits-sub">
              档位未录入前，达标判定一律输出「需人工对照」，禁自动断言；录入须对照标准原文，导出物化后写作技能方可引用
            </p>
          </div>
          <a-button
            v-if="userStore.isAdmin"
            size="small"
            :disabled="!dbTableCount"
            :loading="exporting"
            @click="exportLimits"
          >
            导出限值行{{ dbTableCount ? `（${dbTableCount} 张待物化）` : '' }}
          </a-button>
        </div>
      </div>
      <div class="limits-grid">
        <div v-for="(t, name) in limitTables" :key="name" class="limit-card">
          <div class="limit-head">
            <span class="limit-desc">{{ t.desc }}</span>
            <span class="limit-head-right">
              <a v-if="userStore.isAdmin" class="limit-edit" @click="openLimitEdit(name, t)"
                >编辑…</a
              >
              <a-tag class="limit-ref">{{ t.code_ref }}</a-tag>
            </span>
          </div>
          <div class="limit-flags">
            <span v-if="!t.needs_verification" class="flag-tag flag-ok">已核实</span>
            <span v-else-if="(t.rows || []).length" class="flag-tag flag-pending">
              已录入 {{ t.rows.length }} 行 · {{ t.source === 'db' ? '待导出' : '待核对全表' }}
            </span>
            <span v-else class="flag-tag flag-todo">未录入</span>
          </div>
          <!-- 已录入限值行：列头取服务端 schemas（字段顺序权威），缺席时回退首行键 -->
          <table v-if="(t.rows || []).length" class="limit-rows">
            <thead>
              <tr>
                <th v-for="k in rowKeys(name, t)" :key="k">{{ rowKeyLabel(name, k) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in t.rows" :key="i">
                <td v-for="k in rowKeys(name, t)" :key="k">{{ r[k] }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="t.note" class="limit-note">{{ t.note }}</p>
        </div>
      </div>
    </div>

    <!-- 核实对话框 -->
    <a-modal
      v-model:open="dlg.open"
      :title="`核实 · ${dlg.record?.code ?? ''}`"
      :confirm-loading="dlg.submitting"
      ok-text="确认核实无误"
      @ok="onSubmit"
    >
      <div v-if="dlg.record" class="dlg-meta">
        <p class="dlg-title">{{ dlg.record.title }}</p>
        <p class="dlg-line">
          {{ tierLabel(dlg.record.tier) }}
          <template v-if="dlg.record.chapters"> · 章节 {{ dlg.record.chapters }}</template>
          · 语料引用 {{ dlg.record.cited_count }} 份
        </p>
        <div class="redline-box">
          <span class="redline-title">核实语义（红线）</span>
          web_search 结果不采信，仅当已对照<strong>标准原文</strong>确认编号、年份、名称无误时才可确认。
          导出物化后该条目转「已核实」，写作技能将按注册表引用规范书写；但<strong>限值数值断言仍以限值查找表数据在位为准</strong>——
          档位未录入前达标判定一律输出「需人工对照」。
        </div>
      </div>
      <a-form layout="vertical" class="dlg-form">
        <a-form-item label="备注（仅平台库留档，不进物化文件）">
          <a-textarea v-model:value="dlg.form.note" :rows="2" placeholder="核实依据，如「已对照生态环境部官网现行版本」" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 限值行编辑对话框（整表替换保存） -->
    <a-modal
      v-model:open="editDlg.open"
      :title="`限值录入 · ${editDlg.tableMeta?.desc ?? ''}`"
      :confirm-loading="editDlg.submitting"
      :width="720"
      ok-text="保存录入"
      @ok="onSaveRows"
    >
      <p class="rows-editor-sub">
        整表替换保存（DB 即导出真源）；数值字段对照标准原文录入纯数字，禁带区间或文字。
      </p>
      <table class="rows-edit-table">
        <thead>
          <tr>
            <th v-for="(spec, k) in editFields" :key="k">{{ spec.label }}</th>
            <th class="op-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in editDlg.rows" :key="i">
            <td v-for="(spec, k) in editFields" :key="k">
              <a-input-number
                v-if="spec.type === 'number'"
                v-model:value="row[k]"
                style="width: 100%"
              />
              <a-input v-else v-model:value="row[k]" />
            </td>
            <td class="op-col"><a class="danger" @click="editDlg.rows.splice(i, 1)">删除</a></td>
          </tr>
        </tbody>
      </table>
      <a-button size="small" @click="addBlankRow">＋ 添加一行</a-button>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ShieldCheck } from '@lucide/vue'
import { eiaStandardApi } from '@/apis/eia_standard_api'
import { useUserStore } from '@/stores/user'

const TIERS = [
  { key: 'framework', label: '框架标准' },
  { key: 'quality_limit', label: '质量标准' },
  { key: 'emission_limit', label: '排放标准' },
  { key: 'method_param', label: '方法与参数' },
  { key: 'pending', label: '档位待定' }
]
const TIER_LABELS = Object.fromEntries(TIERS.map((t) => [t.key, t.label]))

const userStore = useUserStore()
const loading = ref(false)
const exporting = ref(false)
const items = ref([])
const limitTables = ref({})
const schemas = ref({})
const gate1 = ref(null)
const counts = reactive({ total: 0, needs_verification: 0, confirmed: 0, limit_tables_pending: 0 })
const filters = reactive({ state: '', tier: '', q: '' })

const columns = [
  { title: '标准编号', key: 'code', width: 180, ellipsis: true },
  // 名称列弹性宽；不设 ellipsis（nowrap 继承会压掉 role 副行折行），bodyCell 渲染主行 + role 副行
  { title: '名称', key: 'title' },
  { title: '层级', key: 'tier', width: 110 },
  { title: '章节', key: 'chapters', width: 140, ellipsis: true },
  { title: '语料引用', key: 'cited_count', width: 90, align: 'right' },
  { title: '核实态', key: 'flags', width: 130 },
  { title: '裁决', key: 'review', width: 190 },
  { title: '操作', key: 'actions', width: 80 }
]

const tierLabel = (k) => TIER_LABELS[k] || k

// 限值行列头取服务端 schemas（字段顺序与中文标签权威）；schemas 缺席时回退首行键
const rowKeys = (name, t) => {
  const s = schemas.value[name]
  if (s) return Object.keys(s)
  return Object.keys(t.rows?.[0] || {}).filter((k) => k !== 'origin')
}
const rowKeyLabel = (name, k) => schemas.value[name]?.[k]?.label || k

const isFiltered = computed(() => Boolean(filters.state || filters.tier || filters.q))
const emptyDesc = computed(() => (isFiltered.value ? '当前筛选无匹配标准' : '标准注册表为空'))

const filteredItems = computed(() => {
  let list = items.value
  if (filters.state === 'todo') list = list.filter((r) => r.needs_verification && !r.review.action)
  if (filters.state === 'done') list = list.filter((r) => !r.needs_verification || r.review.action)
  if (filters.tier) list = list.filter((r) => r.tier === filters.tier)
  if (filters.q) {
    const q = filters.q.toLowerCase()
    list = list.filter((r) => r.code.toLowerCase().includes(q) || (r.title || '').toLowerCase().includes(q))
  }
  return list
})

const clearFilters = () => {
  filters.state = ''
  filters.tier = ''
  filters.q = ''
}

const fetchList = async () => {
  loading.value = true
  try {
    const [data, limits, gate1Data] = await Promise.all([
      eiaStandardApi.listStandards(),
      eiaStandardApi.listLimits(),
      eiaStandardApi.getGate1().catch(() => null) // 体检卡独立降级：不阻塞标准表主链
    ])
    items.value = data.items
    Object.assign(counts, data.counts)
    schemas.value = limits.schemas || {}
    limitTables.value = Object.fromEntries(
      Object.entries(limits.limit_tables).filter(([, v]) => typeof v === 'object' && v !== null)
    )
    gate1.value = gate1Data
  } catch (e) {
    message.error(e?.message || '标准库加载失败')
  } finally {
    loading.value = false
  }
}

const onExport = async () => {
  exporting.value = true
  message.loading({ content: '正在物化…', key: 'std-export', duration: 0 })
  try {
    const r = await eiaStandardApi.exportReviews()
    message.success({
      content: `已翻转 ${r.materialized} 条裁决 → standards_index.json（落运行栈技能目录，需人工回流 pisuan-custom）`,
      key: 'std-export'
    })
    await fetchList()
  } catch (e) {
    message.error({ content: e?.message || '导出失败', key: 'std-export' })
  } finally {
    exporting.value = false
  }
}

// ── 核实对话框 ──────────────────────────────────────────

const dlg = reactive({ open: false, submitting: false, record: null, form: { note: '' } })

const openReview = (record) => {
  dlg.record = record
  dlg.form.note = record.review?.note || ''
  dlg.open = true
}

const onSubmit = async () => {
  dlg.submitting = true
  try {
    await eiaStandardApi.setReview(dlg.record.code, {
      action: 'confirm',
      note: dlg.form.note || null
    })
    message.success(`「${dlg.record.code}」核实裁决已保存（导出物化后生效）`)
    dlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '核实保存失败')
  } finally {
    dlg.submitting = false
  }
}

// ── 限值行编辑对话框（整表替换保存）──────────────────────

const dbTableCount = computed(
  () => Object.values(limitTables.value).filter((t) => t.source === 'db').length
)

const editDlg = reactive({
  open: false,
  submitting: false,
  tableKey: '',
  tableMeta: null,
  rows: []
})
const editFields = computed(() => schemas.value[editDlg.tableKey] || {})

const addBlankRow = () => {
  const blank = {}
  for (const [k, spec] of Object.entries(editFields.value))
    blank[k] = spec.type === 'number' ? null : ''
  editDlg.rows.push(blank)
}

const openLimitEdit = (name, t) => {
  editDlg.tableKey = name
  editDlg.tableMeta = t
  // 按 schema 投影装载：文件锚点行携带的 origin 等溯源字段不进编辑器（服务端校验拒收）
  const fields = schemas.value[name] || {}
  editDlg.rows = (t.rows || []).map((r) =>
    Object.fromEntries(
      Object.entries(fields).map(([k, spec]) => [k, r[k] ?? (spec.type === 'number' ? null : '')])
    )
  )
  if (!editDlg.rows.length) addBlankRow()
  editDlg.open = true
}

const onSaveRows = async () => {
  editDlg.submitting = true
  try {
    const r = await eiaStandardApi.saveLimitRows(editDlg.tableKey, editDlg.rows)
    message.success(
      `「${editDlg.tableMeta?.desc || editDlg.tableKey}」已保存 ${r.saved} 行（导出物化后生效）`
    )
    editDlg.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '限值行保存失败')
  } finally {
    editDlg.submitting = false
  }
}

const exportLimits = async () => {
  exporting.value = true
  message.loading({ content: '正在物化限值行…', key: 'limits-export', duration: 0 })
  try {
    const r = await eiaStandardApi.exportLimits()
    message.success({
      content: `已物化 ${r.materialized} 张限值表 ${r.rows} 行 → standards_index.json（落运行栈技能目录，需人工回流 pisuan-custom）`,
      key: 'limits-export'
    })
    await fetchList()
  } catch (e) {
    message.error({ content: e?.message || '限值行导出失败', key: 'limits-export' })
  } finally {
    exporting.value = false
  }
}

onMounted(fetchList)
</script>

<style lang="less" scoped>
.standards-panel {
  --hairline: var(--gray-200);
}

/* ── 指标带 ─────────────────────────────────────────── */
.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
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
.code-cell {
  font-weight: 600;
  color: var(--gray-800);
  font-size: 12px;
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  .title-main {
    color: var(--gray-800);
  }

  .title-role {
    font-size: 11px;
    line-height: 1.5;
    color: var(--gray-400);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    white-space: normal;
    word-break: break-all;
  }
}

.muted {
  color: var(--gray-400);
}

.cited {
  font-weight: 600;
  color: var(--main-600);
  font-variant-numeric: tabular-nums;
}

.review-cell {
  display: flex;
  flex-direction: column;

  .review-by {
    font-size: 13px;
    font-weight: 600;
    color: var(--main-600);
  }

  .review-note {
    font-size: 11px;
    color: var(--gray-400);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.flag-tag {
  display: inline-block;
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 18px;
}

.flag-ok {
  color: var(--main-600);
  border: 1px solid var(--main-600);
  background: var(--main-0);
}

.flag-pending {
  color: var(--second-600);
  border: 1px solid var(--second-600);
  background: var(--main-0);
}

.flag-todo {
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

/* ── 限值查找表（只读） ─────────────────────────────── */
.limits-section {
  margin-top: 20px;
}

.limits-header {
  margin-bottom: 10px;

  .limits-header-main {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 12px;
  }

  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--gray-800);
  }

  .limits-sub {
    margin: 4px 0 0;
    font-size: 12px;
    color: var(--gray-500);
  }
}

.limits-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 10px;
}

.limit-card {
  padding: 12px 14px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  background: var(--main-0);

  .limit-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
  }

  .limit-desc {
    font-size: 13px;
    font-weight: 600;
    color: var(--gray-800);
  }

  .limit-ref {
    flex-shrink: 0;
    font-size: 11px;
    color: var(--gray-600);
  }

  .limit-head-right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .limit-edit {
    font-size: 12px;
    color: var(--main-600);
  }

  .limit-flags {
    margin-bottom: 4px;
  }

  .limit-rows {
    width: 100%;
    margin-top: 6px;
    border-collapse: collapse;
    font-size: 12px;

    th,
    td {
      padding: 4px 8px;
      border: 1px solid var(--hairline);
      text-align: left;
    }

    th {
      font-weight: 600;
      color: var(--gray-600);
      background: var(--gray-50);
    }

    td {
      color: var(--gray-800);
      font-variant-numeric: tabular-nums;
    }
  }

  .limit-note {
    margin: 4px 0 0;
    font-size: 11px;
    color: var(--gray-400);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
}

/* ── 核实对话框 ─────────────────────────────────────── */
.dlg-meta {
  margin-bottom: 12px;
}

.dlg-title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gray-800);
}

.dlg-line {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--gray-600);
}

.redline-box {
  padding: 10px 12px;
  border: 1px solid var(--second-600);
  border-radius: 6px;
  background: var(--main-0);
  font-size: 12px;
  line-height: 1.7;
  color: var(--gray-600);

  .redline-title {
    display: block;
    margin-bottom: 4px;
    font-weight: 600;
    color: var(--second-600);
  }

  strong {
    color: var(--gray-800);
  }
}

.dlg-form {
  margin-top: 4px;
}

/* ── 限值行编辑对话框 ───────────────────────────────── */
.rows-editor-sub {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--gray-500);
}

.rows-edit-table {
  width: 100%;
  margin-bottom: 10px;
  border-collapse: collapse;

  th,
  td {
    padding: 4px 6px;
    border: 1px solid var(--hairline);
  }

  th {
    font-size: 12px;
    font-weight: 600;
    color: var(--gray-600);
    background: var(--gray-50);
    text-align: left;
  }

  td {
    color: var(--gray-800);
  }

  .op-col {
    width: 48px;
    text-align: center;
  }

  a.danger {
    color: var(--second-600);
    font-size: 12px;
  }
}

/* ── 门 1 体检卡 ── */
.gate1-card {
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--gray-0);
  margin-bottom: 12px;
  overflow: hidden;
}

.gate1-hd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;

  h3 {
    font-size: 14px;
    font-weight: 600;
    margin: 0;
  }

  .hd-sub {
    font-size: 12px;
    color: var(--gray-500);
  }

  .hd-right {
    margin-left: auto;
  }
}

.gate1-badge {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--main-0);
  color: var(--main-600);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.pill-warn-tag,
.pill-ok-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
}

.pill-warn-tag {
  background: var(--second-50, var(--gray-100));
  color: var(--second-600);
}

.pill-ok-tag {
  background: var(--main-0);
  color: var(--main-600);
}

.gate1-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--hairline);
}

.gate1-m {
  padding: 11px 16px;
  display: flex;
  align-items: baseline;
  gap: 8px;

  & + & {
    border-left: 1px solid var(--hairline);
  }

  .v {
    font-size: 20px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;

    &.zero {
      color: var(--main-600);
    }

    &.hot {
      color: var(--second-600);
    }
  }

  .l {
    font-size: 12px;
    color: var(--gray-600);
  }

  .h {
    margin-left: auto;
    font-size: 11px;
    color: var(--gray-500);
  }
}

.gate1-body {
  border-top: 1px solid var(--hairline);
  padding: 10px 16px 12px;
}

.pl-label {
  display: inline-block;
  font-size: 12px;
  color: var(--gray-500);
  margin-right: 8px;
}

.gate1-patterns,
.gate1-viol {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

code.k {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  background: var(--gray-100);
  border-radius: 4px;
  padding: 1px 6px;
  color: var(--gray-700);

  &.viol {
    color: var(--second-600);
    background: var(--second-50, var(--gray-100));
  }
}

.gate1-rules {
  margin: 8px 0 0;
  padding-left: 30px;
  font-size: 12px;
  color: var(--gray-600);
  line-height: 1.9;

  li + li {
    margin-top: 2px;
  }
}

.gate1-viol {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--hairline);
}
</style>
