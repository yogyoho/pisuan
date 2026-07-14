<script setup>
import { computed, onMounted, ref, watch, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { LeftOutlined, RightOutlined, UpOutlined, DownOutlined } from '@ant-design/icons-vue'
import { FileText, Inbox, Plus, X } from 'lucide-vue-next'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { databaseApi } from '@/apis/knowledge_api'
import { useTaskerStore } from '@/stores/tasker'

const props = defineProps({
  task: { type: Object, default: null }
})

const emit = defineEmits(['task-completed', 'task-updated', 'navigate-to-data-sources'])

const taskerStore = useTaskerStore()

// ========== 基础状态 ==========
const loading = ref(false)
const saving = ref(false)
const taskDetail = ref(null)
const activeTab = ref('parse')

// ========== 段落相关状态 ==========
const selectedParagraph = ref(null)
const detailEditMode = ref(false)
const editTab = ref('form') // 'form' | 'json'
const jsonEditValue = ref('')
const chapterFilterKey = ref(null)

// ========== 表格相关状态 ==========
const structuredBlocks = ref([])

// ========== 章节导航 ==========
const chapterTree = ref([])
const chapterTreeExpandedKeys = ref([])
const chapterNavCollapsed = ref(false)
const tableDetailExpanded = ref(true)
const tableSchemaExpanded = ref(false)
const tableStructRowsExpanded = ref(false)

// ========== Tab 2 泛化相关 ==========
const selectedParamPara = ref(null)

// ========== 未识别实体相关 ==========
const unrecognizedEntities = ref([])
const rawSlots = ref([])
const groupedUnrecognizedEntities = ref({})
const loadingUnrecognizedEntities = ref(false)
const selectedEntities = ref([])
const entityCategories = ref([])
const entityEditModalVisible = ref(false)
const editingEntity = ref(null)
const activeEntityCategory = ref('')
const proposedDomainCode = ref('')
const matchedCount = ref(0)
const newCount = ref(0)

// ========== 半自动审核状态 ==========
const reviewedParagraphIds = ref(new Set())
const showOnlyUnreviewed = ref(false)

// ========== 分类筛选 ==========
const classifyFilter = ref(null)

// ========== 知识库 ==========
const lightragKnowledgeBases = ref([])
const selectedKnowledgeBaseId = ref(null)
const loadingKnowledgeBases = ref(false)

// ========== 步骤完成追踪 ==========
const stepCompleted = ref({ parse: false, generalize: false, entities: false, commit: false })

// ========== 常量 ==========
const CLASSIFY_TYPE_MAP = {
  heading: { label: '标题', color: 'green' },
  table: { label: '表格', color: 'blue' },
  formula: { label: '公式', color: 'purple' },
  figure: { label: '图片', color: 'cyan' },
  list: { label: '列表', color: 'orange' },
  legal_reference: { label: '标准引用', color: 'geekblue' },
  parameter: { label: '参数', color: 'gold' },
  narrative: { label: '叙述', color: 'default' },
}

const SLOT_TYPE_MAP = {
  parameter: { label: '参数型', color: 'blue' },
  enum: { label: '枚举型', color: 'green' },
  descriptive: { label: '描述型', color: 'orange' },
  reference: { label: '引用型', color: 'purple' },
}

const TABLE_ROLE_MAP = {
  key: { label: '键', color: 'cyan' },
  structural: { label: '结构', color: 'blue' },
  classification: { label: '分类', color: 'geekblue' },
  data: { label: '数据', color: 'gold' },
  reference: { label: '引用', color: 'purple' },
  derived: { label: '派生', color: 'orange' },
}

const TABLE_TYPE_MAP = {
  key_value: { label: '键值对', color: 'blue' },
  monitoring: { label: '监测数据', color: 'green' },
  compliance: { label: '达标分析', color: 'orange' },
  standard_limit: { label: '标准限值', color: 'purple' },
}

const LEGAL_TYPE_MAP = {
  law: '法律',
  admin_regulation: '行政法规',
  local_regulation: '地方性法规',
  ministry_rule: '部门规章',
  local_rule: '地方规章',
  technical_standard: '技术规范',
  national_plan: '国家规划',
  local_plan: '地方规划',
  project_material: '项目资料',
}

const LEGAL_SCOPE_MAP = {
  national: { label: '国家', color: 'blue' },
  regional: { label: '地方', color: 'orange' },
  project: { label: '项目', color: 'default' },
}

const SUBTYPE_MAP = {
  // table
  key_value: '键值对',
  monitoring: '监测数据',
  compliance: '达标分析',
  standard_limit: '标准限值',
  // legal_reference
  law: '法律',
  admin_regulation: '行政法规',
  technical_standard: '技术规范',
  ministry_rule: '部门规章',
  general: '其他',
  // parameter
  measurable: '可量化',
  reusable: '可复用',
  descriptive: '描述性',
  // narrative
  conclusion: '结论',
  methodology: '方法',
  summary: '概况',
  background: '背景',
  description: '描述',
}

const getConfidenceColor = (conf) => {
  if (conf >= 0.8) return '#52c41a'
  if (conf >= 0.6) return '#faad14'
  return '#ff4d4f'
}

// ========== 计算属性 ==========
const sourceParagraphs = computed(() => taskDetail.value?.source_paragraphs || [])

const classifyStats = computed(() => {
  const stats = {}
  sourceParagraphs.value.forEach(p => {
    const ct = p.classify_type || 'unknown'
    stats[ct] = (stats[ct] || 0) + 1
  })
  return stats
})

const parameterParagraphs = computed(() =>
  sourceParagraphs.value.filter(p => p.classify_type === 'parameter')
)

const slotSummary = computed(() => {
  const map = {}
  sourceParagraphs.value.forEach(p => {
    const slots = p.template?.slots || []
    slots.forEach(s => {
      if (s.name && s.value != null) {
        map[s.name] = { value: s.value, type: s.type || 'parameter', unit: s.unit || '', entity_ref: s.entity_ref || '' }
      }
    })
  })
  return map
})

const filteredParagraphs = computed(() => {
  let result = sourceParagraphs.value
  if (classifyFilter.value) {
    result = result.filter(p => p.classify_type === classifyFilter.value)
  }
  if (chapterFilterKey.value && chapterFilterKey.value !== 'all') {
    const node = findNodeInTree(chapterTree.value, chapterFilterKey.value)
    if (node) {
      const paraIds = new Set(collectChapterParagraphs(node).map(p => p.id))
      result = result.filter(p => paraIds.has(p.id))
    }
  }
  if (showOnlyUnreviewed.value) {
    result = result.filter(p => needsReview(p) && !reviewedParagraphIds.value.has(p.id))
  }
  return result
})

const filteredParamParagraphs = computed(() => {
  let result = parameterParagraphs.value
  if (showOnlyUnreviewed.value) {
    result = result.filter(p => needsReview(p) && !reviewedParagraphIds.value.has(p.id))
  }
  return result
})

const selectedTableBlock = computed(() => {
  if (!selectedParagraph.value) return null
  const para = selectedParagraph.value
  const blocks = structuredBlocks.value || []
  if (!blocks.length) return null
  const paraPath = para.section_path || []
  const paraPathStr = Array.isArray(paraPath) ? paraPath.join('.') : String(paraPath || '')
  // 按 section_path 匹配
  if (paraPathStr) {
    const match = blocks.find(b => b.type === 'table' && (b.section_path === paraPathStr || b.section_path?.join('.') === paraPathStr))
    if (match) return match
  }
  // 按 content 中 <td> 文本匹配
  const content = para.content || ''
  const tdTexts = content.match(/<td[^>]*>([^<]+)<\/td>/g)?.slice(0, 3).map(m => m.replace(/<[^>]+>/g, '')) || []
  if (tdTexts.length) {
    const match = blocks.find(b => {
      if (b.type !== 'table') return false
      const rows = b.rows || []
      if (!rows.length) return false
      const firstRow = Array.isArray(rows[0]) ? rows[0] : Object.values(rows[0] || {})
      return tdTexts.every(t => firstRow.some(c => String(c).includes(t)))
    })
    if (match) return match
  }
  // fallback: 唯一表格直接返回
  const tableBlocks = blocks.filter(b => b.type === 'table')
  if (tableBlocks.length === 1) return tableBlocks[0]
  return null
})

const tableBlockColumns = computed(() => {
  const block = selectedTableBlock.value
  if (!block?.headers?.length) return []
  return block.headers.map((h, i) => ({ title: h, dataIndex: `col_${i}`, ellipsis: true }))
})

const tableBlockRows = computed(() => {
  const block = selectedTableBlock.value
  if (!block?.rows?.length || !block?.headers?.length) return []
  const headers = block.headers
  return block.rows.map((row, ri) => {
    const obj = { _key: ri }
    if (Array.isArray(row)) {
      headers.forEach((h, i) => { obj[`col_${i}`] = row[i] ?? '' })
    } else {
      headers.forEach((h, i) => { obj[`col_${i}`] = row[h] ?? '' })
    }
    return obj
  })
})

const reviewProgress = computed(() => {
  const reviewable = sourceParagraphs.value.filter(p => needsReview(p))
  const reviewed = reviewable.filter(p => reviewedParagraphIds.value.has(p.id))
  return {
    total: reviewable.length,
    reviewed: reviewed.length,
    percent: reviewable.length ? Math.round(reviewed.length / reviewable.length * 100) : 100
  }
})

const highConfidenceCount = computed(() => {
  return sourceParagraphs.value.filter(p => {
    const ct = p.classify_type
    if (!ct || ct === 'heading' || ct === 'narrative') return false
    const qs = p.template?.quality_score
    return qs != null && qs >= 0.7 && !reviewedParagraphIds.value.has(p.id)
  }).length
})

const domainLabel = computed(() => taskDetail.value?.domain_label || '')
const reportTypeLabel = computed(() => {
  const code = taskDetail.value?.report_type_code
  if (!code || code === '通用') return ''
  return code
})

// ========== 置信度 & 审核 ==========

const isHtmlTable = (str) => typeof str === 'string' && /<table[\s>]/i.test(str)

const needsReview = (para) => {
  const ct = para.classify_type
  if (!ct || ct === 'heading' || ct === 'narrative') return false
  const qs = para.template?.quality_score
  if (qs == null) return true
  return qs < 0.6
}

const confirmHighConfidenceAndSave = async () => {
  let count = 0
  sourceParagraphs.value.forEach(p => {
    const qs = p.template?.quality_score
    if (qs != null && qs >= 0.7 && !reviewedParagraphIds.value.has(p.id) && p.classify_type) {
      reviewedParagraphIds.value.add(p.id)
      count++
    }
  })
  if (count === 0) {
    message.info('没有需要确认的高置信度段落')
    return
  }
  const ok = await doSaveParagraphs()
  if (ok) message.success(`已确认 ${count} 个高置信度段落并保存`)
}

// ========== 章节树 ==========
const buildChapterTree = (paragraphs) => {
  const treeMap = new Map()
  const rootNodes = []
  const titleMap = new Map()
  paragraphs.forEach(para => {
    if (!para.is_title || !para.title) return
    const rawPath = para.section_path || para.path || []
    const sectionPath = Array.isArray(rawPath) ? rawPath.map(p => String(p)) : [String(rawPath || '')]
    if (!sectionPath.length || !sectionPath[0]) return
    const key = sectionPath.join('.')
    if (!titleMap.has(key)) titleMap.set(key, para.title)
  })
  paragraphs.forEach(para => {
    const rawPath = para.section_path || para.path || []
    const sectionPath = Array.isArray(rawPath) ? rawPath.map(p => String(p)) : [String(rawPath || '')]
    if (!sectionPath.length || !sectionPath[0]) {
      const key = 'uncategorized'
      if (!treeMap.has(key)) { const node = { key, title: '未分类段落', children: [], paragraphs: [] }; treeMap.set(key, node); rootNodes.push(node) }
      treeMap.get(key).paragraphs.push(para)
      return
    }
    let currentPath = []
    sectionPath.forEach((segment) => {
      currentPath.push(segment)
      const key = currentPath.join('.')
      if (!treeMap.has(key)) {
        const pathTitle = titleMap.get(key) || segment
        const node = { key, title: pathTitle, children: [], paragraphs: [] }
        treeMap.set(key, node)
        if (currentPath.length === 1) rootNodes.push(node)
        else { const parentKey = currentPath.slice(0, -1).join('.'); const parent = treeMap.get(parentKey); if (parent) parent.children.push(node) }
      }
      if (currentPath.length === sectionPath.length) treeMap.get(key).paragraphs.push(para)
    })
  })
  return rootNodes
}

const collectTreeKeys = (nodes) => {
  const keys = []
  const stack = [...nodes]
  while (stack.length > 0) {
    const node = stack.pop()
    if (node?.key) keys.push(node.key)
    if (Array.isArray(node?.children)) for (let i = node.children.length - 1; i >= 0; i--) stack.push(node.children[i])
  }
  return keys
}

const findNodeInTree = (nodes, targetKey) => {
  for (const node of nodes || []) {
    if (node.key === targetKey) return node
    if (node.children?.length) { const found = findNodeInTree(node.children, targetKey); if (found) return found }
  }
  return null
}

const collectChapterParagraphs = (node) => {
  const result = [...(node.paragraphs || [])]
  for (const child of node.children || []) result.push(...collectChapterParagraphs(child))
  return result
}

// ========== 加载任务详情 ==========
const fetchTaskDetail = async (taskId) => {
  loading.value = true
  try {
    const detail = await domainFactoryApi.getTaskDetail(taskId)
    taskDetail.value = detail
    structuredBlocks.value = detail?.structured_blocks || []
    if (detail?.source_paragraphs?.length > 0) {
      chapterTree.value = buildChapterTree(detail.source_paragraphs)
      chapterTreeExpandedKeys.value = collectTreeKeys(chapterTree.value)
    }
    setTimeout(() => { loadUnrecognizedEntities(taskId).catch(() => {}) }, 100)
  } catch (e) {
    console.error('Failed to fetch task detail:', e)
    message.error('加载任务详情失败')
  } finally {
    loading.value = false
  }
}

// ========== 段落点击 ==========
const handleParagraphClick = (para) => {
  selectedParagraph.value = para
  detailEditMode.value = false
  tableDetailExpanded.value = true
  tableSchemaExpanded.value = false
  tableStructRowsExpanded.value = false
}

const handleToggleEditMode = async () => {
  if (detailEditMode.value) {
    if (editTab.value === 'json') {
      try {
        const parsed = JSON.parse(jsonEditValue.value)
        Object.assign(selectedParagraph.value, parsed)
      } catch {
        message.error('JSON 格式错误，请检查')
        return
      }
    }
    const saved = await doSaveParagraphs()
    if (saved) stepCompleted.value.parse = true
    detailEditMode.value = false
  } else {
    editTab.value = 'form'
    jsonEditValue.value = JSON.stringify(selectedParagraph.value, null, 2)
    detailEditMode.value = true
  }
}

const handleParamParaClick = (para) => {
  selectedParamPara.value = para
}

// ========== Tab 切换 ==========
const STEP_KEYS = ['parse', 'generalize', 'entities', 'commit']
const currentStep = computed(() => STEP_KEYS.indexOf(activeTab.value))

const goToStep = (index) => {
  const key = STEP_KEYS[index]
  if (!key) return
  activeTab.value = key
  if (key === 'parse') selectedParagraph.value = null
  if (key === 'generalize') selectedParamPara.value = null
}


// ========== 保存段落修改 ==========
const doSaveParagraphs = async () => {
  if (!taskDetail.value?.id) return false
  saving.value = true
  try {
    await domainFactoryApi.saveTaskStep(taskDetail.value.id, {
      step: 'structured',
      payload: {
        source_paragraphs: taskDetail.value.source_paragraphs,
        structured_blocks: structuredBlocks.value,
      }
    })
    emit('task-updated')
    return true
  } catch {
    message.error('保存失败')
    return false
  } finally {
    saving.value = false
  }
}

// ========== Tab 2: 保存段落泛化 ==========
const handleSaveParaTemplate = async () => {
  if (!taskDetail.value?.id || !selectedParamPara.value) return
  const ok = await doSaveParagraphs()
  if (ok) {
    stepCompleted.value.generalize = true
    reviewedParagraphIds.value.add(selectedParamPara.value.id)
    message.success('模板修改已保存')
  }
}

// ========== 修改 slot 字段 ==========
const updateSlotField = (paraId, slotName, field, value) => {
  const para = sourceParagraphs.value.find(p => p.id === paraId)
  if (!para?.template?.slots) return
  const slot = para.template.slots.find(s => s.name === slotName)
  if (slot) slot[field] = value
}

const addSlot = (paraId) => {
  const para = sourceParagraphs.value.find(p => p.id === paraId)
  if (!para?.template) return
  if (!para.template.slots) para.template.slots = []
  const idx = para.template.slots.length + 1
  const newSlot = {
    name: `slot_${idx}`,
    type: 'parameter',
    value: '',
    unit: '',
    entity_ref: '',
  }
  para.template.slots.push(newSlot)
  if (para.template.generalized) {
    para.template.generalized += ` {{${newSlot.name}}}`
  }
}

const removeSlot = (paraId, slotName) => {
  const para = sourceParagraphs.value.find(p => p.id === paraId)
  if (!para?.template?.slots) return
  const idx = para.template.slots.findIndex(s => s.name === slotName)
  if (idx === -1) return
  const slot = para.template.slots[idx]
  const restoreValue = slot.value || ''
  para.template.slots.splice(idx, 1)
  if (para.template.generalized) {
    para.template.generalized = para.template.generalized
      .replace(new RegExp(`\\{\\{${slotName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\}\\}`, 'g'), restoreValue)
  }
}

// ========== 模板文本选中抽取 Slot ==========
const templateSelection = ref({ text: '', left: 0, top: 0, visible: false })

const onTemplateMouseUp = () => {
  setTimeout(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !sel.toString().trim()) {
      templateSelection.value = { text: '', left: 0, top: 0, visible: false }
      return
    }
    const selText = sel.toString().trim()
    const para = selectedParamPara.value
    if (!para?.template?.generalized) {
      templateSelection.value = { text: '', left: 0, top: 0, visible: false }
      return
    }
    // 检查选中文字是否在泛化模板区域
    const range = sel.getRangeAt(0)
    const container = document.querySelector('.template-text')
    if (!container || !container.contains(range.commonAncestorContainer)) {
      templateSelection.value = { text: '', left: 0, top: 0, visible: false }
      return
    }
    // 检查选中文字是否包含已有的 {{slot}} 占位符
    if (/\{\{.*?\}\}/.test(selText)) {
      templateSelection.value = { text: '', left: 0, top: 0, visible: false }
      return
    }
    const rect = range.getBoundingClientRect()
    templateSelection.value = {
      text: selText,
      left: rect.left + rect.width / 2,
      top: rect.top - 40,
      visible: true,
    }
  }, 10)
}

