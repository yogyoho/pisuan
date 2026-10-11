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
      v-if="items.length"
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
            <a v-if="record.status !== 'splitting'" @click="openRename(record)">改名</a>
            <a @click="openMentions(record)">提及</a>
          </div>
        </template>
      </template>
    </a-table>

    <!-- 空态：区分「库空未导入」与「筛选无匹配」，前者给一键导入 CTA -->
    <div v-else-if="!loading" class="empty-state">
      <a-empty :description="emptyDesc">
        <a-button v-if="!isFiltered" type="primary" :loading="importing" @click="onImport">
          <RefreshCw :size="14" style="margin-right: 4px" />重扫语料导入
        </a-button>
        <a-button v-else @click="clearFilters">清除筛选</a-button>
      </a-empty>
      <p v-if="!isFiltered" class="empty-hint">
        词表数据存于平台库，首次使用需从 coal-eia-writer 技能语料扫描导入候选口径；导入幂等，重复执行只补新增、绝不覆盖人工决策。
      </p>
    </div>

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

    <!-- 改名对话框：语料语境三段高亮 + 人工修正口径名（旧指纹自动入抑制清单） -->
    <a-modal
      v-model:open="renameModal.open"
      :title="`改名 · ${renameModal.entry?.caliber ?? ''}`"
      :confirm-loading="renameModal.submitting"
      width="680px"
      @ok="onRenameSubmit"
    >
      <div class="rename-summary">
        <span class="caliber-name">{{ renameModal.entry?.caliber }}</span>
        <span class="cat-tag" :class="`cat-${renameModal.entry?.category}`">
          {{ categoryLabel(renameModal.entry?.category) }}
        </span>
        <span class="status-tag" :class="`st-${renameModal.entry?.status}`">
          {{ statusLabel(renameModal.entry?.status) }}
        </span>
        <span class="count-cell">
          {{ renameModal.entry?.n_values }} 值 / {{ renameModal.entry?.n_reports }} 报告 · {{ renameModal.entry?.unit }}
        </span>
      </div>
      <p class="rename-ctx-title">
        语料语境（高亮为扫描命中）
        <a-tag v-if="renameModal.source === 'old_fingerprint'" color="orange">旧口径语境：新名在语料中零命中</a-tag>
        <span v-if="renameModal.ctxError" class="ctx-error">{{ renameModal.ctxError }}</span>
      </p>
      <div class="assign-list rename-ctx">
        <a-spin v-if="renameModal.loadingCtx" size="small" class="ctx-spin" />
        <template v-else>
          <div v-for="(m, i) in renameModal.mentions" :key="i" class="ctx-row">
            <span class="ctx-text">{{ m.before }}<mark>{{ m.hit }}</mark>{{ m.after }}</span>
            <span class="ctx-value">{{ m.value }} {{ m.unit }}</span>
            <span class="ctx-rid" :title="m.rid">{{ m.rid }}</span>
          </div>
          <p v-if="!renameModal.mentions.length && !renameModal.ctxError" class="assign-empty">
            该口径在语料中无提及
          </p>
        </template>
      </div>
      <div class="rename-form">
        <a-input v-model:value="renameModal.caliber" placeholder="新口径名（至少 2 个字）" />
        <a-input v-model:value="renameModal.note" placeholder="备注（可选）" />
      </div>
      <div class="rename-warn">
        <Pencil :size="14" style="flex: none; margin-top: 3px" />
        <span>
          新名若非语料逐字出现，语料计数将归 0、导出物化永久跳过（机制必然）；旧口径名自动进入抑制清单，重扫语料不会复活。
        </span>
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
import { Pencil, RefreshCw } from '@lucide/vue'
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
  { key: 'measure', label: 'A 措施效率' },
  { key: 'site', label: 'B 现状监测' },
  { key: 'junk', label: 'C 非护栏杂项' }
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
  { title: '口径', key: 'caliber', width: 300, ellipsis: true },
  { title: '阶段', key: 'stage', width: 110 },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 70 },
  { title: '分类', key: 'category', width: 100 },
  { title: '状态', key: 'status', width: 90 },
  { title: '语料计数', key: 'counts', width: 150 },
  { title: '操作', key: 'actions' }
]

const stageLabel = (k) => STAGE_LABELS[k] || k
const categoryLabel = (k) => CATEGORY_LABELS[k] || k
const statusLabel = (k) => STATUS_LABELS[k] || k

