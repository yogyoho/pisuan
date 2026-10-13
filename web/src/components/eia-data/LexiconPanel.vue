<template>
  <div class="ewp lexicon-panel">
    <!-- 页头（原型 s9：BookOpen + 可物化 pill + 导出物化；覆盖层开关为真实运营件，s9 无对应物） -->
    <div class="page-head">
      <div class="ph-icon">
        <BookOpen :size="18" />
      </div>
      <div>
        <h2>数值护栏词表</h2>
        <div class="ph-sub">lexicon · 写手数值护栏（指标识别 / 单位量纲 / 禁算词）的权威清单</div>
      </div>
      <div class="ph-actions">
        <span v-if="counts.approved" class="pill pill-orange"
          ><span class="dot dot-warn"></span>{{ counts.approved }} 项已入选</span
        >
        <template v-if="userStore.isAdmin">
          <span class="switch-box" :title="switchHint">
            <span class="switch-label">覆盖层</span>
            <a-switch
              :checked="switchState.enabled"
              :loading="switchLoading"
              size="small"
              @change="(v) => onToggleSwitch(v)"
            />
          </span>
          <button class="btn btn-pri btn-sm" :disabled="exporting" @click="onExport">
            <Download :size="14" />{{ exporting ? '导出中…' : '导出物化' }}
          </button>
        </template>
        <span v-else class="pill pill-gray" :title="switchHint">{{ switchHint }}</span>
      </div>
    </div>

    <a-spin v-if="loading && !items.length" style="display: block; margin: 48px auto" />
    <template v-else-if="items.length || isFiltered">
      <div class="split">
        <!-- 左：状态分组（真实数据无「域」维度，状态即运营主轴） -->
        <div class="card fam-list">
          <div class="fam-search">
            <a-input-search
              v-model:value="filters.q"
              placeholder="搜索口径…"
              allow-clear
              @search="fetchList"
            />
          </div>
          <div
            v-for="g in statusGroups"
            :key="g.key"
            class="fam-item"
            :class="{ on: filters.status === g.key }"
            @click="setStatus(g.key)"
          >
            <span v-if="g.key === 'splitting' && g.count" class="mini-dot"></span>
            <span class="fam-name">{{ g.label }}</span>
            <span class="fam-cnt num">{{ g.count }} 词条</span>
          </div>
          <!-- 分类/阶段两维为真实数据特有，收在左列底部（样本下拉同款数据驱动必要） -->
          <div class="fam-filters">
            <a-select v-model:value="filters.category" style="width: 100%" @change="fetchList">
              <a-select-option value="">全部分类</a-select-option>
              <a-select-option v-for="c in CATEGORY_DEFS" :key="c.key" :value="c.key">{{
                c.label
              }}</a-select-option>
            </a-select>
            <a-select v-model:value="filters.stage" style="width: 100%" @change="fetchList">
              <a-select-option value="">全部阶段</a-select-option>
              <a-select-option v-for="s in STAGES" :key="s.key" :value="s.key">{{
                s.label
              }}</a-select-option>
            </a-select>
          </div>
        </div>

        <!-- 右：当前状态词条表 -->
        <div>
          <div class="card">
            <div class="card-hd">
              <h3>{{ activeGroupLabel }}</h3>
              <span class="hd-sub"
                >{{ total }} 词条 · 可发布 {{ readyCount }} · A {{ catCounts.measure }} · B
                {{ catCounts.site }} · C {{ catCounts.junk }}</span
              >
              <div class="hd-right">
                <button class="btn btn-sec btn-sm" :disabled="importing" @click="onImport">
                  <RefreshCw :size="14" />{{ importing ? '扫描中…' : '重扫语料导入' }}
                </button>
              </div>
            </div>
            <table class="tbl" :style="loading && items.length ? 'opacity: .55' : ''">
              <thead>
                <tr>
                  <th style="width: 19%">口径</th>
                  <th style="width: 9%">阶段</th>
                  <th style="width: 6%">单位</th>
                  <th style="width: 9%">分类</th>
                  <th style="width: 8%">状态</th>
                  <th class="r" style="width: 12%">语料计数</th>
                  <th style="width: 13%">来源</th>
                  <th class="r" style="width: 24%; padding-right: 20px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="record in pagedItems" :key="record.id">
                  <td>
                    <div class="caliber-cell">
                      <span class="caliber-name" :title="record.caliber">{{ record.caliber }}</span>
                      <span v-if="record.note" class="caliber-note" :title="record.note">{{
                        record.note
                      }}</span>
                    </div>
                  </td>
                  <td>{{ stageLabel(record.stage) }}</td>
                  <td class="mono">
                    <template v-if="record.unit">{{ record.unit }}</template>
                    <template v-else>
                      <span class="missing-unit">缺单位</span>
                    </template>
                  </td>
                  <td>
                    <span class="pill pill-gray pill-sm">{{ categoryLabel(record.category) }}</span>
                  </td>
                  <td>
                    <span class="pill pill-sm" :class="statusPillClass(record.status)">{{
                      statusLabel(record.status)
                    }}</span>
                  </td>
                  <td class="r num">
                    <span class="count-cell" :class="{ ready: record.range_ready }"
                      >{{ record.n_values }} 值 / {{ record.n_reports }} 报告</span
                    >
                    <span
                      v-if="record.range_ready"
                      class="pill pill-ok pill-sm"
                      style="margin-left: 6px"
                      >可发布</span
                    >
                  </td>
                  <td>
                    <span
                      class="field-src db"
                      :title="record.decided_at ? `裁决于 ${record.decided_at}` : '导入预置'"
                      >DB · {{ record.decided_by || '导入' }}</span
                    >
                  </td>
                  <td class="r" style="padding-right: 20px; white-space: nowrap">
                    <template v-if="record.status === 'candidate'">
                      <button class="btn btn-txt btn-sm" @click="onPatch(record, 'approved')">
                        入选
                      </button>
                      <button
                        class="btn btn-txt btn-sm withdraw-btn"
                        @click="onPatch(record, 'rejected')"
                      >
                        驳回
                      </button>
                    </template>
                    <template v-else-if="record.status === 'approved'">
                      <button class="btn btn-txt btn-sm" @click="onPatch(record, 'candidate')">
                        撤回
                      </button>
                    </template>
                    <template v-else-if="record.status === 'rejected'">
                      <button class="btn btn-txt btn-sm" @click="onPatch(record, 'candidate')">
                        恢复候选
                      </button>
                    </template>
                    <template v-else-if="record.status === 'splitting'">
                      <button class="btn btn-pri btn-sm" @click="openSplit(record)">拆分…</button>
                      <button
                        class="btn btn-txt btn-sm withdraw-btn"
                        @click="onPatch(record, 'rejected')"
                      >
                        放弃
                      </button>
                    </template>
                    <button
                      v-if="record.status !== 'splitting'"
                      class="btn btn-txt btn-sm"
                      @click="openRename(record)"
                    >
                      改名
                    </button>
                    <button class="btn btn-txt btn-sm" @click="openMentions(record)">提及</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="tbl-foot">
              <span
                >共 {{ total }} 条 · 语料计数实时现扫非快照 ·
                区间护栏达报告数门槛即可发布（P5/P50/P95 语义取自 bank_compile）</span
              >
              <span v-if="pageCount > 1" class="pager">
                <button class="btn btn-sm" :disabled="page <= 1" @click="page--">上一页</button>
                <span class="num">{{ page }} / {{ pageCount }}</span>
                <button class="btn btn-sm" :disabled="page >= pageCount" @click="page++">
                  下一页
                </button>
              </span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 空态：区分「库空未导入」与「筛选无匹配」，前者给一键导入 CTA -->
    <div v-else-if="!loading" class="card">
      <div class="empty-state">
        <a-empty :description="emptyDesc">
          <button
            v-if="!isFiltered"
            class="btn btn-pri btn-sm"
            :disabled="importing"
            @click="onImport"
          >
            <RefreshCw :size="14" />重扫语料导入
          </button>
          <button v-else class="btn btn-sec btn-sm" @click="clearFilters">清除筛选</button>
        </a-empty>
        <p v-if="!isFiltered" class="empty-hint">
          词表数据存于平台库，首次使用需从 coal-eia-writer
          技能语料扫描导入候选口径；导入幂等，重复执行只补新增、绝不覆盖人工决策。
        </p>
      </div>
    </div>

    <div class="note-bar">
      <Info :size="14" />
      <span>
        导出物化仅合并已入选条目到 references/overrides/curated_lexicon.json（range
        一律现算）；改名旧口径自动进抑制清单，重扫语料不再复活；覆盖层开关关闭即删文件，管线回内置词表。
      </span>
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
        <a-button type="dashed" size="small" @click="splitModal.groups.push({ name: '' })"
          >+ 增加子口径</a-button
        >
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
        <p v-if="!splitModal.mentions.length" class="assign-empty">
          该口径在语料中无提及（无法拆分）
        </p>
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
          {{ renameModal.entry?.n_values }} 值 / {{ renameModal.entry?.n_reports }} 报告 ·
          {{ renameModal.entry?.unit }}
        </span>
      </div>
      <p class="rename-ctx-title">
        语料语境（高亮为扫描命中）
        <a-tag v-if="renameModal.source === 'old_fingerprint'" color="orange"
          >旧口径语境：新名在语料中零命中</a-tag
        >
        <span v-if="renameModal.ctxError" class="ctx-error">{{ renameModal.ctxError }}</span>
      </p>
      <div class="assign-list rename-ctx">
        <a-spin v-if="renameModal.loadingCtx" size="small" class="ctx-spin" />
        <template v-else>
          <div v-for="(m, i) in renameModal.mentions" :key="i" class="ctx-row">
            <span class="ctx-text"
              >{{ m.before }}<mark>{{ m.hit }}</mark
              >{{ m.after }}</span
            >
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
          新名若非语料逐字出现，语料计数将归
          0、导出物化永久跳过（机制必然）；旧口径名自动进入抑制清单，重扫语料不会复活。
        </span>
      </div>
    </a-modal>

    <!-- 提及明细抽屉 -->
    <a-drawer
      v-model:open="mentionDrawer.open"
      :title="`提及明细 · ${mentionDrawer.entry?.caliber ?? ''}`"
      width="420"
    >
      <p class="drawer-sub">
        {{ stageLabel(mentionDrawer.entry?.stage) }} · 首见单位
        {{ mentionDrawer.entry?.unit || '—' }} · 语料实时 {{ mentionDrawer.mentions.length }} 处提及
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
import { BookOpen, Download, Info, Pencil, RefreshCw } from '@lucide/vue'
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

