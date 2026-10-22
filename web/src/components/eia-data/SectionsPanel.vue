<template>
  <div class="ewp sections-panel">
    <!-- 页头：双 tab seg 收编进 ph-actions（原型 s1/s2） -->
    <div class="page-head">
      <div class="ph-icon">
        <AlignLeft :size="18" />
      </div>
      <div>
        <h2>章节口径</h2>
        <div class="ph-sub">
          section_expectations · 各章节应出现的数值口径全景（bank_compile 产物）
        </div>
      </div>
      <div class="ph-actions">
        <div class="seg">
          <button :class="{ on: activeTab === 'detail' }" @click="activeTab = 'detail'">
            节级明细
          </button>
          <button :class="{ on: activeTab === 'fields' }" @click="switchToFields">字段维护</button>
        </div>
      </div>
    </div>

    <!-- ═══ Tab 1：节级明细（只读，s1）═══ -->
    <template v-if="activeTab === 'detail'">
      <div class="card">
        <div class="toolbar">
          <button
            v-for="s in STAGES"
            :key="s.key"
            class="stage-chip"
            :class="{ on: detailStage === s.key }"
            @click="setDetailStage(s.key)"
          >
            {{ s.label }} <span class="cnt">{{ s.key }}</span>
          </button>
          <span class="flex-sp"></span>
          <span class="src-chip">
            <TrendingUp :size="13" />
            仅看未归并 <b>{{ unmapped.length }}</b>
          </span>
          <button
            v-if="userStore.isAdmin"
            class="btn btn-txt btn-sm"
            :disabled="recompiling"
            @click="confirmRecompile"
          >
            <RefreshCw :size="13" /> 重编译
          </button>
        </div>

        <div
          class="metric-strip"
          style="border: none; border-bottom: 1px solid var(--gray-200); border-radius: 0"
        >
          <div class="metric-cell">
            <span class="metric-label">口径总条目</span>
            <span class="metric-value">{{ detailMetrics.total }}</span>
          </div>
          <div class="metric-cell accent">
            <span class="metric-label"><span class="dot dot-ok"></span>已归并 mapped</span>
            <span class="metric-value"
              >{{ detailMetrics.mapped }}<small>{{ detailMetrics.mappedPct }}%</small></span
            >
          </div>
          <div class="metric-cell" :class="{ warn: unmapped.length > 0 }">
            <span class="metric-label"><span class="dot dot-warn"></span>未归并 unmapped</span>
            <span class="metric-value">{{ unmapped.length }}</span>
          </div>
          <div class="metric-cell">
            <span class="metric-label">覆盖章节</span>
            <span class="metric-value">{{ detailMetrics.titledSections }}<small>节</small></span>
          </div>
        </div>

        <div v-if="sectionRows.length" style="overflow-x: auto">
          <table class="tbl">
            <thead>
              <tr>
                <th style="width: 64px">节</th>
                <th style="width: 150px">节题</th>
                <th>口径</th>
                <th style="width: 64px">单位</th>
                <th>置信档</th>
                <th class="r" style="padding-right: 20px">语料频次</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in pagedRows"
                :key="row.rowKey"
                :class="{ 'unmapped-row': row.unmapped }"
              >
                <td class="mono">{{ row.sectionLabel }}</td>
                <td class="sec-cite" :title="row.title">{{ row.title || '—' }}</td>
                <td>
                  {{ row.caliber }}
                  <span v-if="row.unmapped" class="pill pill-orange pill-sm">未归并</span>
                </td>
                <td class="mono">{{ row.unit || '—' }}</td>
                <td>
                  <span v-if="row.tierRank" class="tier" :class="`tier-${row.tierRank}`"
                    >T{{ row.tierRank }}</span
                  >
                  <span v-else class="muted-cell">—</span>
                </td>
                <td class="r" style="padding-right: 20px">
                  <template v-if="row.freqPct != null">
                    <span class="meter" :class="{ low: row.freqPct < 40 }"
                      ><i :style="{ width: row.freqPct + '%' }"></i
                    ></span>
                    <span class="num">{{ row.freqPct }}%</span>
                  </template>
                  <span v-else class="muted-cell">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else-if="!loading" class="empty-state">
          <a-empty description="该阶段暂无节级口径数据" />
        </div>

        <div class="tbl-foot">
          共 {{ mergedRows.length }} 条 · 每页 {{ PAGE_SIZE }} ·
          <span
            >橙色行为 forms_label_map 未命中的未归并口径 → 由「字段维护」补字段后重跑 bank_compile
            归并</span
          >
          <template v-if="pageCount > 1">
            <span class="flex-sp"></span>
            <button class="btn btn-txt btn-sm" :disabled="page <= 1" @click="page--">上一页</button>
            <span class="num">{{ page }}/{{ pageCount }}</span>
            <button class="btn btn-txt btn-sm" :disabled="page >= pageCount" @click="page++">
              下一页
            </button>
          </template>
        </div>
      </div>

      <div class="note-bar">
        <Info :size="14" />
        <span>
          只读边界：本页数据为 bank_compile
          生成物，页面零写通道；专家加工动作全部收敛在「字段维护」tab。
        </span>
      </div>
    </template>

    <!-- ═══ Tab 2：字段维护（编辑 + 导出，s2）═══ -->
    <template v-else>
      <div class="card">
        <div class="toolbar" style="gap: 14px">
          <span class="toolbar-label">阶段</span>
          <button
            v-for="s in STAGES"
            :key="s.key"
            class="stage-chip"
            :class="{ on: fieldsStage === s.key }"
            @click="setFieldsStage(s.key)"
          >
            {{ s.label }} <span class="cnt">{{ s.key }}</span>
          </button>
          <span class="flex-sp"></span>
          <span v-if="pendingCount" class="pill pill-orange">
            <span class="dot dot-warn"></span>{{ pendingCount }} 项待导出
          </span>
          <button class="btn btn-pri btn-sm" @click="openAddModal">
            <Plus :size="14" />添加字段
          </button>
          <button
            v-if="userStore.isAdmin"
            class="btn btn-sec btn-sm"
            :disabled="!pendingCount"
            @click="onExport"
          >
            <Download :size="14" />{{ exporting ? '导出中…' : '导出物化' }}
          </button>
        </div>
      </div>

      <div class="split">
        <!-- 左：口径族列表 -->
        <div class="card fam-list">
          <div class="fam-search">
            <input v-model="famQuery" class="inp" placeholder="搜索口径族…" />
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
            <span class="pill pill-gray pill-sm">{{ f.key }}</span>
            <span class="fam-cnt">{{ f.fields.length }} 字段</span>
          </div>
          <div v-if="!filteredFamilies.length" class="empty-state">
            <a-empty description="无匹配口径族" />
          </div>
        </div>

        <!-- 右：字段表 -->
        <div class="card">
          <template v-if="activeFamilyDetail">
            <div class="card-hd">
              <h3>{{ activeFamilyDetail.label }}</h3>
              <code class="k">{{ activeFamily }}</code>
              <span class="hd-sub">
                {{ fieldsStage }} · {{ activeFamilyDetail.fields.length }} 个字段
                <template v-if="activeFamilyDetail.chapters?.length">
                  · 挂载 {{ activeFamilyDetail.chapters.join('、') }}
                </template>
              </span>
              <div class="hd-right">
                <span class="pill pill-gray">文件锚点 {{ fileFieldCount }}</span>
                <span v-if="dbFieldCount" class="pill pill-main"
                  >DB 裁决 {{ dbFieldCount }} · 待导出</span
                >
              </div>
            </div>
            <table class="tbl">
              <thead>
                <tr>
                  <th>字段标识（name）</th>
                  <th>中文名称（label）</th>
                  <th style="width: 90px">类型</th>
                  <th style="width: 70px">必填</th>
                  <th style="width: 130px">来源</th>
                  <th class="r" style="padding-right: 20px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="record in activeFamilyDetail.fields" :key="record.name">
                  <td class="mono">
                    {{ record.name }}
                    <span v-if="isPendingAdd(record)" class="pill pill-warn pill-sm"
                      >新增 · 未导出</span
                    >
                  </td>
                  <td>
                    {{ record.label }}
                    <span v-if="isPendingAmend(record)" class="pill pill-warn pill-sm"
                      >修改 · 未导出</span
                    >
                    <div v-if="isPendingAmend(record) && record.db_edit" class="amend-preview">
                      → {{ record.db_edit.field.label ?? record.label }}
                    </div>
                  </td>
                  <td>
                    <span class="pill pill-gray pill-sm">{{ record.type }}</span>
                  </td>
                  <td>
                    <Check v-if="record.required" class="req-ic yes" :size="14" />
                    <span v-else class="muted-cell">选填</span>
                  </td>
                  <td>
                    <span v-if="record.source === 'db'" class="field-src db"
                      >DB · {{ record.decided_by }}</span
                    >
                    <span v-else class="field-src file">文件锚点</span>
                  </td>
                  <td class="r" style="padding-right: 20px; white-space: nowrap">
                    <button class="btn btn-txt btn-sm" @click="openAmendModal(record)">
                      改 label
                    </button>
                    <button
                      v-if="isPendingAdd(record)"
                      class="btn btn-txt btn-sm withdraw-btn"
                      @click="onWithdraw(record)"
                    >
                      撤回
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
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
import { AlignLeft, Check, Download, Info, Plus, RefreshCw, TrendingUp } from '@lucide/vue'
import { eiaDataApi } from '@/apis/eia_data_api'
import { eiaStageApi } from '@/apis/eia_stage_api'
import { useUserStore } from '@/stores/user'