const extractSlotFromSelection = () => {
  const para = selectedParamPara.value
  if (!para?.template) return
  if (!para.template.slots) para.template.slots = []

  const selText = templateSelection.value.text
  if (!selText) return

  // 在 generalized 文本中定位并替换选中文字
  const escaped = selText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(escaped)
  const match = para.template.generalized.match(regex)
  if (!match) {
    message.warning('未在模板中找到选中文字')
    templateSelection.value = { text: '', left: 0, top: 0, visible: false }
    return
  }

  const idx = para.template.slots.length + 1
  const slotName = `slot_${idx}`
  para.template.generalized = para.template.generalized.replace(regex, `{{${slotName}}}`)

  para.template.slots.push({
    name: slotName,
    type: 'parameter',
    value: selText,
    unit: '',
    entity_ref: '',
  })

  templateSelection.value = { text: '', left: 0, top: 0, visible: false }
  message.success(`已抽取 "${selText.slice(0, 20)}${selText.length > 20 ? '...' : ''}" 为 ${slotName}`)
}

const dismissSelection = () => {
  templateSelection.value = { text: '', left: 0, top: 0, visible: false }
}

// ========== 知识库 ==========
const loadLightragKnowledgeBases = async () => {
  loadingKnowledgeBases.value = true
  try {
    const response = await databaseApi.getDatabases()
    lightragKnowledgeBases.value = (response.databases || []).filter(db => db.kb_type === 'milvus' || db.type === 'milvus')
    if (lightragKnowledgeBases.value.length === 1) {
      selectedKnowledgeBaseId.value = lightragKnowledgeBases.value[0].kb_id
    }
  } catch (e) {
    console.error('加载知识库列表失败', e)
  } finally {
    loadingKnowledgeBases.value = false
  }
}