const STATUS_PILL_CLASS = {
  candidate: 'pill-warn',
  approved: 'pill-ok',
  splitting: 'pill-orange',
  rejected: 'pill-gray'
}

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
const page = ref(1)
const PAGE_SIZE = 20

const stageLabel = (k) => STAGE_LABELS[k] || k
const categoryLabel = (k) => CATEGORY_LABELS[k] || k
const statusLabel = (k) => STATUS_LABELS[k] || k
const statusPillClass = (k) => STATUS_PILL_CLASS[k] || 'pill-gray'

// 左列状态分组：counts 为全量状态分布（服务端口径），全部 = 四态合计
const grandTotal = computed(() => Object.values(counts.value).reduce((acc, n) => acc + n, 0))

const statusGroups = computed(() => [
  { key: '', label: '全部口径', count: grandTotal.value },
  ...STATUS_DEFS.map((s) => ({ key: s.key, label: s.label, count: counts.value[s.key] ?? 0 }))
])

const activeGroupLabel = computed(
  () => statusGroups.value.find((g) => g.key === filters.status)?.label ?? '全部口径'
)

const readyCount = computed(() => items.value.filter((it) => it.range_ready).length)

const catCounts = computed(() => {
  const acc = { measure: 0, site: 0, junk: 0 }
  for (const it of items.value) acc[it.category] = (acc[it.category] ?? 0) + 1
  return acc
})

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const pagedItems = computed(() =>
  items.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE)
)