const switchHint = computed(() => {
  if (!switchState.enabled) return '关闭：管线用内置词表'
  return switchState.file ? '开启：管线消费覆盖层' : '开启但文件缺失：待导出物化'
})

const isFiltered = computed(() => Boolean(filters.status || filters.category || filters.stage || filters.q))
const emptyDesc = computed(() => (isFiltered.value ? '当前筛选无匹配条目' : '词表为空：尚未从语料扫描导入候选口径'))

const clearFilters = () => {
  filters.status = ''
  filters.category = ''
  filters.stage = ''
  filters.q = ''
  fetchList()
}

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
    const suppressed = r.blocklist_skipped ? `，抑制 ${r.blocklist_skipped} 条` : ''
    message.success(`重扫完成：扫描 ${r.scanned} 条，新增 ${r.added} 条${suppressed}`)
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

// ── 改名 ────────────────────────────────────────────────

const renameModal = reactive({
  open: false,
  submitting: false,
  loadingCtx: false,
  entry: null,
  caliber: '',
  note: '',
  mentions: [],
  source: 'current',
  ctxError: ''
})

const openRename = (record) => {
  renameModal.entry = record
  renameModal.caliber = record.caliber
  renameModal.note = record.note || ''
  renameModal.mentions = []
  renameModal.source = 'current'
  renameModal.ctxError = ''
  renameModal.open = true
  renameModal.loadingCtx = true
  eiaLexiconApi
    .getMentions(record.id)
    .then((data) => {
      renameModal.mentions = data.mentions
      renameModal.source = data.source || 'current'
    })
    .catch(() => {
      // 语境加载失败仅内联提示，不阻断改名提交主链路
      renameModal.ctxError = '语境加载失败（不影响提交）'
    })
    .finally(() => {
      renameModal.loadingCtx = false
    })
}

const onRenameSubmit = async () => {
  const entry = renameModal.entry
  const newName = renameModal.caliber.trim()
  if (newName.length < 2) {
    message.warning('口径名至少 2 个字')
    return
  }
  if (newName !== entry.caliber) {
    // 客户端重名预检（列表可能被筛选，后端 ValueError 仍兜底）
    const clash = items.value.find(
      (it) => it.id !== entry.id && it.stage === entry.stage && it.unit === entry.unit && it.caliber === newName
    )
    if (clash) {
      message.warning(`口径已存在：${stageLabel(entry.stage)} / ${newName} / ${entry.unit}`)
      return
    }
  }
  renameModal.submitting = true
  try {
    await eiaLexiconApi.updateEntry(entry.id, { caliber: newName, note: renameModal.note.trim() })
    message.success(`已改名：${entry.caliber} → ${newName}`)
    renameModal.open = false
    await fetchList()
  } catch (e) {
    message.error(e?.message || '改名失败')
  } finally {
    renameModal.submitting = false
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

.empty-state {
  padding: 48px 0;
  background: var(--main-0);
  border: 1px solid var(--hairline);
  border-radius: 6px;
  text-align: center;
}

.empty-hint {
  max-width: 460px;
  margin: 12px auto 0;
  font-size: 12px;
  color: var(--gray-400);
  line-height: 1.6;
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
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
    word-break: break-all;
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

/* ── 改名对话框 ─────────────────────────────────────── */
.rename-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.rename-ctx-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-600);
}

.ctx-error {
  font-weight: 400;
  color: var(--second-600);
}

.rename-ctx {
  margin-bottom: 12px;

  .ctx-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 6px 10px;

    & + .ctx-row {
      border-top: 1px solid var(--gray-100);
    }
  }

  .ctx-text {
    flex: 1;
    min-width: 0;
    font-size: 12px;
    line-height: 1.7;
    color: var(--gray-700);
    word-break: break-all;

    mark {
      padding: 0 2px;
      border-radius: 2px;
      background: var(--second-100);
      color: var(--second-900);
    }
  }

  .ctx-value {
    flex: none;
    min-width: 80px;
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    font-size: 12px;
    color: var(--gray-800);
  }

  .ctx-rid {
    flex: none;
    max-width: 140px;
    font-size: 11px;
    color: var(--gray-400);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ctx-spin {
    display: block;
    padding: 16px;
    text-align: center;
  }
}

.rename-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.rename-warn {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--second-50);
  color: var(--second-900);
  font-size: 12px;
  line-height: 1.6;
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