// ========== 入库 ==========
const handleCommit = async () => {
  if (!taskDetail.value?.id) return
  if (!selectedKnowledgeBaseId.value) {
    message.warning('请先选择目标知识库')
    return
  }
  Modal.confirm({
    title: '确认入库？',
    content: () => {
      const selectedKB = lightragKnowledgeBases.value.find(kb => kb.kb_id === selectedKnowledgeBaseId.value)
      return [
        h('p', { style: 'margin-bottom: 12px' }, '提交后模板将同步至知识图谱，确保已完成校验。'),
        h('p', {}, ['目标知识库：', h('strong', selectedKB?.name || selectedKnowledgeBaseId.value)])
      ]
    },
    okText: '确认入库',
    cancelText: '返回修改',
    onOk: async () => {
      saving.value = true
      try {
        await domainFactoryApi.saveTaskStep(taskDetail.value.id, {
          step: 'structured',
          payload: {
            source_paragraphs: taskDetail.value.source_paragraphs,
            structured_blocks: structuredBlocks.value,
          }
        })

        const baseInfo = {}
        Object.entries(slotSummary.value).forEach(([k, v]) => { baseInfo[k] = v.value })

        const result = await domainFactoryApi.commitTask(taskDetail.value.id, {
          form: baseInfo,
          structured: structuredBlocks.value,
          source_paragraphs: taskDetail.value.source_paragraphs,
          knowledge_base_id: selectedKnowledgeBaseId.value
        })

        if (result?.task?.ingest_task_id) {
          taskerStore.registerQueuedTask({
            task_id: result.task.ingest_task_id,
            name: `知识工厂入库: ${taskDetail.value?.file_name || '未知文件'}`,
            task_type: 'domain_factory_commit',
            message: '数据正在同步到知识库',
            payload: {
              task_id: taskDetail.value.id,
              knowledge_base_id: selectedKnowledgeBaseId.value,
            }
          })
        }

        stepCompleted.value.commit = true
        emit('task-completed', { task_id: taskDetail.value.id, result })
        message.success('入库任务已提交')
      } catch (e) {
        message.error('入库失败：' + (e.message || e))
      } finally {
        saving.value = false
      }
    }
  })
}

// ========== 未识别实体 ==========
const entityTableColumns = [
  { title: '类型', key: 'type', width: 80 },
  { title: '名称', key: 'name_cn', ellipsis: true },
  { title: '同义词', key: 'synonyms', ellipsis: true },
  { title: '置信度', key: 'confidence', width: 80 },
  { title: '操作', key: 'action', width: 120 },
]

const loadUnrecognizedEntities = async (taskId) => {
  if (!taskId) return
  loadingUnrecognizedEntities.value = true
  try {
    const result = await domainFactoryApi.getUnrecognizedEntities(taskId)
    rawSlots.value = result.raw_slots || []
    matchedCount.value = result.matched_count || 0
    newCount.value = result.new_count || 0
    proposedDomainCode.value = result.domain_code || ''

    const entities = result.entities || []
    unrecognizedEntities.value = entities
    const groups = {}
    const cats = new Set()
    entities.forEach(e => {
      const cat = e.category || '其他'
      cats.add(cat)
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(e)
    })
    groupedUnrecognizedEntities.value = groups
    entityCategories.value = Array.from(cats)
    if (cats.size > 0) activeEntityCategory.value = Array.from(cats)[0]
  } catch (e) {
    console.error('加载未识别实体失败', e)
  } finally {
    loadingUnrecognizedEntities.value = false
  }
}

const openEntityEditModal = (record) => {
  editingEntity.value = { ...record }
  entityEditModalVisible.value = true
}

const saveEntity = async () => {
  if (!editingEntity.value) return
  const entity = editingEntity.value
  if (!entity.entity_key || !entity.name_cn) {
    message.warning('实体名称和 Entity Key 为必填项')
    return
  }
  entity._confirmed = true
  try {
    await domainFactoryApi.confirmProposedEntities(taskDetail.value.id, [entity])
    entityEditModalVisible.value = false
    message.success(`实体 "${entity.name_cn}" 已保存`)
    await loadUnrecognizedEntities(taskDetail.value.id)
  } catch {
    message.error('保存实体失败')
  }
}

const saveEntityDirectly = async (record) => {
  record._confirmed = true
  try {
    const result = await domainFactoryApi.confirmProposedEntities(taskDetail.value.id, [record])
    message.success(`实体 "${record.name_cn || record.entity_key}" 已保存`)
    if (result.remapped > 0) {
      message.info(`${result.remapped} 个待审核任务的 slot 已重新映射`)
    }
    await loadUnrecognizedEntities(taskDetail.value.id)
  } catch {
    message.error('保存失败')
  }
}

const batchSaveEntities = async () => {
  if (!selectedEntities.value.length) return
  try {
    const entities = selectedEntities.value.map(e => ({ ...e, _confirmed: true }))
    const result = await domainFactoryApi.confirmProposedEntities(taskDetail.value.id, entities)
    message.success(`已保存 ${result.saved || 0} 个实体`)
    if (result.remapped > 0) {
      message.info(`${result.remapped} 个待审核任务的 slot 已重新映射`)
    }
    selectedEntities.value = []
    await loadUnrecognizedEntities(taskDetail.value.id)
    stepCompleted.value.entities = true
  } catch {
    message.error('批量保存失败')
  }
}

// ========== 高亮模板中的 slot ==========
const highlightedGeneralized = computed(() => {
  const text = selectedParamPara.value?.template?.generalized || ''
  if (!text) return ''
  return text.replace(/(\{\{[^}]+\}\})/g, '<mark>$1</mark>')
})

// ========== 生命周期 ==========
onMounted(async () => {
  if (props.task?.id) {
    await fetchTaskDetail(props.task.id)
  }
  await loadLightragKnowledgeBases()
})

watch(() => props.task, async (newTask) => {
  if (newTask?.id) {
    activeTab.value = 'parse'
    selectedParagraph.value = null
    selectedParamPara.value = null
    reviewedParagraphIds.value = new Set()
    stepCompleted.value = { parse: false, generalize: false, entities: false, commit: false }
    await fetchTaskDetail(newTask.id)
  }
}, { deep: true })
</script>

