<template>
  <div class="sections-panel">
    <!-- 双 tab：节级明细（只读）/ 字段维护（编辑 + 导出物化） -->
    <div class="tab-bar">
      <div class="seg">
        <button :class="{ on: activeTab === 'detail' }" @click="activeTab = 'detail'">
          节级明细
        </button>
        <button :class="{ on: activeTab === 'fields' }" @click="switchToFields">字段维护</button>
      </div>
      <span class="tab-hint">
        {{
          activeTab === 'detail'
            ? 'bank_compile 生成物 · 页面零写通道'
            : '专家裁决落 DB · 导出物化回写 stages/*.json'
        }}
      </span>
    </div>

    <!-- ═══ Tab 1：节级明细（只读）═══ -->
    <template v-if="activeTab === 'detail'">
      <div class="card">
        <div class="toolbar">
          <a-radio-group v-model:value="detailStage" button-style="solid" @change="fetchSections">
            <a-radio-button v-for="s in STAGES" :key="s.key" :value="s.key">{{
              s.label
            }}</a-radio-button>
          </a-radio-group>
          <span style="flex: 1"></span>
          <span class="muted-chip"
            >仅看未归并 <b>{{ unmapped.length }}</b></span
          >
        </div>

        <div class="metric-strip">
          <div class="metric-cell">
            <span class="metric-label">口径总条目</span>
            <span class="metric-value">{{ detailMetrics.total }}</span>
          </div>
          <div class="metric-cell">
            <span class="metric-label">覆盖章节</span>
            <span class="metric-value">{{ detailMetrics.titledSections }}<small>节</small></span>
          </div>
          <div class="metric-cell" :class="{ warn: unmapped.length > 0 }">
            <span class="metric-label">未归并 unmapped</span>
            <span class="metric-value">{{ unmapped.length }}</span>
          </div>
        </div>

        <a-table
          v-if="sectionRows.length"
          :data-source="sectionRows"
          :columns="detailColumns"
          :loading="loading"
          :pagination="{ pageSize: 50, showTotal: (t) => `共 ${t} 条` }"
          size="middle"
          row-key="rowKey"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'section'">
              <span class="mono">{{ record.sectionLabel }}</span>
            </template>
            <template v-else-if="column.key === 'tier'">
              <span class="tier" :class="`tier-${tierRank(record.tier)}`">{{
                tierLabel(record.tier)
              }}</span>
            </template>
            <template v-else-if="column.key === 'corpus_freq'">
              <span class="num">{{
                record.corpus_freq != null ? `${Math.round(record.corpus_freq * 100)}%` : '—'
              }}</span>
            </template>
          </template>
        </a-table>
        <div v-else-if="!loading" class="empty-state">
          <a-empty description="该阶段暂无节级口径数据" />
        </div>

        <!-- 未归并口径：独立清单（P1-3 unmapped 抽屉的数据真源，此处只读浏览） -->
        <template v-if="unmapped.length">
          <div class="unmapped-block">
            <div class="block-hd">
              <h4>未归并口径</h4>
              <span class="hd-sub"
                >forms_label_map 未命中的量词短语 → 在「字段维护」补字段后重跑 bank_compile
                归并</span
              >
            </div>
            <a-table
              :data-source="unmapped"
              :columns="unmappedColumns"
              :pagination="{ pageSize: 10, hideOnSinglePage: true }"
              size="small"
              row-key="(r) => [r.section, r.caliber, r.value].join('|')"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'section'">
                  <span class="mono">{{ record.section }}</span>
                </template>
              </template>
            </a-table>
          </div>
        </template>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          只读边界：本页数据为 bank_compile
          生成物，页面零写通道；专家加工动作全部收敛在「字段维护」tab。
        </span>
      </div>
    </template>

    <!-- ═══ Tab 2：字段维护（编辑 + 导出）═══ -->
    <template v-else>
      <div class="card toolbar-card">
        <div class="toolbar">
          <span class="toolbar-label">阶段</span>
          <a-select v-model:value="fieldsStage" style="width: 180px" @change="fetchForms">
            <a-select-option v-for="s in STAGES" :key="s.key" :value="s.key">{{
              s.label
            }}</a-select-option>
          </a-select>
          <span style="flex: 1"></span>
          <span v-if="pendingCount" class="pill-warn-tag">
            <span class="dot"></span>{{ pendingCount }} 项待导出
          </span>
          <a-button @click="openAddModal"
            ><Plus :size="14" style="margin-right: 4px" />添加字段</a-button
          >
          <a-button
            v-if="userStore.isAdmin"
            type="primary"
            :disabled="!pendingCount"
            :loading="exporting"
            @click="onExport"
          >
            导出物化
          </a-button>
        </div>
      </div>

      <div class="split">
        <!-- 左：口径族列表 -->
        <div class="card fam-list">
          <div class="fam-search">
            <a-input-search v-model:value="famQuery" placeholder="搜索口径族…" allow-clear />
          </div>
          <div
            v-for="f in filteredFamilies"
            :key="f.key"
            class="fam-item"
            :class="{ on: f.key === activeFamily }"
            @click="activeFamily = f.key"
          >
            <span v-if="f.pending" class="mini-dot"></span>
            <span class="fam-name" :title="f.label">{{ f.label }}</span>
            <span class="fam-key mono">{{ f.key }}</span>
            <span class="fam-cnt">{{ f.fields.length }} 字段</span>
          </div>
          <div v-if="!filteredFamilies.length" class="empty-state">
            <a-empty description="无匹配口径族" />
          </div>
        </div>

        <!-- 右：字段表 -->
        <div class="card">
          <template v-if="activeFamilyDetail">
            <div class="fam-hd">
              <h3>
                {{ activeFamilyDetail.label }} <code class="k">{{ activeFamily }}</code>
              </h3>
              <span class="hd-sub">
                {{ fieldsStage }} · {{ activeFamilyDetail.fields.length }} 个字段
                <template v-if="activeFamilyDetail.chapters?.length">
                  · 挂载 {{ activeFamilyDetail.chapters.join('、') }}
                </template>
              </span>
              <span class="hd-right">
                <span class="pill-tag">文件锚点 {{ fileFieldCount }}</span>
                <span v-if="dbFieldCount" class="pill-tag main">DB 裁决 {{ dbFieldCount }}</span>
              </span>
            </div>
            <a-table
              :data-source="activeFamilyDetail.fields"
              :columns="fieldColumns"
              :pagination="false"
              size="middle"
              row-key="name"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'name'">
                  <span class="mono">{{ record.name }}</span>
                  <span v-if="isPendingAdd(record)" class="pill-mini warn">新增 · 未导出</span>
                </template>
                <template v-else-if="column.key === 'label'">
                  {{ record.label }}
                  <span v-if="isPendingAmend(record)" class="pill-mini warn">修改 · 未导出</span>
                  <div v-if="isPendingAmend(record) && record.db_edit" class="amend-preview">
                    → {{ record.db_edit.field.label ?? record.label }}
                  </div>
                </template>
                <template v-else-if="column.key === 'type'">
                  <span class="pill-mini">{{ record.type }}</span>
                </template>
                <template v-else-if="column.key === 'required'">
                  <Check v-if="record.required" class="req-ic yes" :size="14" />
                  <span v-else class="muted">选填</span>
                </template>
                <template v-else-if="column.key === 'source'">
                  <span v-if="record.source === 'db'" class="field-src db"
                    >DB · {{ record.decided_by }}</span
                  >
                  <span v-else class="field-src file">文件锚点</span>
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a class="primary" @click="openAmendModal(record)">改 label…</a>
                  <a v-if="isPendingAdd(record)" class="danger" @click="onWithdraw(record)">撤回</a>
                </template>
              </template>
            </a-table>
            <div class="tbl-foot">
              禁删字段、禁改字段标识（name）——下游
              <code class="k">{{ slotNotation }}</code>
              寻址与一致性合约依赖其稳定；删除需走工程侧评审
            </div>
          </template>
          <div v-else class="empty-state"><a-empty description="选择左侧口径族查看字段" /></div>
        </div>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          导出物化按文本级插接写回 stages/*.json（字节纪律，幂等）；文件落运行栈技能目录，需人工回流
          pisuan-custom 仓库，重跑 bank_compile 后节级明细生效。
        </span>
      </div>
    </template>

    <!-- 添加字段弹窗 -->
    <a-modal
      v-model:open="addModal.open"
      title="添加口径字段"
      :confirm-loading="addModal.saving"
      @ok="submitAdd"
    >
      <div class="frm-row">
        <label>字段标识（name）<span class="must">*</span></label>
        <a-input v-model:value="addModal.form.name" placeholder="snake_case，导出后不可修改" />
        <div class="frm-help">小写字母开头的 snake_case；下游 SLOT 寻址依赖，落库后禁改</div>
      </div>
      <div class="frm-row">
        <label>中文名称（label）<span class="must">*</span></label>
        <a-input v-model:value="addModal.form.label" />
      </div>
      <div class="frm-row">
        <label>类型<span class="must">*</span></label>
        <a-select v-model:value="addModal.form.type" style="width: 100%">
          <a-select-option value="string">string</a-select-option>
          <a-select-option value="number">number</a-select-option>
          <a-select-option value="int">int</a-select-option>
          <a-select-option value="bool">bool</a-select-option>
          <a-select-option value="enum:">enum: 自定义枚举</a-select-option>
        </a-select>
        <a-input
          v-if="addModal.form.type === 'enum:'"
          v-model:value="addModal.form.enumBody"
          style="margin-top: 6px"
          placeholder="枚举体，如 规划环评|项目环评"
        />
      </div>
      <div class="frm-row inline">
        <div>
          <label>必填</label>
          <a-switch v-model:checked="addModal.form.required" />
        </div>
        <div style="flex: 1">
          <label>单位（选填）</label>
          <a-input v-model:value="addModal.form.unit" placeholder="如 km²、mm、%" />
        </div>
      </div>
      <div class="frm-row">
        <label>备注（选填）</label>
        <a-textarea v-model:value="addModal.form.note" :rows="2" />
      </div>
      <div class="frm-help">落库为待导出裁决，admin「导出物化」后写回 stages/*.json 生效</div>
    </a-modal>

    <!-- 修改 label/required 弹窗 -->
    <a-modal
      v-model:open="amendModal.open"
      :title="`修改字段 · ${amendModal.name}`"
      :confirm-loading="amendModal.saving"
      @ok="submitAmend"
    >
      <div class="frm-row">
        <label>字段标识（name，禁改）</label>
        <a-input :value="amendModal.name" disabled />
      </div>
      <div class="frm-row">
        <label>中文名称（label）</label>
        <a-input v-model:value="amendModal.label" />
      </div>
      <div class="frm-row">
        <label>必填（required）</label>
        <a-switch v-model:checked="amendModal.required" />
      </div>
      <div class="frm-help">仅允许改 label / required；其余属性属工程侧管线契约</div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Check, Info, Plus } from '@lucide/vue'
import { eiaDataApi } from '@/apis/eia_data_api'
import { eiaStageApi } from '@/apis/eia_stage_api'
import { useUserStore } from '@/stores/user'

const STAGES = [
  { key: 'planning_eia', label: '规划环评' },
  { key: 'post_eia', label: '事后环评' },
  { key: 'project_eia_openpit', label: '项目环评·露天' },
  { key: 'project_eia_underground', label: '项目环评·井工' },
  { key: 'tracking_eia', label: '跟踪评价' }
]

const TIER_DEFS = [
  { key: 'required', label: '必须', rank: 1 },
  { key: 'contextual', label: '情境', rank: 2 },
  { key: 'optional', label: '可选', rank: 3 }
]

const userStore = useUserStore()
const activeTab = ref('detail')
const loading = ref(false)
const exporting = ref(false)

// 模板里写字面 `}}` 会提前闭合插值，SLOT 记法只能走 script 常量
const slotNotation = '{{SLOT:family.field}}'

// ── Tab 1：节级明细 ──
const detailStage = ref('planning_eia')
const sections = ref([])
const unmapped = ref([])

const detailColumns = [
  { title: '节', key: 'section', width: 90 },
  { title: '节题', dataIndex: 'title', key: 'title', width: 200, ellipsis: true },
  { title: '口径', dataIndex: 'caliber', key: 'caliber', ellipsis: true },
  { title: '挂载字段', dataIndex: 'field', key: 'field', width: 200, ellipsis: true },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
  { title: '置信档', key: 'tier', width: 80 },
  { title: '语料频次', key: 'corpus_freq', width: 90 }
]

const unmappedColumns = [
  { title: '节', key: 'section', width: 90 },
  { title: '量词口径', dataIndex: 'caliber', key: 'caliber', ellipsis: true },
  { title: '样例值', dataIndex: 'value', key: 'value', width: 140, ellipsis: true },
  { title: '单位', dataIndex: 'unit', key: 'unit', width: 80 },
  { title: '来源样本', dataIndex: 'sample', key: 'sample', width: 160, ellipsis: true }
]

const sectionRows = computed(() =>
  sections.value.flatMap((s) =>
    s.quantities.map((q, i) => ({
      ...q,
      rowKey: `${s.key}-${i}`,
      sectionLabel: s.key.replace(/^ch/, '').replace('_S', '.'),
      title: s.title
    }))
  )
)

const detailMetrics = computed(() => ({
  total: sectionRows.value.length,
  titledSections: sections.value.filter((s) => s.title).length
}))

const tierDef = (t) => TIER_DEFS.find((d) => d.key === t)
const tierLabel = (t) => tierDef(t)?.label ?? t ?? '—'
const tierRank = (t) => tierDef(t)?.rank ?? 3

// ── Tab 2：字段维护 ──
const fieldsStage = ref('planning_eia')
const families = ref([])
const activeFamily = ref('')
const famQuery = ref('')

const fieldColumns = [
  { title: '字段标识（name）', key: 'name', width: 240 },
  { title: '中文名称（label）', key: 'label', ellipsis: true },
  { title: '类型', key: 'type', width: 110 },
  { title: '必填', key: 'required', width: 70 },
  { title: '来源', key: 'source', width: 130 },
  { title: '操作', key: 'actions', width: 140 }
]

const filteredFamilies = computed(() => {
  const q = famQuery.value.trim().toLowerCase()
  if (!q) return families.value
  return families.value.filter((f) => f.key.toLowerCase().includes(q) || f.label.includes(q))
})

const activeFamilyDetail = computed(() => families.value.find((f) => f.key === activeFamily.value))

const pendingCount = computed(() =>
  families.value.reduce(
    (acc, f) =>
      acc + f.fields.filter((fd) => (fd.source === 'db' ? fd.pending : fd.db_edit?.pending)).length,
    0
  )
)

const fileFieldCount = computed(
  () => activeFamilyDetail.value?.fields.filter((f) => f.source === 'file').length ?? 0
)
const dbFieldCount = computed(
  () => activeFamilyDetail.value?.fields.filter((f) => f.source === 'db' || f.db_edit).length ?? 0
)

const isPendingAdd = (record) => record.source === 'db' && record.pending
const isPendingAmend = (record) => record.source === 'file' && record.db_edit?.pending

// ── 弹窗状态 ──
const addModal = reactive({
  open: false,
  saving: false,
  form: { name: '', label: '', type: 'string', enumBody: '', required: false, unit: '', note: '' }
})
const amendModal = reactive({
  open: false,
  saving: false,
  name: '',
  label: '',
  required: false,
  originalLabel: ''
})

// ── 数据获取 ──
const fetchSections = async () => {
  loading.value = true
  try {
    const out = await eiaDataApi.getSections(detailStage.value)
    sections.value = out.sections
    unmapped.value = out.unmapped
  } catch (e) {
    message.error(`获取节级明细失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

const fetchForms = async () => {
  loading.value = true
  try {
    const out = await eiaStageApi.listForms(fieldsStage.value)
    const stageData = out.stages[fieldsStage.value]
    families.value = Object.entries(stageData?.families ?? {}).map(([key, f]) => ({ key, ...f }))
    if (!families.value.some((f) => f.key === activeFamily.value)) {
      activeFamily.value = families.value[0]?.key ?? ''
    }
  } catch (e) {
    message.error(`获取口径字段失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

const switchToFields = () => {
  activeTab.value = 'fields'
  if (!families.value.length) fetchForms()
}

// ── 裁决动作 ──
const openAddModal = () => {
  addModal.form = {
    name: '',
    label: '',
    type: 'string',
    enumBody: '',
    required: false,
    unit: '',
    note: ''
  }
  addModal.open = true
}

const submitAdd = async () => {
  const f = addModal.form
  const payload = {
    edit_kind: 'add',
    name: f.name.trim(),
    label: f.label.trim(),
    type: f.type === 'enum:' ? `enum:${f.enumBody.trim()}` : f.type,
    required: f.required
  }
  if (f.unit.trim()) payload.unit = f.unit.trim()
  if (f.note.trim()) payload.note = f.note.trim()
  addModal.saving = true
  try {
    await eiaStageApi.saveField(fieldsStage.value, activeFamily.value, payload)
    message.success('裁决已落库，待导出物化')
    addModal.open = false
    await fetchForms()
  } catch (e) {
    message.error(e.message)
  } finally {
    addModal.saving = false
  }
}

const openAmendModal = (record) => {
  const current = record.db_edit?.field.label ?? record.label
  amendModal.name = record.name
  amendModal.label = current
  amendModal.required = record.db_edit?.field.required ?? record.required
  amendModal.originalLabel = record.label
  amendModal.open = true
}

const submitAmend = async () => {
  const payload = { edit_kind: 'amend', field_name: amendModal.name }
  if (amendModal.label !== amendModal.originalLabel) payload.label = amendModal.label.trim()
  if (
    amendModal.required !==
    (activeFamilyDetail.value?.fields.find((f) => f.name === amendModal.name)?.required ?? false)
  ) {
    payload.required = amendModal.required
  }
  if (!payload.label && payload.required === undefined) {
    message.warning('label 与 required 均未变更')
    return
  }
  amendModal.saving = true
  try {
    await eiaStageApi.saveField(fieldsStage.value, activeFamily.value, payload)
    message.success('裁决已落库，待导出物化')
    amendModal.open = false
    await fetchForms()
  } catch (e) {
    message.error(e.message)
  } finally {
    amendModal.saving = false
  }
}

const onWithdraw = async (record) => {
  try {
    await eiaStageApi.deleteField(fieldsStage.value, activeFamily.value, record.name)
    message.success('已撤回未物化裁决')
    await fetchForms()
  } catch (e) {
    message.error(e.message)
  }
}

const onExport = async () => {
  exporting.value = true
  try {
    const out = await eiaStageApi.exportForms(fieldsStage.value)
    const r = out.results[fieldsStage.value]
    message.success(
      `已写回 ${out.paths.join('、')}（+${r?.added ?? 0} 新增 / ~${r?.amended ?? 0} 修改）；落运行栈技能目录，需人工回流 pisuan-custom`,
      6
    )
    await fetchForms()
  } catch (e) {
    message.error(e.message)
  } finally {
    exporting.value = false
  }
}

onMounted(fetchSections)
</script>

<style lang="less" scoped>
.sections-panel {
  --hairline: var(--gray-200);
}

.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
}

.num {
  font-variant-numeric: tabular-nums;
}

/* ── 双 tab ── */
.tab-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.tab-hint {
  font-size: 12px;
  color: var(--gray-500);
}