const setStatus = (key) => {
  filters.status = key
  page.value = 1
  fetchList()
}

const switchHint = computed(() => {
  if (!switchState.enabled) return '关闭：管线用内置词表'
  return switchState.file ? '开启：管线消费覆盖层' : '开启但文件缺失：待导出物化'
})

const isFiltered = computed(() =>
  Boolean(filters.status || filters.category || filters.stage || filters.q)
)
const emptyDesc = computed(() =>
  isFiltered.value ? '当前筛选无匹配条目' : '词表为空：尚未从语料扫描导入候选口径'
)

const clearFilters = () => {
  filters.status = ''
  filters.category = ''
  filters.stage = ''
  filters.q = ''
  page.value = 1
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
    // 筛选/变更后列表可能缩水，页码越界会切出空表——钳回有效范围
    if (page.value > pageCount.value) page.value = pageCount.value
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

const splitModal = reactive({
  open: false,
  submitting: false,
  entry: null,
  groups: [],
  mentions: [],
  assignment: []
})

const openSplit = async (record) => {
  splitModal.entry = record
  splitModal.groups = [{ name: `${record.caliber}（甲）` }, { name: `${record.caliber}（乙）` }]
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
      (it) =>
        it.id !== entry.id &&
        it.stage === entry.stage &&
        it.unit === entry.unit &&
        it.caliber === newName
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
      message.success({
        content: `物化 ${r.materialized} 条完成（落运行栈技能目录，需人工回流 pisuan-custom）`,
        key: 'lexicon-export'
      })
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
.withdraw-btn {
  color: var(--second-600);

  &:hover {
    background: var(--second-50);
  }
}

.switch-box {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--gray-200);
  border-radius: 999px;
  background: var(--main-0);
}

.switch-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}