<template>
  <div v-if="loading" class="loading-state">
    <a-spin size="large" tip="加载任务详情..." />
  </div>
  <div v-else-if="!taskDetail" class="empty-state">
    <Inbox :size="40" :stroke-width="1.2" class="empty-state-icon" />
    <span>请选择一个待校验的任务</span>
  </div>
  <div v-else class="etl-workbench">
    <!-- ========== Header: 状态栏 ========== -->
    <div class="workbench-header">
      <div>
        <h3>ETL 清洗工作台</h3>
        <p>{{ taskDetail.file_name }}</p>
      </div>
      <a-space :size="12" class="header-status">
        <a-tag v-if="domainLabel" color="blue">{{ domainLabel }}</a-tag>
        <a-tag v-if="reportTypeLabel" color="green">{{ reportTypeLabel }}</a-tag>
        <span class="status-item">
          AI 置信度:
          <span :style="{ color: getConfidenceColor((taskDetail.ai_confidence || 0) / 100), fontWeight: 600 }">
            {{ taskDetail.ai_confidence || 0 }}%
          </span>
        </span>
        <span class="status-item" v-if="reviewProgress.total > 0">
          审核:
          <span :style="{ color: reviewProgress.percent >= 80 ? '#52c41a' : '#faad14', fontWeight: 600 }">
            {{ reviewProgress.reviewed }}/{{ reviewProgress.total }}
          </span>
        </span>
      </a-space>
    </div>

    <!-- 步骤流程导航 -->
    <div class="flow-steps">
      <div
        v-for="(step, idx) in [
          { key: 'parse', title: '结构化元数据校验', icon: 'FileSearch' },
          { key: 'generalize', title: 'Slot 变量校验', icon: 'Code' },
          { key: 'entities', title: '实体确认', icon: 'Group' },
          { key: 'commit', title: '入库确认', icon: 'CloudUpload' },
        ]"
        :key="step.key"
        class="flow-step"
        :class="{
          active: activeTab === step.key,
          done: stepCompleted[step.key],
          clickable: idx <= currentStep + 1
        }"
        @click="idx <= currentStep + 1 && goToStep(idx)"
      >
        <span class="flow-step-num">{{ idx + 1 }}</span>
        <span class="flow-step-title">{{ step.title }}</span>
        <span v-if="idx < 3" class="flow-step-arrow">›</span>
      </div>
    </div>

    <!-- ========== 流程内容面板 ========== -->
    <div class="flow-panel">

      <!-- ================================================================ -->
      <!-- Step 1: 结构化元数据校验                                            -->
      <!-- ================================================================ -->
      <div v-show="activeTab === 'parse'" class="flow-content">
        <div class="tab-header-bar">
          <a-space :size="8">
            <span class="classify-filter-label">类型筛选:</span>
            <a-radio-group v-model:value="classifyFilter" size="small" button-style="solid">
              <a-radio-button :value="null">全部</a-radio-button>
              <a-radio-button v-for="(info, key) in CLASSIFY_TYPE_MAP" :key="key" :value="key">
                {{ info.label }} <span class="classify-count">{{ classifyStats[key] || 0 }}</span>
              </a-radio-button>
            </a-radio-group>
          </a-space>
          <a-space :size="8">
            <a-switch v-model:checked="showOnlyUnreviewed" size="small" />
            <span style="font-size: 11px; color: var(--gray-500)">仅待审核</span>
            <a-button size="small" @click="confirmHighConfidenceAndSave" :loading="saving" :disabled="highConfidenceCount === 0">
              确认高置信度并保存 ({{ highConfidenceCount }})
            </a-button>
          </a-space>
        </div>

        <div v-if="reviewProgress.total > 0" class="review-progress">
          <a-progress :percent="reviewProgress.percent" :stroke-color="reviewProgress.percent >= 80 ? '#52c41a' : '#1677ff'" size="small" :format="() => `${reviewProgress.reviewed}/${reviewProgress.total}`" />
        </div>

        <a-row :gutter="16" class="parse-row">
          <!-- 左栏: 章节导航 -->
          <a-col v-if="chapterTree.length" :span="chapterNavCollapsed ? 1 : 4">
            <a-card size="small" class="fixed-height-card chapter-nav-card">
              <template #title>
                <div v-if="!chapterNavCollapsed" class="chapter-nav-title">
                  <span style="font-size: 13px">章节导航</span>
                </div>
              </template>
              <template #extra>
                <a-button type="text" size="small" class="chapter-toggle-btn" @click="chapterNavCollapsed = !chapterNavCollapsed">
                  <LeftOutlined v-if="!chapterNavCollapsed" style="font-size: 10px" />
                  <RightOutlined v-else style="font-size: 10px" />
                </a-button>
              </template>
              <div v-if="!chapterNavCollapsed" class="scroll-pane chapter-tree-pane">
                <a-tree
                  :tree-data="chapterTree"
                  :field-names="{ children: 'children', title: 'title', key: 'key' }"
                  :selected-keys="chapterFilterKey ? [chapterFilterKey] : []"
                  :default-expand-all="true"
                  size="small"
                  :show-line="false"
                  @select="(keys) => { chapterFilterKey = keys?.[0] || null }"
                >
                  <template #title="{ dataRef }">
                    <span class="chapter-tree-node">{{ dataRef?.title || '未命名' }}</span>
                  </template>
                </a-tree>
                <a-button v-if="chapterFilterKey" type="link" size="small" style="margin-top: 8px; font-size: 11px" @click="chapterFilterKey = null">清除筛选</a-button>
              </div>
            </a-card>
          </a-col>

          <!-- 中栏: 段落列表 -->
          <a-col :span="(chapterTree.length ? (chapterNavCollapsed ? 11 : 8) : 12)">
            <a-card size="small" class="paragraph-viewer-card">
              <template #title><span style="font-size: 13px">段落列表 ({{ filteredParagraphs.length }})</span></template>
              <div class="scroll-pane">
                <div
                  v-for="para in filteredParagraphs"
                  :key="para.id"
                  class="paragraph"
                  :class="{
                    selected: selectedParagraph && selectedParagraph.id === para.id,
                    'para-reviewed': reviewedParagraphIds.has(para.id),
                    'para-needs-review': needsReview(para) && !reviewedParagraphIds.has(para.id)
                  }"
                  @click="handleParagraphClick(para)"
                >
                  <div class="para-title">
                    <a-tag v-if="para.classify_type && CLASSIFY_TYPE_MAP[para.classify_type]" size="small" :color="CLASSIFY_TYPE_MAP[para.classify_type].color">
                      {{ CLASSIFY_TYPE_MAP[para.classify_type].label }}
                    </a-tag>
                    <a-tag v-if="para.section_path?.length" size="small" color="default" class="para-section-tag">
                      {{ Array.isArray(para.section_path) ? para.section_path.join('/') : para.section_path }}
                    </a-tag>
                    <a-tag v-for="tag in (para.classify_tags || [])" :key="tag" size="small" color="processing" class="para-subtype-tag">
                      {{ SUBTYPE_MAP[tag] || tag }}
                    </a-tag>
                    <span v-if="para.classify_type && para.classify_type !== 'heading' && para.classify_type !== 'narrative' && para.template?.quality_score != null" class="para-confidence" :style="{ color: getConfidenceColor(para.template.quality_score) }">
                      {{ Math.round(para.template.quality_score * 100) }}%
                    </span>
                    <span v-if="reviewedParagraphIds.has(para.id)" class="para-reviewed-badge">✓</span>
                  </div>
                  <div class="para-content">{{ para.title || para.content }}</div>
                  <div v-if="para.classify_type === 'narrative' && para.template?.summary" class="para-summary">
                    {{ para.template.summary }}
                  </div>
                </div>
              </div>
            </a-card>
          </a-col>

          <!-- 右栏: 类型化详情面板 -->
          <a-col :span="12">
            <a-card size="small" class="detail-panel-card">
              <template #title>
                <a-space :size="8" align="center">
                  <span style="font-size: 13px">结构化详情</span>
                  <a-tag v-if="selectedParagraph?.classify_type && CLASSIFY_TYPE_MAP[selectedParagraph.classify_type]" size="small" :color="CLASSIFY_TYPE_MAP[selectedParagraph.classify_type].color">
                    {{ CLASSIFY_TYPE_MAP[selectedParagraph.classify_type].label }}
                  </a-tag>
                </a-space>
              </template>
              <template #extra>
                <a-space :size="4">
                  <a-button v-if="selectedParagraph" size="small" :type="detailEditMode ? 'primary' : 'default'" @click="handleToggleEditMode">
                    {{ detailEditMode ? '保存' : '编辑' }}
                  </a-button>
                  <a-button v-if="selectedParagraph && reviewedParagraphIds.has(selectedParagraph.id)" size="small" danger :loading="saving" @click="async () => { reviewedParagraphIds.delete(selectedParagraph.id); const ok = await doSaveParagraphs(); if (ok) stepCompleted.parse = true }">撤销审核</a-button>
                  <a-button v-else-if="selectedParagraph && !detailEditMode" size="small" type="primary" :loading="saving" @click="async () => { reviewedParagraphIds.add(selectedParagraph.id); const ok = await doSaveParagraphs(); if (ok) stepCompleted.parse = true }">确认审核</a-button>
                  <a-button v-if="selectedParagraph?.classify_type === 'parameter' && selectedParagraph?.template?.generalized" size="small" type="link" @click="activeTab = 'generalize'; selectedParamPara = selectedParagraph">前往 → Slot变量校验</a-button>
                </a-space>
              </template>

              <div v-if="!selectedParagraph" class="detail-empty">
                <FileText :size="36" :stroke-width="1.2" style="color: var(--gray-300, #c0c4cc)" />
                <a-empty description="请点击段落查看详情" :image="false" />
              </div>

              <!-- 编辑模式 -->
              <div v-else-if="detailEditMode" class="detail-section">
                <a-radio-group v-model:value="editTab" size="small" button-style="solid" style="margin-bottom: 8px; font-size: 13px">
                  <a-radio-button value="form">表单编辑</a-radio-button>
                  <a-radio-button value="json">JSON 编辑</a-radio-button>
                </a-radio-group>

                <!-- 表单编辑 -->
                <template v-if="editTab === 'form'">
                  <div class="detail-label" style="margin-bottom: 4px">编辑内容</div>
                  <a-textarea v-model:value="selectedParagraph.content" :auto-size="{ minRows: 3, maxRows: 12 }" style="font-size: 13px" />
                  <div style="margin-top: 8px">
                    <div class="detail-label" style="margin-bottom: 4px">分类</div>
                    <a-select
                      :value="selectedParagraph.classify_type"
                      @change="(v) => { selectedParagraph.classify_type = v }"
                      style="width: 100%; font-size: 13px"
                    >
                      <a-select-option v-for="(info, key) in CLASSIFY_TYPE_MAP" :key="key" :value="key">{{ info.label }}</a-select-option>
                    </a-select>
                  </div>
                </template>

                <!-- JSON 编辑 -->
                <template v-else>
                  <div class="detail-label" style="margin-bottom: 4px">段落结构化 JSON</div>
                  <a-textarea v-model:value="jsonEditValue" :auto-size="{ minRows: 8, maxRows: 24 }" style="font-family: monospace; font-size: 12px" />
                </template>
              </div>

              <!-- heading 类型 -->
              <div v-else-if="selectedParagraph.classify_type === 'heading'" class="detail-section">
                <div class="detail-field"><span class="detail-label">标题</span><span class="detail-value">{{ selectedParagraph.title }}</span></div>
                <div class="detail-field"><span class="detail-label">章节路径</span><span class="detail-value">{{ Array.isArray(selectedParagraph.section_path) ? selectedParagraph.section_path.join(' / ') : selectedParagraph.section_path }}</span></div>
                <div class="detail-field" v-if="selectedParagraph.parent_title"><span class="detail-label">父章节</span><span class="detail-value">{{ selectedParagraph.parent_title }}</span></div>
              </div>

              <!-- legal_reference 类型 -->
              <div v-else-if="selectedParagraph.classify_type === 'legal_reference'" class="detail-section">
                <div class="detail-field"><span class="detail-label">原文</span><div class="detail-value detail-text-block">{{ selectedParagraph.content }}</div></div>
                <a-divider style="margin: 8px 0" />
                <div class="detail-label" style="margin-bottom: 8px">
                  法律引用 ({{ selectedParagraph.template?.legal_references?.length || 0 }})
                </div>
                <div v-if="selectedParagraph.template?.legal_references?.length" class="legal-ref-list-scroll">
                  <div v-for="(ref, idx) in selectedParagraph.template.legal_references" :key="idx" class="legal-ref-item">
                    <div class="legal-ref-header">
                      <span class="legal-ref-name">{{ ref.name }}</span>
                      <span v-if="ref.code" class="legal-ref-code">({{ ref.code }})</span>
                    </div>
                    <div class="legal-ref-meta">
                      <a-tag size="small" v-if="ref.type">{{ LEGAL_TYPE_MAP[ref.type] || ref.type }}</a-tag>
                      <a-tag size="small" v-if="ref.scope" :color="(LEGAL_SCOPE_MAP[ref.scope] || {}).color || 'default'">{{ (LEGAL_SCOPE_MAP[ref.scope] || {}).label || ref.scope }}</a-tag>
                      <span v-if="ref.authority" class="legal-ref-auth">{{ ref.authority }}</span>
                      <span v-if="ref.effective_date" class="legal-ref-date">生效: {{ ref.effective_date }}</span>
                      <a-tag v-if="ref.status && ref.status !== 'effective'" size="small" :color="ref.status === 'superseded' ? 'red' : 'orange'">{{ ref.status }}</a-tag>
                    </div>
                  </div>
                </div>
                <a-empty v-else description="未提取到法律引用" :image="false" />
              </div>

              <!-- table 类型 -->
              <div v-else-if="selectedParagraph.classify_type === 'table'" class="detail-section">
                <!-- Panel 1: 原始表格 (默认展开) -->
                <div class="collapse-panel">
                  <div class="collapse-header" @click="tableDetailExpanded = !tableDetailExpanded">
                    <span class="collapse-title">原始表格</span>
                    <UpOutlined v-if="tableDetailExpanded" style="font-size: 10px" />
                    <DownOutlined v-else style="font-size: 10px" />
                  </div>
                  <div v-show="tableDetailExpanded" class="collapse-body">
                    <div v-if="isHtmlTable(selectedParagraph.content)" v-html="selectedParagraph.content" class="html-table-container"></div>
                    <div v-else-if="selectedTableBlock?.rows?.length" class="html-table-container">
                      <a-table
                        :data-source="tableBlockRows"
                        :columns="tableBlockColumns"
                        :pagination="false"
                        size="small"
                        bordered
                        class="structural-rows-table"
                      />
                    </div>
                    <div v-else class="detail-text-block">{{ selectedParagraph.content }}</div>
                  </div>
                </div>

                <a-divider style="margin: 6px 0" />

                <!-- Panel 2: 表格 Schema (默认收起) -->
                <div class="collapse-panel">
                  <div class="collapse-header" @click="tableSchemaExpanded = !tableSchemaExpanded">
                    <span class="collapse-title">
                      表格 Schema
                      <a-tag v-if="selectedParagraph.template?.table_schema?.table_type" size="small" :color="(TABLE_TYPE_MAP[selectedParagraph.template.table_schema.table_type] || {}).color || 'default'" style="margin-left: 6px">
                        {{ (TABLE_TYPE_MAP[selectedParagraph.template.table_schema.table_type] || {}).label || selectedParagraph.template.table_schema.table_type }}
                      </a-tag>
                      <span v-if="selectedParagraph.template?.table_schema?.columns?.length" class="collapse-meta">{{ selectedParagraph.template.table_schema.columns.length }} 列</span>
                    </span>
                    <UpOutlined v-if="tableSchemaExpanded" style="font-size: 10px" />
                    <DownOutlined v-else style="font-size: 10px" />
                  </div>
                  <div v-show="tableSchemaExpanded" class="collapse-body">
                    <template v-if="selectedParagraph.template?.table_schema">
                      <div class="table-schema-cols">
                        <div v-for="(col, ci) in (selectedParagraph.template.table_schema.columns || [])" :key="ci" class="ts-col-item">
                          <a-tag size="small" :color="(TABLE_ROLE_MAP[col.role] || {}).color || 'default'">{{ (TABLE_ROLE_MAP[col.role] || {}).label || col.role }}</a-tag>
                          <span class="ts-col-name">{{ col.name }}</span>
                          <span v-if="col.unit" class="ts-col-unit">({{ col.unit }})</span>
                          <span v-if="col.vocabulary?.length" class="ts-col-vocab" :title="col.vocabulary.join(', ')">词表: {{ col.vocabulary.slice(0, 3).join('/') }}{{ col.vocabulary.length > 3 ? '...' : '' }}</span>
                        </div>
                      </div>
                    </template>
                    <a-empty v-else description="未提取到表格 Schema" :image="false" />
                  </div>
                </div>

                <a-divider style="margin: 6px 0" />

                <!-- Panel 3: 结构行 (默认收起) -->
                <div v-if="selectedParagraph.template?.table_schema?.structural_rows?.length" class="collapse-panel">
                  <div class="collapse-header" @click="tableStructRowsExpanded = !tableStructRowsExpanded">
                    <span class="collapse-title">
                      结构行
                      <span class="collapse-meta">{{ selectedParagraph.template.table_schema.structural_rows.length }} 行</span>
                    </span>
                    <UpOutlined v-if="tableStructRowsExpanded" style="font-size: 10px" />
                    <DownOutlined v-else style="font-size: 10px" />
                  </div>
                  <div v-show="tableStructRowsExpanded" class="collapse-body">
                    <a-table
                      :data-source="selectedParagraph.template.table_schema.structural_rows"
                      :columns="Object.keys(selectedParagraph.template.table_schema.structural_rows[0] || {}).map(k => ({ title: k, dataIndex: k, ellipsis: true }))"
                      :pagination="false"
                      size="small"
                      bordered
                      class="structural-rows-table"
                    />
                  </div>
                </div>
              </div>

              <!-- formula 类型 -->
              <div v-else-if="selectedParagraph.classify_type === 'formula'" class="detail-section">
                <div class="detail-field"><span class="detail-label">原文</span><div class="detail-value detail-text-block">{{ selectedParagraph.content }}</div></div>
                <a-divider style="margin: 8px 0" />
                <template v-if="selectedParagraph.template?.formula">
                  <div class="detail-field"><span class="detail-label">用途</span><span class="detail-value">{{ selectedParagraph.template.formula.purpose || '通用计算' }}</span></div>
                  <div class="detail-field"><span class="detail-label">格式</span><span class="detail-value">{{ selectedParagraph.template.formula.format || 'text' }}</span></div>
                  <div class="detail-label" style="margin-top: 8px">变量 ({{ (selectedParagraph.template.formula.variables || []).length }})</div>
                  <div class="formula-vars">
                    <div v-for="(v, vi) in (selectedParagraph.template.formula.variables || [])" :key="vi" class="formula-var-item">
                      <span class="formula-var-symbol">{{ v.symbol }}</span>
                      <span class="formula-var-arrow">→</span>
                      <span class="formula-var-name">{{ v.name || v.symbol }}</span>
                      <span v-if="v.unit" class="formula-var-unit">({{ v.unit }})</span>
                      <span v-if="v.entity_ref" class="formula-var-ref">ref: {{ v.entity_ref }}</span>
                    </div>
                  </div>
                </template>
                <a-empty v-else description="未提取到公式结构" :image="false" />
              </div>

              <!-- figure 类型 -->
              <div v-else-if="selectedParagraph.classify_type === 'figure'" class="detail-section">
                <div class="detail-field"><span class="detail-label">原文</span><div class="detail-value detail-text-block">{{ selectedParagraph.content }}</div></div>
                <a-divider style="margin: 8px 0" />
                <template v-if="selectedParagraph.template?.figure">
                  <div class="detail-field"><span class="detail-label">图片类型</span><span class="detail-value">{{ selectedParagraph.template.figure.figure_type || 'unknown' }}</span></div>
                  <div class="detail-field" v-if="selectedParagraph.template.figure.caption"><span class="detail-label">标题</span><span class="detail-value">{{ selectedParagraph.template.figure.caption }}</span></div>
                  <div v-if="selectedParagraph.template.figure.steps?.length" class="detail-label" style="margin-top: 8px">步骤 ({{ selectedParagraph.template.figure.steps.length }})</div>
                  <div v-if="selectedParagraph.template.figure.steps?.length" class="formula-vars">
                    <div v-for="(step, si) in selectedParagraph.template.figure.steps" :key="si" class="formula-var-item">
                      <span class="step-order">{{ si + 1 }}.</span>
                      <span>{{ typeof step === 'string' ? step : step.name || JSON.stringify(step) }}</span>
                    </div>
                  </div>
                </template>
                <a-empty v-else description="未提取到图片信息" :image="false" />
              </div>

              <!-- parameter 类型 -->
              <div v-else-if="selectedParagraph.classify_type === 'parameter'" class="detail-section">
                <div class="detail-label" style="margin-bottom: 4px">原文</div>
                <div class="detail-text-block">{{ selectedParagraph.content }}</div>
                <a-divider style="margin: 8px 0" />
                <template v-if="selectedParagraph.template?.generalized">
                  <div class="detail-label" style="margin-bottom: 4px">泛化模板</div>
                  <div class="detail-text-block template-text-box" v-html="selectedParagraph.template.generalized.replace(/(\{\{[^}]+\}\})/g, '<mark>$1</mark>')"></div>
                  <div v-if="selectedParagraph.template.slots?.length" class="detail-label" style="margin-top: 8px">Slot ({{ selectedParagraph.template.slots.length }})</div>
                  <div class="slot-chips-list">
                    <span v-for="slot in (selectedParagraph.template.slots || [])" :key="slot.name" class="slot-chip">
                      <a-tag :color="(SLOT_TYPE_MAP[slot.type] || {}).color || 'blue'" size="small">{{ slot.name }}</a-tag>
                      <span v-if="slot.value" class="slot-chip-value">= {{ slot.value }}</span>
                      <span v-if="slot.entity_ref" class="slot-chip-ref">→ {{ slot.entity_ref }}</span>
                    </span>
                  </div>
                  <div v-if="selectedParagraph.template.quality_score != null" class="detail-field" style="margin-top: 8px">
                    <span class="detail-label">质量评分</span>
                    <span class="detail-value" :style="{ color: getConfidenceColor(selectedParagraph.template.quality_score) }">{{ (selectedParagraph.template.quality_score * 100).toFixed(0) }}%</span>
                  </div>
                </template>
                <a-empty v-else description="该参数段落未生成泛化模板" :image="false" />
              </div>

              <!-- narrative / list / 其他 -->
              <div v-else class="detail-section">
                <div class="detail-field">
                  <span class="detail-label">分类</span>
                  <span class="detail-value">
                    {{ selectedParagraph.classify_type || '未分类' }}
                    <template v-if="selectedParagraph.classify_tags?.length">
                      <a-tag v-for="tag in selectedParagraph.classify_tags" :key="tag" size="small" color="processing" style="margin-left: 4px">
                        {{ SUBTYPE_MAP[tag] || tag }}
                      </a-tag>
                    </template>
                  </span>
                </div>

                <!-- 叙述型摘要 -->
                <template v-if="selectedParagraph.classify_type === 'narrative' && selectedParagraph.template">
                  <a-divider style="margin: 8px 0" />
                  <div v-if="selectedParagraph.template.summary" class="detail-field">
                    <span class="detail-label">摘要</span>
                    <div class="detail-value" style="color: var(--gray-800); font-weight: 500">{{ selectedParagraph.template.summary }}</div>
                  </div>
                  <div v-if="selectedParagraph.template.key_points?.length" class="detail-field" style="flex-direction: column; align-items: flex-start">
                    <span class="detail-label" style="margin-bottom: 4px">关键要点</span>
                    <ul style="margin: 0; padding-left: 16px; font-size: 12px; color: var(--gray-700)">
                      <li v-for="point in selectedParagraph.template.key_points" :key="point">{{ point }}</li>
                    </ul>
                  </div>
                  <div v-if="selectedParagraph.template.entities?.length" class="detail-field">
                    <span class="detail-label">关键实体</span>
                    <div class="detail-value">
                      <a-tag v-for="ent in selectedParagraph.template.entities" :key="ent" size="small" style="margin: 2px">{{ ent }}</a-tag>
                    </div>
                  </div>
                </template>

                <a-divider style="margin: 8px 0" />
                <div class="detail-label" style="margin-bottom: 4px">原文</div>
                <div class="detail-text-block">{{ selectedParagraph.content }}</div>
              </div>
            </a-card>
          </a-col>
        </a-row>

        <!-- 步骤导航 -->
        <div class="flow-nav">
          <a-button type="primary" @click="goToStep(1)">下一步：Slot 变量校验</a-button>
        </div>
      </div>

      <!-- ================================================================ -->
      <!-- Step 2: Slot 变量校验                                               -->
      <!-- ================================================================ -->
      <div v-show="activeTab === 'generalize'" class="flow-content">
        <a-row :gutter="16" class="generalize-row">
          <!-- 左栏: parameter 段落列表 -->
          <a-col :span="6">
            <a-card size="small" class="fixed-height-card">
              <template #title><span style="font-size: 12px">参数段落 ({{ filteredParamParagraphs.length }})</span></template>
              <div class="scroll-pane">
                <div
                  v-for="para in filteredParamParagraphs"
                  :key="para.id"
                  class="para-item"
                  :class="{ selected: selectedParamPara && selectedParamPara.id === para.id }"
                  @click="handleParamParaClick(para)"
                >
                  <div class="para-item-header">
                    <span class="para-item-text">{{ (para.content || '').slice(0, 60) }}{{ (para.content || '').length > 60 ? '...' : '' }}</span>
                    <span v-if="para.template?.slots?.length" class="para-item-slots">{{ para.template.slots.length }} slot</span>
                    <span v-if="para.template?.quality_score != null" class="para-item-score" :style="{ color: getConfidenceColor(para.template.quality_score) }">
                      {{ (para.template.quality_score * 100).toFixed(0) }}%
                    </span>
                    <span v-if="reviewedParagraphIds.has(para.id)" class="para-reviewed-badge">✓</span>
                  </div>
                </div>
                <a-empty v-if="!filteredParamParagraphs.length" description="无参数型段落" :image="false" />
              </div>
            </a-card>
          </a-col>

          <!-- 中栏: Diff -->
          <a-col :span="10">
            <a-card size="small" class="fixed-height-card">
              <template #title><span style="font-size: 12px">原文 vs 模板</span></template>
              <template v-if="selectedParamPara">
                <div class="diff-section">
                  <div class="diff-label">原文</div>
                  <div class="diff-text original-text">{{ selectedParamPara.content }}</div>
                </div>
                <div class="diff-section">
                  <div class="diff-label">泛化模板</div>
                  <div class="diff-text template-text" v-html="highlightedGeneralized" @mouseup="onTemplateMouseUp"></div>
                  <!-- 选中文字抽取 Slot 浮动按钮 -->
                  <div
                    v-if="templateSelection.visible"
                    class="slot-extract-popup"
                    :style="{ left: templateSelection.left + 'px', top: templateSelection.top + 'px' }"
                  >
                    <a-button size="small" type="primary" @click="extractSlotFromSelection">抽取为 Slot</a-button>
                    <a-button size="small" @click="dismissSelection">取消</a-button>
                  </div>
                </div>
                <div v-if="selectedParamPara.template?.quality_score != null" class="quality-bar">
                  质量评分:
                  <span :style="{ color: getConfidenceColor(selectedParamPara.template.quality_score), fontWeight: 600 }">
                    {{ (selectedParamPara.template.quality_score * 100).toFixed(0) }}%
                  </span>
                </div>
              </template>
              <a-empty v-else description="请选择左侧段落" :image="false" />
            </a-card>
          </a-col>

          <!-- 右栏: Slot 编辑 -->
          <a-col :span="8">
            <a-card size="small" class="fixed-height-card">
              <template #title><span style="font-size: 12px">Slot 编辑</span></template>
              <template #extra>
                <a-button size="small" type="primary" @click="handleSaveParaTemplate" :loading="saving" :disabled="!selectedParamPara">保存</a-button>
              </template>
              <template v-if="selectedParamPara?.template?.slots?.length">
                <div class="scroll-pane">
                  <div v-for="slot in selectedParamPara.template.slots" :key="slot.name" class="slot-edit-card">
                    <div class="slot-edit-header">
                      <span class="slot-edit-name">{{ slot.name }}</span>
                      <a-tag size="small" :color="(SLOT_TYPE_MAP[slot.type] || {}).color || 'blue'">{{ (SLOT_TYPE_MAP[slot.type] || {}).label || slot.type || '参数型' }}</a-tag>
                      <a-button type="text" size="small" class="slot-remove-btn" @click="removeSlot(selectedParamPara.id, slot.name)" title="移除此 slot">
                        <X :size="14" />
                      </a-button>
                    </div>
                    <div class="slot-edit-row">
                      <span class="slot-edit-label">type</span>
                      <a-select v-model:value="slot.type" size="small" style="flex: 1" @change="(v) => updateSlotField(selectedParamPara.id, slot.name, 'type', v)">
                        <a-select-option value="parameter">参数型</a-select-option>
                        <a-select-option value="enum">枚举型</a-select-option>
                        <a-select-option value="descriptive">描述型</a-select-option>
                        <a-select-option value="reference">引用型</a-select-option>
                      </a-select>
                    </div>
                    <div class="slot-edit-row">
                      <span class="slot-edit-label">value</span>
                      <a-select v-if="slot.type === 'enum' && slot.vocabulary?.length" v-model:value="slot.value" size="small" style="flex: 1" @change="(v) => updateSlotField(selectedParamPara.id, slot.name, 'value', v)">
                        <a-select-option v-for="opt in slot.vocabulary" :key="opt" :value="opt">{{ opt }}</a-select-option>
                      </a-select>
                      <a-input v-else v-model:value="slot.value" size="small" style="flex: 1" @change="() => updateSlotField(selectedParamPara.id, slot.name, 'value', slot.value)" />
                    </div>
                    <div class="slot-edit-row" v-if="slot.unit">
                      <span class="slot-edit-label">unit</span>
                      <span class="slot-edit-readonly">{{ slot.unit }}</span>
                    </div>
                    <div class="slot-edit-row" v-if="slot.entity_ref">
                      <span class="slot-edit-label">ref</span>
                      <span class="slot-edit-readonly">{{ slot.entity_ref }}</span>
                    </div>
                  </div>
                </div>
              </template>
              <a-empty v-else-if="selectedParamPara" description="该段落无 slot" :image="false" />
              <a-empty v-else description="请选择左侧段落" :image="false" />
            </a-card>
          </a-col>
        </a-row>

        <!-- 步骤导航 -->
        <div class="flow-nav">
          <a-button @click="goToStep(0)">上一步：结构化元数据校验</a-button>
          <a-button type="primary" @click="goToStep(2)">下一步：实体确认</a-button>
        </div>
      </div>

      <!-- ================================================================ -->
      <!-- Step 3: 实体确认                                                   -->
      <!-- ================================================================ -->
      <div v-show="activeTab === 'entities'" class="flow-content">
        <a-card title="LLM 建议的新实体" :loading="loadingUnrecognizedEntities">
          <template #extra>
            <a-space>
              <a-button size="small" @click="loadUnrecognizedEntities(taskDetail?.id)" :disabled="!taskDetail?.id">重新分析</a-button>
              <a-button type="primary" size="small" @click="batchSaveEntities" :disabled="!selectedEntities.length">确认并保存 ({{ selectedEntities.length }})</a-button>
            </a-space>
          </template>

          <a-alert v-if="unrecognizedEntities.length === 0 && !loadingUnrecognizedEntities" message="未发现新的实体建议" description="泛化阶段产生的所有插槽均已匹配到现有实体，或文档中未包含可识别的实体。" type="success" show-icon style="margin-bottom: 16px" />
          <a-alert v-else type="info" show-icon style="margin-bottom: 16px">
            <template #message>
              检测到 <strong>{{ rawSlots.length }}</strong> 个未识别插槽，
              其中 <strong>{{ matchedCount }}</strong> 个可归入已有实体，
              <strong>{{ newCount }}</strong> 个建议为新实体。
              确认后将保存到实体库，下次提取时自动使用。
            </template>
          </a-alert>

          <div v-if="unrecognizedEntities.length > 0">
            <a-tabs v-model:activeKey="activeEntityCategory" type="card">
              <a-tab-pane v-for="(entities, category) in groupedUnrecognizedEntities" :key="category" :tab="`${category} (${entities.length})`">
                <a-table
                  :data-source="entities"
                  :columns="entityTableColumns"
                  :row-selection="{
                    selectedRowKeys: selectedEntities.map(e => e.entity_key || e.name_cn || e.name),
                    onSelect: (record, selected) => {
                      if (selected) selectedEntities.push(record)
                      else { const key = record.entity_key || record.name_cn; const idx = selectedEntities.findIndex(e => (e.entity_key || e.name_cn) === key); if (idx !== -1) selectedEntities.splice(idx, 1) }
                    }
                  }"
                  :pagination="{ pageSize: 10 }"
                  row-key="entity_key"
                  size="small"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'type'">
                      <a-tag v-if="record.suggestion_type === 'add_property'" color="blue">属性补充</a-tag>
                      <a-tag v-else color="green">新实体</a-tag>
                    </template>
                    <template v-else-if="column.key === 'name_cn'">
                      <template v-if="record.suggestion_type === 'add_property'">{{ record.target_entity_name }} → +{{ record.proposed_property?.name_cn }}</template>
                      <template v-else>{{ record.name_cn }}</template>
                    </template>
                    <template v-else-if="column.key === 'synonyms'">{{ (record.synonyms || []).join('、') }}</template>
                    <template v-else-if="column.key === 'confidence'">
                      <span :style="{ color: Math.round((record.confidence || 0) * 100) >= 80 ? '#52c41a' : Math.round((record.confidence || 0) * 100) >= 60 ? '#faad14' : '#ff4d4f' }">{{ Math.round((record.confidence || 0) * 100) }}%</span>
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <a-space>
                        <a-button type="link" size="small" @click="openEntityEditModal(record)">编辑</a-button>
                        <a-button type="link" size="small" @click="saveEntityDirectly(record)">确认保存</a-button>
                      </a-space>
                    </template>
                  </template>
                </a-table>
              </a-tab-pane>
            </a-tabs>
          </div>
        </a-card>

        <!-- 编辑实体弹窗 -->
        <a-modal v-model:open="entityEditModalVisible" title="编辑实体定义" ok-text="确认并保存" cancel-text="取消" @ok="saveEntity" width="640px">
          <a-form layout="vertical" v-if="editingEntity">
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="实体名称" required><a-input v-model:value="editingEntity.name_cn" placeholder="中文名称" /></a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="Entity Key" required><a-input v-model:value="editingEntity.entity_key" placeholder="snake_case_key" /></a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="16">
              <a-col :span="8">
                <a-form-item label="分类" required>
                  <a-select v-model:value="editingEntity.category" placeholder="选择分类" :options="entityCategories.map(cat => ({ label: cat, value: cat }))" show-search allow-clear />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="值类型">
                  <a-select v-model:value="editingEntity.value_type" placeholder="选择类型">
                    <a-select-option value="String">String</a-select-option>
                    <a-select-option value="Numeric">Numeric</a-select-option>
                    <a-select-option value="Boolean">Boolean</a-select-option>
                    <a-select-option value="Date">Date</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="单位"><a-input v-model:value="editingEntity.unit" placeholder="如 Mt/a、mg/m³" /></a-form-item>
              </a-col>
            </a-row>
            <a-form-item label="描述"><a-textarea v-model:value="editingEntity.description" placeholder="实体含义描述" :rows="2" /></a-form-item>
            <a-form-item label="同义词">
              <a-select v-model:value="editingEntity.synonyms" mode="tags" placeholder="输入后回车添加" :tokenSeparators="[',', '、']" />
            </a-form-item>
          </a-form>
        </a-modal>

        <!-- 步骤导航 -->
        <div class="flow-nav">
          <a-button @click="goToStep(1)">上一步：Slot 变量校验</a-button>
          <a-button type="primary" @click="goToStep(3)">下一步：入库确认</a-button>
        </div>
      </div>

      <!-- ================================================================ -->
      <!-- Step 4: 入库确认                                                   -->
      <!-- ================================================================ -->
      <div v-show="activeTab === 'commit'" class="flow-content">
        <!-- 统计卡片 -->
        <a-row :gutter="12" class="stats-row">
          <a-col :span="4">
            <a-card size="small" class="stat-card">
              <div class="stat-value">{{ sourceParagraphs.length }}</div>
              <div class="stat-label">总段落</div>
            </a-card>
          </a-col>
          <a-col :span="4">
            <a-card size="small" class="stat-card">
              <div class="stat-value">{{ classifyStats.parameter || 0 }}</div>
              <div class="stat-label">参数型</div>
            </a-card>
          </a-col>
          <a-col :span="4">
            <a-card size="small" class="stat-card">
              <div class="stat-value">{{ classifyStats.legal_reference || 0 }}</div>
              <div class="stat-label">标准引用</div>
            </a-card>
          </a-col>
          <a-col :span="4">
            <a-card size="small" class="stat-card">
              <div class="stat-value">{{ classifyStats.table || 0 }}</div>
              <div class="stat-label">表格</div>
            </a-card>
          </a-col>
          <a-col :span="4">
            <a-card size="small" class="stat-card">
              <div class="stat-value">{{ classifyStats.formula || 0 }}</div>
              <div class="stat-label">公式</div>
            </a-card>
          </a-col>
          <a-col :span="4">
            <a-card size="small" class="stat-card">
              <div class="stat-value">{{ Object.keys(slotSummary).length }}</div>
              <div class="stat-label">提取变量</div>
            </a-card>
          </a-col>
        </a-row>

        <!-- 变量汇总 -->
        <a-card title="变量汇总" size="small" style="margin-top: 16px" v-if="Object.keys(slotSummary).length > 0">
          <a-table
            :data-source="Object.entries(slotSummary).map(([k, v]) => ({ key: k, value: v.value, type: v.type, unit: v.unit, entity_ref: v.entity_ref }))"
            :columns="[
              { title: '变量名', dataIndex: 'key', ellipsis: true },
              { title: '值', dataIndex: 'value', ellipsis: true },
              { title: '类型', dataIndex: 'type', width: 80 },
              { title: '单位', dataIndex: 'unit', width: 80 },
              { title: '实体引用', dataIndex: 'entity_ref', ellipsis: true },
            ]"
            :pagination="{ pageSize: 15 }"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'type'">
                <a-tag size="small" :color="(SLOT_TYPE_MAP[record.type] || {}).color || 'blue'">{{ (SLOT_TYPE_MAP[record.type] || {}).label || record.type }}</a-tag>
              </template>
            </template>
          </a-table>
        </a-card>

        <!-- 入库操作 -->
        <a-card title="入库操作" size="small" style="margin-top: 16px">
          <a-form layout="vertical">
            <a-form-item label="目标知识库">
              <a-select
                v-model:value="selectedKnowledgeBaseId"
                placeholder="选择目标知识库"
                :loading="loadingKnowledgeBases"
                style="max-width: 400px"
              >
                <a-select-option v-for="kb in lightragKnowledgeBases" :key="kb.kb_id" :value="kb.kb_id">{{ kb.name }}</a-select-option>
              </a-select>
            </a-form-item>
          </a-form>
          <div class="commit-actions">
            <a-button type="primary" size="large" danger @click="handleCommit" :disabled="!selectedKnowledgeBaseId" :loading="saving">
              确认入库
            </a-button>
          </div>
        </a-card>

        <!-- 步骤导航 -->
        <div class="flow-nav">
          <a-button @click="goToStep(2)">上一步：实体确认</a-button>
        </div>
      </div>

    </div>
  </div>
