<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { CircleHelp, Info, RefreshCw, ShieldCheck } from '@lucide/vue'
import { regulationApi } from '@/extensions/regulation-library/regulation_api'

// 标准规范库加工工作台：UI 配方对齐环评域「语料元数据标注」。
const loading = ref(false)
const loaded = ref(false)
const processingFileId = ref('')
const enriching = ref(false)
const items = ref([])
const summary = ref({
  documents: 0,
  enriched: 0,
  indexed: 0,
  empty: 0,
  indicators: 0,
  verified: 0,
  process_status_counts: {},
  run_status_counts: {}
})
const keyword = ref('')
const boundKbId = ref('')
const processStatus = ref('')
const settingOpen = ref(false)
const savingBinding = ref(false)
const kbList = ref([])
const bindingForm = ref({ kb_id: '' })
const page = ref(1)
const pageSize = ref(20)
const enrichForm = ref({
  kb_id: '',
  file_id: '',
  doc_code: '',
  doc_name: '',
  doc_type: 'technical_standard'
})
const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
const detailTab = ref('units')
const runStatus = ref('')

const emptySummary = {
  documents: 0,
  enriched: 0,
  indexed: 0,
  empty: 0,
  indicators: 0,
  verified: 0,
  process_status_counts: {},
  run_status_counts: {}
}

const statusCounts = computed(() => summary.value.process_status_counts || {})
const statusChips = computed(() => [
  { key: '', label: '全部', count: summary.value.documents },
  { key: 'enriched', label: '已加工', count: statusCounts.value.enriched || 0 },
  { key: 'indexed', label: '仅索引', count: statusCounts.value.indexed || 0 },
  { key: 'empty', label: '无索引', count: statusCounts.value.empty || 0 }
])
const pendingCount = computed(() => summary.value.documents - summary.value.enriched)
const enrichedRatio = computed(() => {
  if (!summary.value.documents) return '0%'
  return `${Math.round((summary.value.enriched / summary.value.documents) * 100)}%`
})
const isFiltered = computed(() => Boolean(processStatus.value || keyword.value))
const emptyDesc = computed(() => (isFiltered.value ? '当前筛选无匹配规范' : '规范文档为空'))

const statusMeta = {
  enriched: { label: '已加工', cls: 'ok' },
  indexed: { label: '仅索引', cls: 'warn' },
  empty: { label: '无索引', cls: 'gray' }
}

const runMeta = {
  not_run: { label: '未加工', cls: 'gray' },
  pending: { label: '加工中', cls: 'main' },
  success: { label: '成功', cls: 'ok' },
  failed: { label: '失败', cls: 'err' },
  conflict: { label: '冲突', cls: 'orange' },
  none: { label: '未加工', cls: 'gray' }
}

const runStatusCounts = computed(() => summary.value.run_status_counts || {})
const runStatusChips = computed(() => [
  { key: '', label: '全部', count: summary.value.documents },
  { key: 'not_run', label: '未加工', count: runStatusCounts.value.not_run || 0 },
  { key: 'running', label: '加工中', count: runStatusCounts.value.running || 0 },
  { key: 'success', label: '成功', count: runStatusCounts.value.success || 0 },
  { key: 'failed', label: '失败', count: runStatusCounts.value.failed || 0 },
  { key: 'conflict', label: '冲突', count: runStatusCounts.value.conflict || 0 }
])

