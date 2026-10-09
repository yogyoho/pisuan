<template>
  <div class="lexicon-panel">
    <!-- 工具条：状态筛选 + 维度过滤 + 运营动作 -->
    <div class="toolbar">
      <div class="filter-row">
        <a-radio-group v-model:value="filters.status" class="status-chips" button-style="solid" @change="fetchList">
          <a-radio-button value="">全部 {{ total }}</a-radio-button>
          <a-radio-button v-for="s in STATUS_DEFS" :key="s.key" :value="s.key">
            {{ s.label }} {{ counts[s.key] ?? 0 }}
          </a-radio-button>
        </a-radio-group>
        <a-select v-model:value="filters.category" style="width: 130px" @change="fetchList">
          <a-select-option value="">全部分类</a-select-option>
          <a-select-option v-for="c in CATEGORY_DEFS" :key="c.key" :value="c.key">{{ c.label }}</a-select-option>
        </a-select>
        <a-select v-model:value="filters.stage" style="width: 150px" @change="fetchList">
          <a-select-option value="">全部阶段</a-select-option>
          <a-select-option v-for="s in STAGES" :key="s.key" :value="s.key">{{ s.label }}</a-select-option>
        </a-select>
        <a-input-search
          v-model:value="filters.q"
          placeholder="按口径名搜索"
          style="width: 200px"
          allow-clear
          @search="fetchList"
        />
      </div>
      <div class="action-row">
        <a-button :loading="importing" @click="onImport">
          <RefreshCw :size="14" style="margin-right: 4px" />重扫语料导入
        </a-button>
        <template v-if="userStore.isAdmin">
          <a-button type="primary" :loading="exporting" @click="onExport">导出物化</a-button>
          <div class="switch-box">
            <span class="switch-label">覆盖层</span>
            <a-switch
              :checked="switchState.enabled"
              :loading="switchLoading"
              size="small"
              @change="(v) => onToggleSwitch(v)"
            />
            <span class="switch-hint" :title="switchHint">{{ switchHint }}</span>
          </div>
        </template>
        <span v-else class="switch-hint">{{ switchHint }}</span>
      </div>
    </div>

    <a-table
      :data-source="items"
      :columns="columns"
      :loading="loading"
      :row-key="(r) => r.id"
      :pagination="{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'caliber'">
          <div class="caliber-cell">
            <span class="caliber-name">{{ record.caliber }}</span>
            <span v-if="record.note" class="caliber-note" :title="record.note">{{ record.note }}</span>
          </div>
        </template>
        <template v-else-if="column.key === 'stage'">
          {{ stageLabel(record.stage) }}
        </template>
        <template v-else-if="column.key === 'category'">
          <span class="cat-tag" :class="`cat-${record.category}`">{{ categoryLabel(record.category) }}</span>
        </template>
        <template v-else-if="column.key === 'status'">
          <span class="status-tag" :class="`st-${record.status}`">{{ statusLabel(record.status) }}</span>
        </template>
        <template v-else-if="column.key === 'counts'">
          <span class="count-cell" :class="{ ready: record.range_ready }">
            {{ record.n_values }} 值 / {{ record.n_reports }} 报告
          </span>
          <span v-if="record.range_ready" class="ready-badge">可发布</span>
        </template>
        <template v-else-if="column.key === 'decided'">
          <span v-if="record.decided_by" class="decided-cell">
            {{ record.decided_by }}
            <br />
            <small>{{ shortTime(record.decided_at) }}</small>
          </span>
          <span v-else class="count-cell">—</span>
        </template>
        <template v-else-if="column.key === 'actions'">
          <div class="row-actions">
            <template v-if="record.status === 'candidate'">
              <a @click="onPatch(record, 'approved')">入选</a>
              <a class="danger" @click="onPatch(record, 'rejected')">驳回</a>
            </template>
            <template v-else-if="record.status === 'approved'">
              <a @click="onPatch(record, 'candidate')">撤回</a>
            </template>
            <template v-else-if="record.status === 'rejected'">
              <a @click="onPatch(record, 'candidate')">恢复候选</a>
            </template>
            <template v-else-if="record.status === 'splitting'">
              <a class="primary" @click="openSplit(record)">拆分…</a>
              <a class="danger" @click="onPatch(record, 'rejected')">放弃拆分</a>
            </template>
            <a @click="openMentions(record)">提及</a>
          </div>
        </template>
      </template>
    </a-table>

    <!-- 拆分对话框：子口径定义 + 提及值逐条指派 -->
    <a-modal
      v-model:open="splitModal.open"
      :title="`拆分「${splitModal.entry?.caliber ?? ''}」`"
      :confirm-loading="splitModal.submitting"
      width="640px"
      @ok="onSplitSubmit"
    >
      <p class="split-tip">
        将原口径的提及值逐条指派到子口径；拆分后原口径转为「已驳回（已拆分）」，子口径直接入选且值集固化。
      </p>
      <div class="group-defs">
        <div v-for="(g, gi) in splitModal.groups" :key="gi" class="group-def">
          <a-input v-model:value="g.name" placeholder="子口径名（如：控制效率（甲））" />
          <a-button
            v-if="splitModal.groups.length > 1"
            type="text"
            danger
            size="small"
            @click="removeGroup(gi)"
          >
            删除
          </a-button>
        </div>
        <a-button type="dashed" size="small" @click="splitModal.groups.push({ name: '' })">+ 增加子口径</a-button>
      </div>
      <div class="assign-list">
        <div v-for="(m, mi) in splitModal.mentions" :key="mi" class="assign-row">
          <span class="assign-value">{{ m.value }} {{ m.unit }}</span>
          <span class="assign-rid" :title="m.rid">{{ m.rid }}</span>
          <a-select v-model:value="splitModal.assignment[mi]" size="small" style="width: 200px">
            <a-select-option v-for="(g, gi) in splitModal.groups" :key="gi" :value="gi">
              {{ gi + 1 }}. {{ g.name || `子口径 ${gi + 1}` }}
            </a-select-option>
          </a-select>
        </div>
        <p v-if="!splitModal.mentions.length" class="assign-empty">该口径在语料中无提及（无法拆分）</p>
      </div>
    </a-modal>

    <!-- 提及明细抽屉 -->
    <a-drawer v-model:open="mentionDrawer.open" :title="`提及明细 · ${mentionDrawer.entry?.caliber ?? ''}`" width="420">
      <p class="drawer-sub">
        {{ stageLabel(mentionDrawer.entry?.stage) }} · 首见单位 {{ mentionDrawer.entry?.unit || '—' }} ·
        语料实时 {{ mentionDrawer.mentions.length }} 处提及
      </p>
      <div class="mention-list">
        <div v-for="(m, i) in mentionDrawer.mentions" :key="i" class="mention-row">
          <span class="mention-value">{{ m.value }} {{ m.unit }}</span>
          <span class="mention-rid" :title="m.rid">{{ m.rid }}</span>
        </div>
      </div>
    </a-drawer>

    <!-- 导出物化结果 -->
    <a-modal v-model:open="exportResult.open" title="导出物化结果" :footer="null" width="560px">
      <p class="split-tip">
        已物化 <b>{{ exportResult.materialized }}</b> 条 →
        <code>references/overrides/curated_lexicon.json</code>（管线消费，重启或热重载后生效）；
        跳过 {{ exportResult.skipped?.length ?? 0 }} 条：
      </p>
      <div class="skip-list">
        <div v-for="(s, i) in exportResult.skipped" :key="i" class="skip-row">
          <span class="caliber-name">{{ s.caliber }}</span>
          <span class="skip-reason">{{ s.reason }}</span>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { RefreshCw } from '@lucide/vue'