/* 左列底部的分类/阶段过滤（真实数据维度，原型无对应物） */
.fam-filters {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 14px 14px;
  border-top: 1px dashed var(--gray-100);
}

.missing-unit {
  color: var(--second-600);
  font-size: 12px;
}

.pager {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

/* 语料口径名是长句片段，auto 布局下 nowrap 最小内容宽会撑爆表格——固定布局 + 换行 */
.lexicon-panel .tbl {
  table-layout: fixed;
  width: 100%;

  td {
    overflow-wrap: break-word;
  }
}

/* ── 表格单元格 ─────────────────────────────────────── */
.caliber-cell {
  display: flex;
  flex-direction: column;
  min-width: 0;

  .caliber-name {
    font-weight: 500;
    color: var(--color-text);
  }

  .caliber-note {
    font-size: 12px;
    color: var(--color-text-tertiary);
  }
}

.count-cell {
  color: var(--color-text-tertiary);

  &.ready {
    color: var(--main-600);
  }
}

.empty-hint {
  max-width: 460px;
  margin: 12px auto 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

/* ── 弹窗内部 ───────────────────────────────────────── */
.cat-tag,
.status-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
}

.cat-tag {
  white-space: nowrap;
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

.split-tip {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.group-defs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;

  .group-def {
    display: flex;
    gap: 8px;
    align-items: center;
  }
}

.assign-list {
  max-height: 320px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;

  .assign-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .assign-value {
    min-width: 88px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }

  .assign-rid,
  .ctx-rid {
    flex: 1;
    font-size: 12px;
    color: var(--color-text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .assign-empty {
    margin: 8px 0;
    font-size: 12px;
    color: var(--color-text-tertiary);
  }
}

.rename-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;

  .caliber-name {
    font-weight: 600;
  }
}

.rename-ctx-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--color-text-secondary);

  .ctx-error {
    font-size: 12px;
    color: var(--second-600);
  }
}

.rename-ctx {
  .ctx-spin {
    display: block;
    margin: 24px auto;
  }

  .ctx-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 6px 8px;
    border-radius: 6px;
    background: var(--main-0);

    .ctx-text {
      flex: 2;
      font-size: 12px;
      line-height: 1.6;

      mark {
        background: var(--main-100);
        color: var(--main-700);
        padding: 0 2px;
        border-radius: 2px;
      }
    }

    .ctx-value {
      min-width: 88px;
      font-weight: 500;
      font-variant-numeric: tabular-nums;
    }
  }
}

.rename-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.rename-warn {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--second-50);
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.drawer-sub {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.mention-list {
  display: flex;
  flex-direction: column;
  gap: 6px;

  .mention-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 6px 8px;
    border-radius: 6px;
    background: var(--main-0);

    .mention-value {
      min-width: 88px;
      font-weight: 500;
      font-variant-numeric: tabular-nums;
    }

    .mention-rid {
      flex: 1;
      font-size: 12px;
      color: var(--color-text-tertiary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}

.skip-list {
  max-height: 260px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;

  .skip-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;

    .caliber-name {
      font-weight: 500;
    }

    .skip-reason {
      font-size: 12px;
      color: var(--color-text-tertiary);
    }
  }
}
</style>

<style lang="less" src="./factory-ui.less"></style>