</template>

<style lang="less" scoped>
.etl-workbench {
  margin-top: 16px;
  max-width: 100%;
  overflow-x: hidden;
  user-select: text;

  :deep(.ant-card) { max-width: 100%; overflow: hidden; }
  :deep(table) { max-width: 100%; table-layout: fixed; word-wrap: break-word; }
}

.loading-state, .empty-state {
  display: flex; align-items: center; justify-content: center;
  height: 400px; background: #fff; border-radius: 12px;
}
.empty-state {
  flex-direction: column; gap: 12px;
  color: var(--gray-500); font-size: 13px;
}
.empty-state-icon {
  color: var(--gray-300, #c0c4cc);
}

.workbench-header {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; padding: 16px 20px;
  border-radius: 12px 12px 0 0; border: 1px solid var(--gray-150); border-bottom: none;
  h3 { margin: 0; font-size: 20px; font-weight: 600; }
  p { margin: 4px 0 0; color: var(--gray-500); font-size: 13px; }
}

.header-status {
  .status-item { font-size: 13px; color: var(--gray-600); }
}

.flow-steps {
  display: flex; align-items: center; justify-content: center;
  background: #fff; padding: 14px 24px;
  border: 1px solid var(--gray-150); border-top: none;
  gap: 0;
}
.flow-step {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: 6px;
  font-size: 13px; color: var(--gray-500);
  transition: all 0.2s; cursor: default;
  &.clickable { cursor: pointer; &:hover { background: var(--gray-50); } }
  &.active {
    color: #1677ff; font-weight: 600;
    .flow-step-num { background: #1677ff; color: #fff; }
  }
  &.done:not(.active) {
    color: #52c41a;
    .flow-step-num { background: #52c41a; color: #fff; }
  }
}
.flow-step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 50%;
  background: var(--gray-200); color: var(--gray-600);
  font-size: 11px; font-weight: 600; transition: all 0.2s;
}
.flow-step-title { white-space: nowrap; }
.flow-step-arrow { margin: 0 8px; color: var(--gray-300); font-size: 18px; }

.flow-panel {
  background: #fff; padding: 16px 20px;
  border: 1px solid var(--gray-150); border-top: none; border-radius: 0 0 12px 12px;
  margin-bottom: 24px; max-width: 100%; overflow: hidden;
}

.flow-nav {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--gray-150);
}

// ========== Tab 1: 结构化元数据校验 ==========
.tab-header-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 16px; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
  :deep(.ant-btn) { font-size: 13px; }
}