import { eiaLexiconApi } from '@/apis/eia_lexicon_api'
import { useUserStore } from '@/stores/user'

const STAGES = [
  { key: 'planning_eia', label: '规划环评' },
  { key: 'post_eia', label: '事后环评' },
  { key: 'project_eia_openpit', label: '项目环评·露天' },
  { key: 'project_eia_underground', label: '项目环评·井工' },
  { key: 'tracking_eia', label: '跟踪评价' }
]

const STATUS_DEFS = [
  { key: 'candidate', label: '待确认' },
  { key: 'approved', label: '已入选' },
  { key: 'splitting', label: '待拆分' },
  { key: 'rejected', label: '已驳回' }
]

const CATEGORY_DEFS = [
  { key: 'measure', label: 'A 工程措施' },
  { key: 'site', label: 'B 站点背景' },
  { key: 'junk', label: 'C 待清理' }
]

const STAGE_LABELS = Object.fromEntries(STAGES.map((s) => [s.key, s.label]))
const CATEGORY_LABELS = Object.fromEntries(CATEGORY_DEFS.map((c) => [c.key, c.label]))
const STATUS_LABELS = Object.fromEntries(STATUS_DEFS.map((s) => [s.key, s.label]))

const userStore = useUserStore()
const loading = ref(false)
const importing = ref(false)
const exporting = ref(false)
const switchLoading = ref(false)
const items = ref([])
const total = ref(0)
const counts = ref({})
const filters = reactive({ status: '', category: '', stage: '', q: '' })
const switchState = reactive({ enabled: false, file: false })