const fetchList = async () => {
  loading.value = true
  try {
    if (!boundKbId.value) {
      items.value = []
      summary.value = emptySummary
      return
    }
    const params = {
      kb_id: boundKbId.value,
      page: page.value,
      page_size: pageSize.value
    }
    if (keyword.value) params.keyword = keyword.value
    if (processStatus.value) params.process_status = processStatus.value
    if (runStatus.value) params.run_status = runStatus.value
    const res = await regulationApi.listDocuments(params)
    items.value = res.items || []
    summary.value = res.summary || emptySummary
  } catch (e) {
    message.error('加载规范文档失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
    loaded.value = true
  }
}

const setStatus = (value) => {
  if (processStatus.value === value) return
  processStatus.value = value
  page.value = 1
  fetchList()
}

const setRunStatus = (value) => {
  if (runStatus.value === value) return
  runStatus.value = value
  page.value = 1
  fetchList()
}

const clearFilters = () => {
  keyword.value = ''
  processStatus.value = ''
  runStatus.value = ''
  page.value = 1
  fetchList()
}

const onSearch = () => {
  page.value = 1
  fetchList()
}

const onKeywordInput = (e) => {
  if (!e.target.value) clearFilters()
}

const onPageChange = (value, size) => {
  page.value = value
  pageSize.value = size
  fetchList()
}

const onSizeChange = (value) => {
  page.value = 1
  pageSize.value = value
  fetchList()
}

const formatTime = (value) => {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

const pdfUrl = ref('')
const pdfLoading = ref(false)
const pdfError = ref('')

const closeDetail = () => {
  detailOpen.value = false
  if (pdfUrl.value) {
    URL.revokeObjectURL(pdfUrl.value)
    pdfUrl.value = ''
  }
}

const loadPdfPreview = async () => {
  pdfUrl.value = ''
  pdfError.value = ''
  const file = detail.value?.file
  if (!file || file.file_type !== 'pdf') return
  pdfLoading.value = true
  try {
    const res = await regulationApi.getPdfResponse(file.kb_id, file.file_id)
    const blob = await res.blob()
    if (blob.type && !blob.type.includes('pdf')) throw new Error('响应不是 PDF')
    pdfUrl.value = URL.createObjectURL(blob)
  } catch (e) {
    pdfError.value = e?.message || '原文加载失败'
  } finally {
    pdfLoading.value = false
  }
}

const openDetail = async (record) => {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  detailTab.value = 'units'
  taxonomyRows.value = []
  taxonomyQuery.value = ''
  loadTaxonomyRows(record)
  try {
    detail.value = await regulationApi.getDocumentDetail(record.kb_id, record.file_id)
    await loadPdfPreview()
  } catch (e) {
    message.error('加载加工详情失败: ' + (e.message || '未知错误'))
  } finally {
    detailLoading.value = false
  }
}

// 分类编码表行（taxonomy 结构化产物；非分类学表为空属正常）
const taxonomyRows = ref([])
const taxonomyQuery = ref('')
const taxonomyRowsFiltered = computed(() => {
  const q = taxonomyQuery.value.trim().toLowerCase()
  if (!q) return taxonomyRows.value
  return taxonomyRows.value.filter(
    (row) =>
      row.code.toLowerCase().includes(q) ||
      (row.name || '').toLowerCase().includes(q) ||
      (row.meaning || '').toLowerCase().includes(q)
  )
})

const tableUnitCount = computed(
  () => detail.value?.units?.filter((u) => u.unit_type === 'table').length ?? 0
)
const structuredRowCount = computed(
  () => taxonomyRows.value.length + (detail.value?.indicators?.length ?? 0)
)
const unclassifiedTableCount = computed(() => {
  const roles = detail.value?.table_roles || {}
  return (roles.other || 0) + (roles.unclassified || 0)
})

// 一级类行（代码 2 位）加强调条；点击行展开/收起完整含义
const expandedCodes = reactive(new Set())
const isLevelOne = (row) => (row.code || '').length === 2
const toggleMeaning = (code) => {
  if (expandedCodes.has(code)) expandedCodes.delete(code)
  else expandedCodes.add(code)
}

const loadTaxonomyRows = async (record) => {
  const docCode = record.doc_codes?.[0]
  if (!docCode) return
  try {
    const res = await regulationApi.listTaxonomyRows({ kb_id: record.kb_id, doc_code: docCode })
    taxonomyRows.value = res.items || []
  } catch (e) {
    console.error('分类表加载失败', e)
  }
}

const openEnrich = (record) => {
  processingFileId.value = record.file_id
  enrichForm.value = {
    kb_id: record.kb_id,
    file_id: record.file_id,
    doc_code: record.suggested_doc_code,
    doc_name: record.suggested_doc_name,
    doc_type: 'technical_standard'
  }
}

const closeEnrich = () => {
  processingFileId.value = ''
}

const submitEnrich = async () => {
  enriching.value = true
  try {
    const res = await regulationApi.enrichFile(enrichForm.value)
    message.success(`加工完成：${res.result.units} 个结构单元，${res.result.indicators} 条指标`)
    closeEnrich()
    await fetchList()
  } catch (e) {
    message.error('加工失败: ' + (e.message || e))
  } finally {
    enriching.value = false
  }
}

const layerText = (record) => {
  const item = record.indicators
  return `${item.expert} / ${item.reviewed} / ${item.candidate}`
}

const actionDisabled = (record) => record.process_status === 'empty' || !record.suggested_doc_code

const actionTitle = (record) => {
  if (record.process_status === 'empty') return '文件尚无索引 chunk'
  if (!record.suggested_doc_code) return '请先补充标准号'
  return record.process_status === 'enriched' ? '重新加工（专家行受保护）' : '开始加工'
}

const loadKbs = async () => {
  const { databaseApi } = await import('@/apis/knowledge_api')
  const res = await databaseApi.getDatabases()
  kbList.value = (res.databases || [])
    .filter((db) => db.kb_type === 'milvus' || db.type === 'milvus')
    .map((db) => ({ value: db.kb_id, label: `${db.name}（${db.kb_id}）` }))
}

const openSettings = async () => {
  bindingForm.value = { kb_id: boundKbId.value }
  settingOpen.value = true
  try {
    await loadKbs()
  } catch (e) {
    message.error('加载知识库失败: ' + (e.message || '未知错误'))
  }
}

const closeSettings = () => {
  settingOpen.value = false
}

const saveBinding = async () => {
  savingBinding.value = true
  try {
    const res = await regulationApi.bindKnowledgeBase(bindingForm.value.kb_id)
    boundKbId.value = res.kb_id
    message.success('标准规范库绑定已保存')
    closeSettings()
    page.value = 1
    await fetchList()
  } catch (e) {
    message.error('绑定失败: ' + (e.message || e))
  } finally {
    savingBinding.value = false
  }
}

onMounted(async () => {
  try {
    const binding = await regulationApi.getBinding()
    boundKbId.value = binding.kb_id || ''
  } catch (e) {
    message.error('加载规范库绑定失败: ' + (e.message || '未知错误'))
  }
  await fetchList()
})
</script>

<template>
  <div class="ewp regulation-library">
    <div class="page-head">
      <div class="ph-icon"><ShieldCheck :size="18" /></div>
      <div>
        <h2>规范库加工</h2>
        <div class="ph-sub">
          标准规范库 KB：{{ boundKbId || '未绑定' }} · {{ summary.documents }} 份已索引规范的条款 / 限值结构化
        </div>
      </div>
      <div class="ph-actions">
        <span v-if="pendingCount" class="pill pill-orange">
          <span class="dot dot-warn"></span>{{ pendingCount }} 份待加工
        </span>
        <button class="btn btn-sec btn-sm" :disabled="loading" @click="fetchList">
          <RefreshCw :size="14" />{{ loading ? '刷新中…' : '刷新' }}
        </button>
        <button class="btn btn-pri btn-sm" @click="openSettings">绑定设置</button>
      </div>
    </div>

    <div v-if="loading && !loaded" class="regulation-skeleton" aria-hidden="true">
      <div class="metric-strip">
        <div v-for="i in 4" :key="i" class="metric-cell">
          <span class="sk sk-line w-25"></span>
          <span class="sk sk-line value w-10"></span>
        </div>
      </div>
      <div class="card">
        <div class="toolbar">
          <span v-for="i in 4" :key="i" class="sk sk-chip"></span>
          <span style="flex: 1"></span>
          <span class="sk sk-inp"></span>
        </div>
        <div v-for="i in 10" :key="i" class="sk-tbl-row" :class="{ hd: i === 1 }">
          <span
            v-for="j in 8"
            :key="j"
            class="sk sk-line"
            :class="['w-40', 'w-10', 'w-10', 'w-10', 'w-10', 'w-10', 'w-10', 'w-10'][j - 1]"
          ></span>
        </div>
      </div>
    </div>

    <div v-else-if="!boundKbId" class="card binding-warning">
      <div class="empty-state">
        <a-empty description="当前部署尚未绑定标准规范库">
          <button class="btn btn-pri btn-sm" @click="openSettings">立即绑定</button>
        </a-empty>
      </div>
    </div>

    <template v-else-if="items.length || isFiltered">
      <div class="metric-strip">
        <div class="metric-cell">
          <span class="metric-label">规范文档</span>
          <span class="metric-value">{{ summary.documents }}<small>份</small></span>
        </div>
        <div class="metric-cell">
          <span class="metric-label"><span class="dot dot-ok"></span>已加工</span>
          <span class="metric-value">{{ summary.enriched }}<small>{{ enrichedRatio }}</small></span>
        </div>
        <div class="metric-cell" :class="{ warn: pendingCount > 0 }">
          <span class="metric-label"><span class="dot dot-warn"></span>待加工</span>
          <span class="metric-value">{{ pendingCount }}</span>
        </div>
        <div class="metric-cell accent">
          <span class="metric-label">候选指标</span>
          <span class="metric-value">{{ summary.indicators }}</span>
        </div>
      </div>

      <div class="card">
        <div class="toolbar">
          <button
            v-for="chip in statusChips"
            :key="chip.key"
            class="stage-chip"
            :class="{ on: processStatus === chip.key }"
            @click="setStatus(chip.key)"
          >
            {{ chip.label }} <span class="cnt">{{ chip.count }}</span>
          </button>
          <span style="flex: 1"></span>

          <span class="toolbar-label">运行状态</span>
          <div class="seg">
            <button
              v-for="chip in runStatusChips"
              :key="chip.key"
              :class="{ on: runStatus === chip.key }"
              @click="setRunStatus(chip.key)"
            >
              {{ chip.label }}
            </button>
          </div>

          <input
            v-model="keyword"
            class="inp"
            style="width: 240px"
            placeholder="搜索文件名 / 标准号…"
            @change="onKeywordInput"
            @keyup.enter="onSearch"
          />
        </div>

        <div v-if="items.length" class="tbl-scroll">
          <table class="tbl regulation-tbl" :style="loading ? 'opacity: .55' : ''">
            <thead>
              <tr>
                <th>规范文档</th>
                <th style="width: 132px">建议标准号</th>
                <th style="width: 76px">加工状态</th>
                <th style="width: 64px" class="r">结构单元</th>
                <th style="width: 56px" class="r">表格</th>
                <th style="width: 64px" class="r">指标</th>
                <th style="width: 112px">
                  <a-tooltip placement="topLeft">
                    <template #title>
                      <div>该文档三层指标行的数量：权威 / 已核验候选 / 未核验候选</div>
                      <div>· 权威：专家手工录入，保存即核验生效</div>
                      <div>· 已核验候选：机器抽取且经人工核验</div>
                      <div>· 未核验候选：机器抽取，使用前需人工对照</div>
                      <div>如 2 / 3 / 12 = 权威 2、已核验 3、未核验 12；全 0 表示尚未加工或未抽到指标</div>
                    </template>
                    <span class="th-help">核验分布 <CircleHelp :size="12" /></span>
                  </a-tooltip>
                </th>
                <th style="width: 150px">最近加工</th>
                <th style="width: 140px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="record in items"
                :key="record.file_id"
              >
                <td>
                  <div class="doc-cell">
                    <span class="doc-name" :title="record.filename">{{ record.filename }}</span>
                    <span class="file-id mono">{{ record.file_id }}</span>
                  </div>
                </td>
                <td>
                  <span v-if="record.doc_codes.length" class="pill pill-ok pill-sm mono">
                    {{ record.doc_codes[0] }}
                  </span>
                  <span v-else-if="record.suggested_doc_code" class="pill pill-main pill-sm mono">
                    {{ record.suggested_doc_code }}
                  </span>
                  <span v-else class="pill pill-err pill-sm">待补充</span>
                </td>
                <td>
                  <span class="pill pill-sm" :class="`pill-${statusMeta[record.process_status]?.cls || 'gray'}`">
                    {{ statusMeta[record.process_status]?.label || record.process_status }}
                  </span>
                </td>
                <td class="r val">{{ record.unit_count }}</td>
                <td class="r val">{{ record.table_count }}</td>
                <td class="r val">{{ record.indicators.total }}</td>
                <td>
                  <span class="layer-text mono" title="权威 / 已核验候选 / 未核验候选">
                    {{ layerText(record) }}
                  </span>
                </td>
                <td>
                  <div class="run-cell">
                    <span class="pill pill-sm" :class="`pill-${runMeta[record.run_status]?.cls || 'gray'}`">
                      {{ runMeta[record.run_status]?.label || record.run_status }}
                    </span>
                    <span class="run-time">{{ formatTime(record.last_run_finished_at || record.last_run_started_at) }}</span>
                  </div>
                </td>
                <td>
                  <div class="action-row">
                    <button class="btn btn-sec btn-sm" @click="openDetail(record)">详情</button>
                  <a-tooltip :title="actionTitle(record)">
                    <button
                      class="btn btn-sec btn-sm"
                      :disabled="actionDisabled(record)"
                      @click="openEnrich(record)"
                    >
                      {{ record.process_status === 'enriched' ? '重跑' : '加工' }}
                    </button>
                  </a-tooltip>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="empty-state">
          <a-empty :description="emptyDesc">
            <button v-if="isFiltered" class="btn btn-sec btn-sm" @click="clearFilters">清除筛选</button>
          </a-empty>
        </div>

        <div v-if="items.length" class="tbl-foot">
          <span>
            展示第 {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, summary.documents) }} 份
          </span>
          <span style="margin-left: auto"></span>
          <a-pagination
            v-model:current="page"
            v-model:page-size="pageSize"
            :total="summary.documents"
            :page-size-options="['10', '20', '30', '50']"
            show-size-changer
            size="small"
            @change="onPageChange"
            @showSizeChange="onSizeChange"
          />
        </div>
      </div>
    </template>

    <div v-else class="card">
      <div class="empty-state">
        <a-empty
          :description="boundKbId ? '当前规范库暂无文档' : '当前部署尚未绑定标准规范库'"
        >
          <button class="btn btn-pri btn-sm" @click="openSettings">绑定设置</button>
        </a-empty>
      </div>
    </div>

    <div class="note-bar">
      <Info :size="14" />
      <span>
        自动抽取产物为候选层；专家行与已核验行可支撑限值结论，未核验行仍须标注「需人工对照」。
        重新加工只刷新候选行，不会覆盖专家权威数据。
      </span>
    </div>

    <a-modal
      :open="!!processingFileId"
      title="确认规范加工"
      :confirm-loading="enriching"
      width="620px"
      ok-text="开始加工"
      cancel-text="取消"
      @ok="submitEnrich"
      @cancel="closeEnrich"
    >
      <div class="meta-ident">
        <span class="name">{{ enrichForm.doc_name || '未命名规范' }}</span>
        <span class="pill pill-main pill-sm mono">{{ enrichForm.doc_code || '待补充' }}</span>
        <span class="pill pill-gray pill-sm">technical_standard</span>
      </div>
      <div class="meta-form">
        <div class="fld">
          <label for="reg-doc-code">标准号 doc_code</label>
          <a-input id="reg-doc-code" v-model:value="enrichForm.doc_code" placeholder="如 GB 3838-2002" />
          <p class="fld-help">图谱与指标查询主键，建议与标准原文封面一致。</p>
        </div>
        <div class="fld">
          <label for="reg-doc-name">标准名称 doc_name</label>
          <a-input id="reg-doc-name" v-model:value="enrichForm.doc_name" placeholder="如 地表水环境质量标准" />
          <p class="fld-help">用于图谱展示、审核对照与检索提示。</p>
        </div>
        <div class="fld">
          <label for="reg-doc-type">文档类型</label>
          <a-select id="reg-doc-type" v-model:value="enrichForm.doc_type">
            <a-select-option value="technical_standard">技术规范/标准</a-select-option>
            <a-select-option value="law">法律</a-select-option>
            <a-select-option value="admin_regulation">行政法规</a-select-option>
            <a-select-option value="ministry_rule">部门规章</a-select-option>
          </a-select>
          <p class="fld-help">影响结构单元解析方式。</p>
        </div>
      </div>
      <div class="meta-warn">
        <Info :size="14" style="flex: none; margin-top: 3px" />
        <span>将读取知识库 chunk，解析结构单元、分类表格并抽取候选指标；已有专家手工行时会直接拒绝加工。</span>
      </div>
    </a-modal>

    <a-modal
      :open="detailOpen"
      :title="detail?.file?.filename || '加工详情'"
      width="1560px"
      :footer="null"
      @cancel="closeDetail"
    >
      <a-spin :spinning="detailLoading">
        <template v-if="detail">
          <div class="detail-body">
            <div class="pdf-pane">
              <div class="pdf-pane-head">原文预览</div>
              <div v-if="pdfLoading" class="pdf-placeholder">加载原文中…</div>
              <div v-else-if="pdfError" class="pdf-placeholder pdf-error">{{ pdfError }}</div>
              <iframe
                v-else-if="pdfUrl"
                :src="pdfUrl"
                class="pdf-frame"
                title="原文 PDF 预览"
              ></iframe>
              <div v-else class="pdf-placeholder">本文件无 PDF 原文</div>
            </div>

            <div class="detail-main">
          <div class="meta-ident">
            <span class="name">{{ detail.doc_codes[0] || '未编号' }}</span>
            <span
              class="pill pill-sm"
              :class="`pill-${runMeta[detail.latest_run?.status || 'none']?.cls || 'gray'}`"
            >
              {{ runMeta[detail.latest_run?.status || 'none']?.label || '未加工' }}
            </span>
            <span class="dim mono">
              最近加工：{{ formatTime(detail.latest_run?.started_at) }}
            </span>
          </div>

          <div class="detail-metrics">
            <div><small>结构单元</small><b>{{ detail.units.length }}</b></div>
            <div><small>表格</small><b>{{ tableUnitCount }}</b></div>
            <div><small>已拆行</small><b>{{ structuredRowCount }}</b></div>
            <div><small>指标</small><b>{{ detail.indicators.length }}</b></div>
            <div><small>运行次数</small><b>{{ detail.runs.length }}</b></div>
          </div>

          <a-tabs v-model:activeKey="detailTab">
            <a-tab-pane key="units" tab="结构单元">
              <div class="detail-scroll detail-table-wrap">
                <table class="tbl detail-table">
                  <thead>
                    <tr>
                      <th style="width: 64px">#</th>
                      <th style="width: 90px">条款 / 表</th>
                      <th style="width: 82px">类型</th>
                      <th style="width: 82px">角色</th>
                      <th>标题 / 内容片段</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(unit, index) in detail.units" :key="`${unit.chunk_id}-${unit.unit_no}`">
                      <td class="mono muted">{{ index + 1 }}</td>
                      <td class="mono code">{{ unit.unit_no }}</td>
                      <td>
                        <span class="type-pill">{{ unit.unit_type }}</span>
                      </td>
                      <td>{{ unit.table_role || '—' }}</td>
                      <td class="detail-title" :title="unit.title">{{ unit.title }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>
            <a-tab-pane key="indicators" tab="指标预览">
              <div v-if="detail.indicators.length" class="detail-scroll">
                <table class="tbl">
                  <thead>
                    <tr>
                      <th>层级</th><th>表/条款</th><th>污染物</th><th>指标</th>
                      <th class="r">限值</th><th>单位</th><th>条件</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in detail.indicators" :key="item.id">
                      <td><span class="pill pill-sm" :class="`pill-${item.layer === 'authority' ? 'ok' : item.layer === 'reviewed' ? 'main' : 'gray'}`">{{ item.layer }}</span></td>
                      <td class="mono">{{ item.unit_no }}</td>
                      <td>{{ item.pollutant }}</td>
                      <td>{{ item.metric }}</td>
                      <td class="r val">{{ item.limit_value }}</td>
                      <td>{{ item.unit }}</td>
                      <td>{{ item.condition || item.category || item.period || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <a-empty v-else description="未抽取到指标行" />
            </a-tab-pane>
            <a-tab-pane key="taxonomy" tab="结构化表格">
              <div style="margin-bottom: 12px">
                <a-input-search
                  v-model:value="taxonomyQuery"
                  placeholder="按代码 / 名称 / 含义搜索（如 0102 或 水浇地）"
                  style="max-width: 360px"
                  allow-clear
                />
              </div>

              <div class="group">
                <div class="group-head">
                  <span class="g-name">限值表</span>
                  <span class="role-chip">limit</span>
                  <span class="g-n">{{ detail.indicators.length }} 行</span>
                </div>
                <div v-if="detail.indicators.length" class="detail-scroll">
                  <table class="tbl detail-table">
                    <thead>
                      <tr>
                        <th style="width: 140px">污染物 / 因子</th>
                        <th>指标</th>
                        <th class="r" style="width: 110px">限值</th>
                        <th style="width: 70px">单位</th>
                        <th>条件</th>
                        <th style="width: 80px">层级</th>
                        <th style="width: 80px">来源表</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in detail.indicators" :key="item.id">
                        <td>{{ item.pollutant }}</td>
                        <td>{{ item.metric }}</td>
                        <td class="r val">{{ item.limit_value }}</td>
                        <td>{{ item.unit }}</td>
                        <td>{{ item.condition || item.category || item.period || '—' }}</td>
                        <td><span class="pill pill-sm" :class="`pill-${item.layer === 'authority' ? 'ok' : item.layer === 'reviewed' ? 'main' : 'gray'}`">{{ item.layer }}</span></td>
                        <td class="mono">{{ item.unit_no }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="group-empty">本文档无限值行。限值类表格拆行后在此按 因子 / 限值 / 单位 / 条件 展示并带专家核验层标记。</div>
              </div>

              <div class="group">
                <div class="group-head">
                  <span class="g-name">分类编码表</span>
                  <span class="role-chip">taxonomy</span>
                  <span class="g-n">{{ taxonomyRowsFiltered.length }} 行（去重后共 {{ taxonomyRows.length }}）</span>
                </div>
                <div v-if="taxonomyRowsFiltered.length" class="detail-scroll">
                  <table class="tbl detail-table tax-table">
                    <thead>
                      <tr>
                        <th style="width: 90px">类别代码</th>
                        <th style="width: 180px">名称</th>
                        <th style="width: 90px">上级</th>
                        <th style="width: 100px">来源表</th>
                        <th>含义（点击行展开全文）</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="row in taxonomyRowsFiltered"
                        :key="row.code"
                        :class="{ 'lv1-row': isLevelOne(row) }"
                        @click="toggleMeaning(row.code)"
                      >
                        <td class="mono lv-code">{{ row.code }}</td>
                        <td class="lv-name">{{ row.name || '—' }}</td>
                        <td class="mono muted">{{ row.parent_code || '—' }}</td>
                        <td class="mono muted">{{ row.unit_no || '—' }}</td>
                        <td class="muted">
                          <div class="meaning-cell" :class="{ open: expandedCodes.has(row.code) }">{{ row.meaning || '—' }}</div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="group-empty">本文档未结构化出分类编码表（非分类学表或未加工）。</div>
                <div v-if="unclassifiedTableCount" class="group-empty" style="margin-top: 10px">
                  另有 <b>{{ unclassifiedTableCount }}</b> 张 other / 未分类表：仅检索不结构化（清单见「结构单元」tab）。
                </div>
              </div>
            </a-tab-pane>
            <a-tab-pane key="runs" tab="运行记录">
              <div class="run-list">
                <div v-for="run in detail.runs" :key="run.run_id" class="run-card">
                  <div>
                    <span class="mono">{{ run.run_id }}</span>
                    <span class="pill pill-sm" :class="`pill-${runMeta[run.status]?.cls || 'gray'}`">{{ runMeta[run.status]?.label }}</span>
                  </div>
                  <div class="run-meta">
                    {{ formatTime(run.started_at) }} → {{ formatTime(run.finished_at) }} · {{ run.started_by }}
                  </div>
                  <div v-if="run.error_message" class="run-error">{{ run.error_message }}</div>
                  <pre v-if="run.result" class="run-result">{{ JSON.stringify(run.result, null, 2) }}</pre>
                </div>
              </div>
              <a-empty v-if="!detail.runs.length" description="暂无持久化运行记录" />
            </a-tab-pane>
          </a-tabs>
            </div>
          </div>
        </template>
        <a-empty v-else-if="!detailLoading" description="详情加载失败" />
      </a-spin>
    </a-modal>

    <a-modal
      :open="settingOpen"
      title="绑定标准规范库"
      :confirm-loading="savingBinding"
      width="620px"
      ok-text="保存绑定"
      cancel-text="取消"
      @ok="saveBinding"
      @cancel="closeSettings"
    >
      <a-alert
        class="binding-alert"
        type="info"
        show-icon
        message="绑定会写入当前部署的系统配置；不同客户环境可选择各自的标准规范知识库。"
      />
      <a-form layout="vertical">
        <a-form-item label="标准规范知识库" required>
          <a-select
            v-model:value="bindingForm.kb_id"
            :options="kbList"
            show-search
            placeholder="选择已上传并索引标准规范的知识库"
            :filter-option="(input, option) => option.label.toLowerCase().includes(input.toLowerCase())"
          />
          <p class="fld-help">标准规范库通常全局共享；绑定后本页将从该 KB 读取 30 类规范文档。</p>
        </a-form-item>
      </a-form>
      <div class="meta-warn">
        <Info :size="14" style="flex: none; margin-top: 3px" />
        <span>切换绑定只影响后续页面读取与加工入口；已抽取指标的 `doc_code / chunk` 溯源保持不变。</span>
      </div>
    </a-modal>
  </div>
</template>

<style lang="less" scoped>
.tbl-scroll {
  overflow-x: auto;
}

/* 表头帮助图标：随 th 的 12px 三级色基调，悬停由 a-tooltip 呈现 */
.th-help {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  cursor: help;

  svg {
    color: var(--color-text-tertiary);
    vertical-align: -2px;
  }
}

.regulation-library .regulation-tbl {
  width: 100%;
  min-width: 1060px;
  table-layout: fixed;

  td {
    overflow-wrap: break-word;
  }
}

/* 列表徽标加同色系边框：以各变体文字色低透明度生成边框色，浅/暗主题自动适配 */
.regulation-tbl .pill {
  border: 1px solid;

  &.pill-main {
    border-color: color-mix(in srgb, var(--main-600) 28%, transparent);
  }

  &.pill-ok {
    border-color: color-mix(in srgb, var(--color-success-700) 28%, transparent);
  }

  &.pill-warn {
    border-color: color-mix(in srgb, var(--color-warning-700) 32%, transparent);
  }

  &.pill-err {
    border-color: color-mix(in srgb, var(--color-error-700) 28%, transparent);
  }

  &.pill-orange {
    border-color: color-mix(in srgb, var(--second-600) 35%, transparent);
  }

  &.pill-gray {
    border-color: var(--gray-200);
  }
}

.doc-cell {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.doc-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-id {
  margin-top: 2px;
  font-size: 11px;
  color: var(--gray-400);
}

.layer-text {
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.run-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  /* 徽标与下方时间戳的间距对齐单元格 9px 垂直 padding，避免上下留白不对称 */
  gap: 9px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.run-time {
  display: block;
  font-size: 11px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.action-row {
  flex-wrap: nowrap;
}

.detail-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0;

  > div {
    padding: 6px 8px;
    border: 1px solid var(--gray-200);
    border-radius: 6px;

    small {
      display: block;
      font-size: 12px;
      color: var(--color-text-tertiary);
    }

    b {
      font-size: 16px;
    }
  }
}

.detail-scroll {
  max-height: 420px;
  overflow: auto;
}

.detail-table-wrap {
  border: 1px solid var(--gray-200);
  border-radius: 6px;
}

.detail-table {
  width: 100%;
  table-layout: fixed;
  min-width: 760px;

  /* 前 4 列（# / 条款、类型、角色）居中；末列无固定宽度，吃满剩余横向空间 */
  th:nth-child(-n + 4),
  td:nth-child(-n + 4) {
    text-align: center;
  }

  /* 末列表头与左对齐的内容保持一致（modal 内无 .ewp 配方，th 默认居中） */
  th:last-child {
    text-align: left;
  }

  th,
  td {
    border-right: 1px solid var(--gray-100);
  }

  th:last-child,
  td:last-child {
    border-right: none;
  }

  th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--gray-50);
  }

  td {
    height: 38px;
  }
}

.muted {
  color: var(--color-text-tertiary);
}

.code {
  font-weight: 500;
  color: var(--main-600);
}

.type-pill {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  background: var(--main-50);
  color: var(--main-600);
}

.detail-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}



.run-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.run-card {
  padding: 10px 12px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
}

.run-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.run-error {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 4px;
  background: var(--color-error-50);
  color: var(--color-error-700);
  font-size: 12px;
  white-space: pre-wrap;
}

.run-result {
  max-height: 220px;
  margin: 8px 0 0;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 4px;
  background: var(--gray-50);
  font-size: 12px;
}

.regulation-skeleton {
  .sk-inp {
    width: 240px;
    height: 30px;
    border-radius: 6px;
  }

  .sk-chip {
    width: 82px;
    height: 28px;
    border-radius: 6px;
  }

  .sk-tbl-row {
    display: flex;
    gap: 14px;
    padding: 10px 16px;

    &.hd {
      border-bottom: 1px solid var(--gray-200);
    }
  }
}

.meta-ident {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 12px;
  margin-bottom: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  background: var(--gray-50);

  .name {
    font-size: 15px;
    font-weight: 600;
  }
}

.meta-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;

  .fld {
    display: flex;
    flex-direction: column;
    gap: 4px;

    label {
      font-size: 12px;
      color: var(--color-text-secondary);
    }

    .fld-help {
      margin: 0;
      font-size: 12px;
      color: var(--color-text-tertiary);
    }
  }
}

.meta-warn {
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

.binding-warning {
  margin-bottom: 12px;
}

.binding-alert {
  margin-bottom: 12px;
}

.fld-help {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

/* 结构化表格分组（限值表 / 分类编码表） */
.group { margin-bottom: 20px; }
.group-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.group-head .g-name { font-weight: 600; font-size: 13.5px; }
.role-chip {
  font-size: 11.5px; font-family: ui-monospace, Consolas, monospace;
  background: rgba(91, 91, 214, 0.08); border: 1px solid rgba(91, 91, 214, 0.25);
  border-radius: 4px; padding: 0 6px; color: #4645c8;
}
.group-head .g-n { color: #9aa0b4; font-size: 12px; font-variant-numeric: tabular-nums; }
.group-empty {
  border: 1px dashed rgba(22, 22, 51, 0.18); border-radius: 8px;
  padding: 12px 16px; color: #6d7286; font-size: 13px;
  background: rgba(0, 0, 0, 0.02);
}
.tax-table tbody tr { cursor: pointer; }
.tax-table tbody tr.lv1-row td { background: rgba(91, 91, 214, 0.05); }
.tax-table tbody tr.lv1-row td:first-child { border-left: 3px solid #5b5bd6; }
.tax-table .lv-code { font-weight: 600; }

.tax-table .lv-name { font-weight: 550; }
.meaning-cell {
  color: #6d7286;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.meaning-cell.open {
  display: block; -webkit-line-clamp: unset; overflow: visible;
  color: inherit;
}


/* 详情弹窗：左 PDF 预览 / 右结构化内容 */
.detail-body { display: flex; gap: 14px; align-items: stretch; }
.pdf-pane { flex: 0 0 46%; min-width: 430px; display: flex; flex-direction: column; }
.pdf-pane-head {
  font-size: 12.5px; color: #6d7286; font-weight: 600;
  margin-bottom: 6px; letter-spacing: 0.02em;
}
.pdf-frame { width: 100%; height: 74vh; border: 1px solid rgba(22, 22, 51, 0.18); border-radius: 8px; background: #525659; }
.pdf-placeholder {
  height: 74vh; display: flex; align-items: center; justify-content: center;
  border: 1px dashed rgba(22, 22, 51, 0.18); border-radius: 8px;
  color: #6d7286; font-size: 13px;
}
.pdf-placeholder.pdf-error { color: #b42318; }
.detail-main { flex: 1 1 0; min-width: 0; overflow-y: auto; max-height: 78vh; padding-right: 4px; }
@media (max-width: 1100px) {
  .detail-body { flex-direction: column; }
  .pdf-pane { min-width: 0; }
  .pdf-frame, .pdf-placeholder { height: 52vh; }
}
</style>


<style lang="less" src="../components/factory-core/factory-ui.less">
</style>