.classify-filter-label {
  font-size: 13px; color: var(--gray-600);
}

.classify-count {
  font-size: 10px; color: var(--gray-400); margin-left: 2px;
}

.tab-header-bar {
  :deep(.ant-radio-group) { font-size: 13px; }
  :deep(.ant-radio-button-wrapper) { font-size: 13px; padding: 0 10px; height: 28px; line-height: 28px; }
}

.review-progress { margin-bottom: 12px; padding: 0 4px; }

.parse-row {
  padding-top: 8px;
}

.paragraph-viewer-card {
  height: 560px; display: flex; flex-direction: column;
  :deep(.ant-card-body) { flex: 1; display: flex; flex-direction: column; overflow-y: auto; min-height: 0; }
}

.detail-panel-card {
  display: flex; flex-direction: column; max-height: 560px;
  :deep(.ant-card-body) { flex: 1; display: flex; flex-direction: column; overflow-y: auto; min-height: 0; }
  :deep(.ant-btn) { font-size: 13px; }
  :deep(.ant-radio-button-wrapper) { font-size: 13px; }
  :deep(.ant-select-selector) { font-size: 13px; }
  :deep(.ant-select-item-option-content) { font-size: 13px; }
}

.fixed-height-card {
  height: 560px; display: flex; flex-direction: column;
  :deep(.ant-card-body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
}

.chapter-nav-card {
  transition: all 0.2s;
  :deep(.ant-card-head) { min-height: 36px; padding: 0 8px; }
  :deep(.ant-card-head-title) { padding: 6px 0; }
  :deep(.ant-card-extra) { padding: 6px 0; }
}
.chapter-toggle-btn { padding: 0 4px; height: 22px; line-height: 22px; }
.chapter-tree-pane { padding-right: 0; }
.chapter-tree-node { font-size: 11px; }

// 章节树缩进减小
.chapter-tree-pane :deep(.ant-tree) {
  font-size: 11px; background: transparent;
  .ant-tree-treenode { padding: 0; margin: 0; }
  .ant-tree-indent-unit { width: 10px; min-width: 10px; }
  .ant-tree-switcher { width: 16px; min-width: 16px; }
  .ant-tree-node-content-wrapper { padding: 1px 4px; min-height: 22px; line-height: 22px; }
}

.scroll-pane { flex: 1; overflow-y: auto; padding-right: 8px; min-height: 0; }

.paragraph {
  padding: 10px 8px; border-bottom: 1px dashed var(--gray-150); cursor: pointer;
  &.selected { background-color: rgba(24, 144, 255, 0.06); border-left: 3px solid #1890ff; padding-left: 5px; }
  &.para-reviewed { opacity: 0.6; }
  &.para-reviewed.selected { opacity: 1; }
  &.para-needs-review { border-left: 3px solid #faad14; padding-left: 5px; }

  .para-title {
    display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-bottom: 4px;
    .para-section-tag { font-weight: 400; font-size: 10px; }
    .para-subtype-tag { font-size: 10px; padding: 0 4px; line-height: 18px; height: 18px; }
  }
  .para-confidence { font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .para-reviewed-badge { color: #52c41a; font-weight: 700; font-size: 13px; }
  .para-content { color: var(--gray-700); font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
  .para-summary { color: var(--gray-500); font-size: 11px; line-height: 1.4; margin-top: 3px; padding-left: 4px; border-left: 2px solid var(--gray-200); }
}

// 详情面板
.detail-section {
  flex: 1; display: flex; flex-direction: column; min-height: 0;
}

.detail-field {
  display: flex; gap: 8px; margin-bottom: 6px; font-size: 13px;
  .detail-label { color: var(--gray-500); min-width: 60px; font-weight: 500; flex-shrink: 0; }
  .detail-value { color: var(--gray-800); word-break: break-all; }
}

.detail-label {
  font-size: 11px; font-weight: 600; color: var(--gray-500);
  text-transform: uppercase; letter-spacing: 0.5px;
}

.detail-text-block {
  background: var(--gray-50); border: 1px solid var(--gray-150);
  border-radius: 6px; padding: 8px 10px; font-size: 12px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word;
  font-family: 'SFMono-Regular', Consolas, monospace;
  margin-top: 4px; max-height: 120px; overflow-y: auto;
}

// 法律引用
.legal-ref-list-scroll {
  display: flex; flex-direction: column; gap: 6px; max-height: 300px; overflow-y: auto;
}

.legal-ref-item {
  padding: 6px 8px; background: var(--gray-50); border-radius: 4px;
  .legal-ref-header { margin-bottom: 4px; }
  .legal-ref-name { font-weight: 500; color: var(--gray-800); font-size: 13px; }
  .legal-ref-code { color: var(--gray-500); font-size: 11px; margin-left: 4px; }
  .legal-ref-meta { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .legal-ref-auth { color: var(--gray-400); font-size: 11px; }
  .legal-ref-date { color: var(--gray-500); font-size: 11px; }
}

// 表格 Schema
.table-schema-cols {
  display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow-y: auto;
}

.ts-col-item {
  display: flex; align-items: center; gap: 6px; font-size: 12px;
  .ts-col-name { font-weight: 500; }
  .ts-col-unit { color: var(--gray-500); font-size: 11px; }
  .ts-col-vocab { color: var(--gray-400); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 160px; }
}

.structural-rows-section { margin-top: 12px; }
.structural-rows-table { :deep(table) { font-size: 11px; } }

// 公式变量
.formula-vars {
  display: flex; flex-direction: column; gap: 4px;
}

.formula-var-item {
  display: flex; align-items: center; gap: 6px; font-size: 12px; padding: 4px 8px; background: var(--gray-50); border-radius: 4px;
  .formula-var-symbol { font-family: monospace; font-weight: 600; color: var(--gray-700); min-width: 30px; }
  .formula-var-arrow { color: var(--gray-400); }
  .formula-var-name { color: var(--gray-800); }
  .formula-var-unit { color: var(--gray-500); font-size: 11px; }
  .formula-var-ref { color: #1890ff; font-size: 11px; margin-left: auto; }
  .step-order { font-weight: 600; color: var(--gray-500); min-width: 20px; }
}

// Slot chips (parameter summary)
.slot-chips-list {
  display: flex; flex-wrap: wrap; gap: 6px;
  .slot-chip { display: inline-flex; align-items: center; gap: 2px; font-size: 12px; }
  .slot-chip-value { color: var(--gray-600); }
  .slot-chip-ref { color: #1890ff; font-size: 11px; }
}

.template-text-box { max-height: 100px; }

// ========== Tab 2: Slot 变量校验 ==========
.generalize-row { padding-top: 8px; }

.para-item {
  padding: 8px; border: 1px solid var(--gray-100); border-radius: 6px; margin-bottom: 6px; cursor: pointer;
  transition: all 0.2s;
  &:hover { border-color: var(--gray-300); background: var(--gray-50); }
  &.selected { border-color: #1890ff; background: rgba(24, 144, 255, 0.06); }

  .para-item-header { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .para-item-text { font-size: 12px; color: var(--gray-700); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .para-item-slots { font-size: 10px; color: var(--gray-500); }
  .para-item-score { font-size: 11px; font-weight: 600; }
  .para-reviewed-badge { color: #52c41a; font-weight: 700; font-size: 13px; }
}

.diff-section {
  margin-bottom: 12px;
  position: relative;
  .diff-label { font-size: 11px; font-weight: 600; color: var(--gray-500); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
  .diff-text {
    padding: 10px; border-radius: 6px; font-size: 13px; line-height: 1.6;
    white-space: pre-wrap; word-break: break-word;
    &.original-text { background: var(--gray-50); border: 1px solid var(--gray-150); }
    &.template-text { background: #f6ffed; border: 1px solid #b7eb8f; user-select: text; cursor: text; }
  }
}

.slot-extract-popup {
  position: fixed;
  z-index: 1000;
  transform: translateX(-50%);
  display: flex;
  gap: 6px;
  padding: 4px;
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  white-space: nowrap;
}

.quality-bar {
  font-size: 13px; color: var(--gray-600); margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--gray-100);
}

// Slot 编辑卡片
.slot-edit-card {
  border: 1px solid var(--gray-150); border-radius: 6px; padding: 8px 10px; margin-bottom: 8px;
  .slot-edit-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
  .slot-edit-name { font-family: monospace; font-weight: 600; font-size: 13px; color: var(--gray-700); flex: 1; }
  .slot-remove-btn {
    flex-shrink: 0; color: var(--gray-400); padding: 0; width: 22px; height: 22px;
    &:hover { color: #ff4d4f; background: rgba(255, 77, 79, 0.06); }
  }
  .slot-edit-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  .slot-edit-label { font-size: 11px; color: var(--gray-500); min-width: 36px; }
  .slot-edit-readonly { font-size: 12px; color: var(--gray-600); }
}

// ========== Tab 4: 入库确认 ==========
.stats-row { margin-bottom: 8px; }

.stat-card {
  text-align: center;
  .stat-value { font-size: 28px; font-weight: 700; color: var(--gray-800); }
  .stat-label { font-size: 12px; color: var(--gray-500); margin-top: 4px; }
}

.commit-actions {
  display: flex; justify-content: center; padding: 16px 0;
}

// ========== 通用 ==========
mark {
  background: rgba(24, 144, 255, 0.2); padding: 0 2px; border-radius: 4px;
}

.detail-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  flex: 1; min-height: 200px; gap: 0;
  :deep(.ant-empty-image) { display: none; }
  :deep(.ant-empty-description) { margin-top: 2px; }
  
  color:var(--gray-500); 
}

.json-viewer {
  flex: 1; margin: 0; padding: 12px;
  background: var(--gray-50, #fafafa); border: 1px solid var(--gray-150, #e8e8e8);
  border-radius: 6px; font-size: 12px; line-height: 1.5;
  font-family: 'SFMono-Regular', Consolas, monospace;
  overflow: auto; white-space: pre-wrap; word-break: break-word;
}

.html-table-container {
  margin: 8px 0; overflow-x: auto;
  :deep(table) {
    border-collapse: collapse; width: 100%; font-size: 13px;
    td, th { border: 1px solid #d9d9d9; padding: 6px 10px; text-align: left; }
    th { background-color: #fafafa; font-weight: 600; }
  }
}

.collapse-panel {
  .collapse-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 8px; cursor: pointer; border-radius: 4px;
    font-size: 12px; font-weight: 600; color: var(--gray-600);
    background: var(--gray-50, #fafafa); transition: background 0.2s;
    &:hover { background: var(--gray-100, #f0f0f0); }
    .collapse-title { display: inline-flex; align-items: center; gap: 4px; }
    .collapse-meta { font-weight: 400; color: var(--gray-400); font-size: 11px; margin-left: 6px; }
  }
  .collapse-body { padding: 8px 0 4px; }
}
</style>