const STAGES = [
  { key: 'planning_eia', label: '规划环评' },
  { key: 'project_eia_underground', label: '井工矿环评' },
  { key: 'project_eia_openpit', label: '露天矿环评' },
  { key: 'tracking_eia', label: '跟踪评价' },
  { key: 'post_eia', label: '后评价' }
]

const TIER_RANKS = { required: 1, contextual: 2, optional: 3 }

const PAGE_SIZE = 50

const userStore = useUserStore()
const activeTab = ref('detail')
const loading = ref(false)
const exporting = ref(false)
const recompiling = ref(false)

// 模板里写字面 `}}` 会提前闭合插值，SLOT 记法只能走 script 常量
const slotNotation = '{{SLOT:family.field}}'

// ── Tab 1：节级明细 ──
const detailStage = ref('planning_eia')
const sections = ref([])
const unmapped = ref([])
const page = ref(1)

const sectionRows = computed(() =>
  sections.value.flatMap((s) =>
    s.quantities.map((q, i) => {
      const rank = TIER_RANKS[q.tier] ?? null
      return {
        rowKey: `${s.key}-${i}`,
        sectionLabel: s.key.replace(/^ch/, '').replace('_S', '.'),
        title: s.title,
        caliber: q.caliber,
        unit: q.unit,
        tierRank: rank,
        freqPct: q.corpus_freq != null ? Math.round(q.corpus_freq * 100) : null,
        unmapped: false,
        sortKey: s.key
      }
    })
  )
)