const columns = [
  { title: '口径', key: 'caliber', ellipsis: true },
  { title: '阶段', key: 'stage', width: 110 },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 70 },
  { title: '分类', key: 'category', width: 100 },
  { title: '状态', key: 'status', width: 90 },
  { title: '语料计数', key: 'counts', width: 150 },
  { title: '决策', key: 'decided', width: 110 },
  { title: '操作', key: 'actions', width: 170 }
]

const stageLabel = (k) => STAGE_LABELS[k] || k
const categoryLabel = (k) => CATEGORY_LABELS[k] || k
const statusLabel = (k) => STATUS_LABELS[k] || k
const shortTime = (t) => (t ? String(t).replace('T', ' ').slice(0, 16) : '—')

const switchHint = computed(() => {
  if (!switchState.enabled) return '关闭：管线用内置词表'
  return switchState.file ? '开启：管线消费覆盖层' : '开启但文件缺失：待导出物化'
})

const fetchList = async () => {
  loading.value = true
  try {
    const data = await eiaLexiconApi.listEntries({
      status: filters.status,
      category: filters.category,
      stage: filters.stage,
      q: filters.q
    })
    items.value = data.items
    total.value = data.total
    counts.value = data.counts
  } catch (e) {
    message.error(e?.message || '词表加载失败')
  } finally {
    loading.value = false
  }
}

const fetchSwitches = async () => {
  try {
    const data = await eiaLexiconApi.getSwitches()
    const s = data.items?.[0]
    if (s) {
      switchState.enabled = s.enabled
      switchState.file = s.overrides_file
    }
  } catch {
    /* 开关态加载失败不打断主列表 */
  }
}