.seg {
  display: inline-flex;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  overflow: hidden;

  button {
    padding: 5px 16px;
    font-size: 13px;
    color: var(--gray-600);
    background: var(--gray-0);
    border: none;
    cursor: pointer;

    & + button {
      border-left: 1px solid var(--hairline);
    }

    &.on {
      background: var(--main-0);
      color: var(--main-600);
      font-weight: 600;
    }
  }
}

.card {
  background: var(--gray-0);
  border: 1px solid var(--hairline);
  border-radius: 8px;
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
}

.toolbar-card {
  margin-bottom: 12px;
}

.toolbar-label {
  font-size: 12px;
  color: var(--gray-500);
}

.muted-chip {
  font-size: 12px;
  color: var(--gray-500);

  b {
    color: var(--second-600);
    font-variant-numeric: tabular-nums;
  }
}

/* ── 指标带（同 StandardsPanel 规范）── */
.metric-strip {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  background: var(--main-0);
  border-top: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
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

/* ── 置信档徽标 ── */
.tier {
  display: inline-block;
  min-width: 26px;
  text-align: center;
  height: 19px;
  line-height: 19px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;

  &.tier-1 {
    background: var(--main-0);
    color: var(--main-600);
  }

  &.tier-2 {
    background: var(--gray-100);
    color: var(--gray-600);
  }

  &.tier-3 {
    background: var(--gray-50);
    color: var(--gray-500);
  }
}

.unmapped-block {
  border-top: 1px solid var(--hairline);
  padding-bottom: 8px;
}

.block-hd {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 12px 16px 6px;

  h4 {
    font-size: 13px;
    font-weight: 600;
    color: var(--second-600);
  }

  .hd-sub {
    font-size: 12px;
    color: var(--gray-500);
  }
}

/* ── 字段维护：左右布局 ── */
.split {
  display: grid;
  grid-template-columns: 264px 1fr;
  gap: 12px;
  align-items: start;
}

.fam-list {
  max-height: 560px;
  overflow-y: auto;
  margin-bottom: 0;
}

.fam-search {
  padding: 10px 12px;
  border-bottom: 1px solid var(--hairline);
}

.fam-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--gray-100);
  transition: background 0.12s;
  font-size: 13px;

  &:hover {
    background: var(--gray-50);
  }

  &.on {
    background: var(--main-0);
    box-shadow: inset 2px 0 0 var(--main-500);
  }

  .mini-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--second-500);
    flex: none;
  }

  .fam-name {
    color: var(--gray-800);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .fam-key {
    color: var(--gray-400);
    font-size: 11px;
  }

  .fam-cnt {
    margin-left: auto;
    font-size: 11px;
    color: var(--gray-500);
    font-variant-numeric: tabular-nums;
    flex: none;
  }
}