// unmapped 橙行按节号内联到对应节之后（原型 s1），对不上号的追加表尾
// unmapped.section 与 sections[].key 同为 ch/ch_S 记法，先归一再匹配
const normSection = (s) => (s ?? '').replace(/^ch/, '').replace('_S', '.')

const mergedRows = computed(() => {
  const rows = [...sectionRows.value]
  const pendingUnmapped = []
  for (const u of unmapped.value) {
    const label = normSection(u.section)
    const idx = rows.findLastIndex((r) => r.sectionLabel === label && !r.unmapped)
    if (idx >= 0) {
      rows.splice(idx + 1, 0, {
        rowKey: `unmapped-${rows.length}-${u.caliber}`,
        sectionLabel: label,
        title: '',
        caliber: u.caliber,
        unit: u.unit,
        tierRank: null,
        freqPct: null,
        unmapped: true
      })
    } else {
      pendingUnmapped.push(u)
    }
  }
  for (const u of pendingUnmapped) {
    rows.push({
      rowKey: `unmapped-tail-${u.caliber}-${u.value}`,
      sectionLabel: normSection(u.section),
      title: '',
      caliber: u.caliber,
      unit: u.unit,
      tierRank: null,
      freqPct: null,
      unmapped: true
    })
  }
  return rows
})

const pageCount = computed(() => Math.max(1, Math.ceil(mergedRows.value.length / PAGE_SIZE)))
const pagedRows = computed(() => {
  const p = Math.min(page.value, pageCount.value)
  return mergedRows.value.slice((p - 1) * PAGE_SIZE, p * PAGE_SIZE)
})

// 已归并 = 注册口径中已挂载字段（q.field 非空）的条目；unmapped 是未命中任何字段的独立流
const detailMetrics = computed(() => {
  const quantities = sections.value.flatMap((s) => s.quantities)
  const total = quantities.length
  const mapped = quantities.filter((q) => q.field).length
  return {
    total,
    mapped,
    mappedPct: total ? Math.round((mapped / total) * 100) : 0,
    titledSections: sections.value.filter((s) => s.quantities.length).length
  }
})

// ── Tab 2：字段维护 ──
const fieldsStage = ref('planning_eia')
const families = ref([])
const activeFamily = ref('')
const famQuery = ref('')

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
    page.value = 1
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

const setDetailStage = (key) => {
  if (detailStage.value === key) return
  detailStage.value = key
  fetchSections()
}

const setFieldsStage = (key) => {
  if (fieldsStage.value === key) return
  fieldsStage.value = key
  fetchForms()
}

const switchToFields = () => {
  activeTab.value = 'fields'
  if (!families.value.length) fetchForms()
}

// ── 重编译（admin，后台任务）──
const confirmRecompile = () => {
  Modal.confirm({
    title: '重编译章节口径',
    content:
      '以语料知识库全量文档重建技能语料衍生物（section_expectations / 切片库 / bank_index 等），后台任务执行，进度见任务中心。继续？',
    okText: '重编译',
    cancelText: '取消',
    onOk: () => {
      recompiling.value = true
      return eiaDataApi
        .recompileExpectations()
        .then(() => message.success('已提交重编译任务，完成后刷新本页查看最新口径'))
        .catch((err) => message.error(err?.message || '任务提交失败'))
        .finally(() => {
          recompiling.value = false
        })
    }
  })
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
.flex-sp {
  flex: 1;
}

.muted-cell {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.amend-preview {
  font-size: 12px;
  color: var(--second-600);
}

.withdraw-btn {
  color: var(--second-600);

  &:hover {
    background: var(--second-50);
  }
}

.empty-state {
  padding: 32px 0;
}

/* ── 表单弹窗 ── */
.frm-row {
  margin-bottom: 14px;

  label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-secondary);
    margin-bottom: 5px;

    .must {
      color: var(--color-error-500);
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
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
</style>

<style lang="less" src="./factory-ui.less"></style>