const onImport = async () => {
  importing.value = true
  try {
    const r = await eiaLexiconApi.importEntries()
    message.success(`重扫完成：扫描 ${r.scanned} 条，新增 ${r.added} 条`)
    await fetchList()
  } catch (e) {
    message.error(e?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

const onPatch = async (record, status) => {
  try {
    await eiaLexiconApi.updateEntry(record.id, { status })
    message.success(`「${record.caliber}」→ ${statusLabel(status)}`)
    await fetchList()
  } catch (e) {
    message.error(e?.message || '状态更新失败')
  }
}

// ── 拆分 ────────────────────────────────────────────────

const splitModal = reactive({ open: false, submitting: false, entry: null, groups: [], mentions: [], assignment: [] })

const openSplit = async (record) => {
  splitModal.entry = record
  splitModal.groups = [
    { name: `${record.caliber}（甲）` },
    { name: `${record.caliber}（乙）` }
  ]
  splitModal.mentions = []
  splitModal.assignment = []
  splitModal.open = true
  try {
    const data = await eiaLexiconApi.getMentions(record.id)
    splitModal.mentions = data.mentions
    splitModal.assignment = data.mentions.map(() => 0)
  } catch (e) {
    message.error(e?.message || '提及明细加载失败')
  }
}

const removeGroup = (gi) => {
  splitModal.groups.splice(gi, 1)
  splitModal.assignment = splitModal.assignment.map((a) => (a === gi ? 0 : a > gi ? a - 1 : a))
}

const onSplitSubmit = async () => {
  const names = splitModal.groups.map((g) => g.name.trim())
  if (names.some((n) => n.length < 2)) {
    message.warning('子口径名至少 2 个字')
    return
  }
  if (new Set(names).size !== names.length) {
    message.warning('子口径名不可重复')
    return
  }
  const items = splitModal.groups
    .map((g, gi) => ({
      caliber: g.name.trim(),
      values: splitModal.mentions
        .filter((_, mi) => splitModal.assignment[mi] === gi)
        .map((m) => ({ rid: m.rid, value: m.value }))
    }))
    .filter((it) => it.values.length > 0)
  if (!items.length) {
    message.warning('每个子口径至少指派一个提及值')
    return
  }
  if (items.length < names.length) {
    message.warning('存在未指派任何值的子口径，请删除或补充指派')
    return
  }
  splitModal.submitting = true
  try {
    const r = await eiaLexiconApi.splitEntry(splitModal.entry.id, items)
    message.success(`拆分完成：${r.children} 条子口径已入选`)
    splitModal.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '拆分失败')
  } finally {
    splitModal.submitting = false
  }
}

// ── 提及明细 ────────────────────────────────────────────

const mentionDrawer = reactive({ open: false, entry: null, mentions: [] })

const openMentions = async (record) => {
  mentionDrawer.entry = record
  mentionDrawer.mentions = []
  mentionDrawer.open = true
  try {
    const data = await eiaLexiconApi.getMentions(record.id)
    mentionDrawer.mentions = data.mentions
  } catch (e) {
    message.error(e?.message || '提及明细加载失败')
  }
}

// ── 导出物化与开关（admin） ─────────────────────────────

const exportResult = reactive({ open: false, materialized: 0, skipped: [] })

const onExport = () => {
  message.loading({ content: '正在物化…', key: 'lexicon-export', duration: 0 })
  eiaLexiconApi
    .exportOverrides()
    .then((r) => {
      message.success({ content: `物化 ${r.materialized} 条完成`, key: 'lexicon-export' })
      exportResult.materialized = r.materialized
      exportResult.skipped = r.skipped
      exportResult.open = true
      fetchSwitches()
    })
    .catch((e) => message.error({ content: e?.message || '导出失败', key: 'lexicon-export' }))
}

const onToggleSwitch = async (enabled) => {
  switchLoading.value = true
  try {
    const r = await eiaLexiconApi.setSwitch('curated_lexicon', enabled)
    switchState.enabled = r.switch.enabled
    switchState.file = r.switch.overrides_file
    message.success(enabled ? '覆盖层已开启' : '覆盖层已关闭（物化文件已删除，管线回内置词表）')
  } catch (e) {
    message.error(e?.message || '开关切换失败')
  } finally {
    switchLoading.value = false
  }
}

onMounted(() => {
  fetchList()
  fetchSwitches()
})
</script>

<style lang="less" scoped>
.lexicon-panel {
  --hairline: var(--gray-200);
}

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

.status-chips {
  :deep(.ant-radio-button-wrapper) {
    font-size: 12px;
  }
}

.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.switch-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  background: var(--main-0);
}

.switch-label {
  font-size: 12px;
  color: var(--gray-700);
}

.switch-hint {
  font-size: 12px;
  color: var(--gray-400);
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 表格单元格 ─────────────────────────────────────── */
.caliber-cell {
  display: flex;
  flex-direction: column;
  min-width: 0;

  .caliber-name {
    font-weight: 600;
    color: var(--gray-800);
  }

  .caliber-note {
    font-size: 12px;
    color: var(--gray-400);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.cat-tag,
.status-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
}

.cat-measure {
  color: var(--main-600);
  background: var(--main-0);
  border: 1px solid var(--main-600);
}

.cat-site {
  color: var(--gray-700);
  background: var(--gray-50);
  border: 1px solid var(--gray-300);
}

.cat-junk {
  color: var(--gray-400);
  background: var(--gray-50);
  border: 1px dashed var(--gray-300);
}

.st-candidate {
  color: var(--second-600);
  background: var(--main-0);
  border: 1px solid var(--second-600);
}

.st-approved {
  color: #fff;
  background: var(--main-600);
  border: 1px solid var(--main-600);
}

.st-rejected {
  color: var(--gray-500);
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
}

.st-splitting {
  color: #fff;
  background: var(--second-600);
  border: 1px solid var(--second-600);
}

.count-cell {
  font-variant-numeric: tabular-nums;
  color: var(--gray-600);

  &.ready {
    color: var(--main-600);
    font-weight: 600;
  }
}

.ready-badge {
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
  line-height: 18px;
  color: var(--main-600);
  border: 1px solid var(--main-600);
}

.decided-cell {
  font-size: 12px;
  color: var(--gray-600);

  small {
    color: var(--gray-400);
  }
}

.row-actions {
  display: flex;
  gap: 10px;

  a {
    font-size: 12px;
  }

  .primary {
    color: var(--main-600);
    font-weight: 600;
  }

  .danger {
    color: var(--second-600);
  }
}

/* ── 拆分对话框 ─────────────────────────────────────── */
.split-tip {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--gray-500);

  b {
    color: var(--main-600);
  }

  code {
    font-size: 11px;
    color: var(--gray-600);
  }
}

.group-defs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;

  .group-def {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.assign-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--hairline);
  border-radius: 6px;
}

.assign-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;

  & + & {
    border-top: 1px solid var(--gray-100);
  }

  .assign-value {
    flex: none;
    min-width: 90px;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    color: var(--gray-800);
  }

  .assign-rid {
    flex: 1;
    font-size: 11px;
    color: var(--gray-400);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.assign-empty {
  padding: 16px;
  margin: 0;
  text-align: center;
  font-size: 12px;
  color: var(--gray-400);
}

/* ── 提及抽屉与导出结果 ─────────────────────────────── */
.drawer-sub {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--gray-500);
}

.mention-list,
.skip-list {
  border: 1px solid var(--hairline);
  border-radius: 6px;
}

.mention-row,
.skip-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;

  & + & {
    border-top: 1px solid var(--gray-100);
  }
}

.mention-value {
  flex: none;
  min-width: 90px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--gray-800);
}

.mention-rid {
  flex: 1;
  font-size: 11px;
  color: var(--gray-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skip-reason {
  flex: 1;
  font-size: 12px;
  color: var(--gray-500);
}
</style>