.fam-hd {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--hairline);

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
    display: flex;
    gap: 6px;
  }
}

.pill-tag {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--gray-100);
  color: var(--gray-600);

  &.main {
    background: var(--main-0);
    color: var(--main-600);
  }
}

.pill-warn-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--second-600);

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--second-500);
  }
}

.pill-mini {
  display: inline-block;
  font-size: 11px;
  padding: 0 6px;
  height: 18px;
  line-height: 18px;
  border-radius: 4px;
  background: var(--gray-100);
  color: var(--gray-600);

  &.warn {
    background: var(--second-50, var(--gray-100));
    color: var(--second-600);
  }
}

.amend-preview {
  font-size: 12px;
  color: var(--second-600);
}

.field-src {
  font-size: 12px;
  white-space: nowrap;

  &.file {
    color: var(--gray-500);
  }

  &.db {
    color: var(--main-600);
    font-weight: 500;
  }
}

.req-ic.yes {
  color: var(--second-600);
}

.tbl-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 16px;
  font-size: 12px;
  color: var(--gray-500);
}

code.k {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  background: var(--gray-100);
  border-radius: 4px;
  padding: 1px 6px;
  color: var(--gray-700);
}

.empty-state {
  padding: 32px 0;
}

/* ── 表格操作列 ── */
:deep(.ant-table-cell) {
  a.primary {
    color: var(--main-600);
    margin-right: 10px;
  }

  a.danger {
    color: var(--second-600);
  }
}

/* ── 表单弹窗 ── */
.frm-row {
  margin-bottom: 14px;

  label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: var(--gray-600);
    margin-bottom: 5px;

    .must {
      color: var(--second-600);
      margin-left: 2px;
    }
  }

  &.inline {
    display: flex;
    gap: 14px;
  }
}

.frm-help {
  font-size: 12px;
  color: var(--gray-500);
  margin-top: 4px;
}

/* ── 只读提示条 ── */
.note-bar {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  background: var(--main-0);
  border-radius: 6px;
  padding: 9px 12px;
  font-size: 12px;
  color: var(--gray-600);

  svg {
    margin-top: 2px;
    flex: none;
    color: var(--main-600);
  }
}
</style>
