<script setup>
import { computed, onMounted, reactive, ref, watch, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { LeftOutlined, RightOutlined, UpOutlined, DownOutlined } from '@ant-design/icons-vue'
import { FileText, Inbox, Plus, X } from 'lucide-vue-next'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { domainEntityBuilderApi } from '@/apis/domain_entity_builder_api'
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
const tableDetailHeight = ref(220)  // 原始表格区域可调整高度
const isResizingTableDetail = ref(false)


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

// ========== 审核状态 ==========
const reviewedParagraphIds = ref(new Set())

// ========== 分类筛选 ==========
const classifyFilter = ref(null)

// ========== 知识库 ==========
const lightragKnowledgeBases = ref([])
const selectedKnowledgeBaseId = ref(null)
const loadingKnowledgeBases = ref(false)

// ========== Slot 高亮交互 ==========
const activeSlotName = ref('')

const onTemplateTextClick = (e) => {
  const mark = e.target.closest('mark')
  if (!mark) { activeSlotName.value = ''; return }
  const slotName = mark.dataset.slot
  activeSlotName.value = slotName || ''
}

const highlightedTemplateHtml = computed(() => {
  const text = selectedParagraph.value?.template?.generalized || ''
  if (!text) return ''
  const active = activeSlotName.value
  const slots = selectedParagraph.value?.template?.slots || []
  const slotNames = new Set(slots.map(s => s.name))
  // 高亮 {{name}} 和 [name] 两种占位格式（name 必须是已知的 slot 名）
  return text.replace(
    /\{\{([^}]+)\}\}|\[([^\]]+)\]/g,
    (m, braceName, bracketName) => {
      const name = braceName || bracketName
      if (!slotNames.has(name)) return m
      return `<mark data-slot="${name}" class="${active === name ? 'slot-active' : ''}">${m}</mark>`
    }
  )
})

// ========== 选中文字新建 Slot ==========
const slotSelection = ref({ text: '', left: 0, top: 0, visible: false })
const newSlotModalVisible = ref(false)
const newSlotForm = ref({ name: '', value: '', entity_ref: '', suggestions: [] })
const allEntitySchemas = ref([])  // 缓存实体列表（含属性）

const loadEntitySchemas = async () => {
  if (allEntitySchemas.value.length) return
  try {
    const res = await domainEntityBuilderApi.listEntitySchemas(null, taskDetail.value?.domain || null)
    const list = res?.data || res?.entities || res?.items || []
    allEntitySchemas.value = Array.isArray(list) ? list : []
  } catch { /* 加载失败不阻断，仅无推荐 */ }
}

// 前端三级匹配：为选中文字/slot名推荐实体属性绑定
const suggestEntityBindings = (text) => {
  const suggestions = []
  for (const entity of allEntitySchemas.value) {
    const props = entity.properties || []
    if (!Array.isArray(props)) continue
    for (const p of props) {
      if (!p || typeof p !== 'object') continue
      const propName = p.name_cn || p.key || ''
      if (!propName) continue
      let score = 0
      if (propName === text) score = 1.0
      else if (propName.includes(text) || text.includes(propName)) score = 0.7
      else {
        const common = [...new Set(text)].filter(c => propName.includes(c)).length
        if (common >= 2) score = 0.4
      }
      if (score > 0) {
        suggestions.push({
          entity_ref: `${entity.entity_key}.${p.key || propName}`,
          label: `${entity.name_cn} → ${propName}`,
          score,
        })
      }
    }
  }
  return suggestions.sort((a, b) => b.score - a.score).slice(0, 5)
}

const onTemplateMouseUp = () => {
  setTimeout(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !sel.toString().trim()) {
      slotSelection.value.visible = false
      return
    }
    const selText = sel.toString().trim()
    // 选中文字不能含已有占位符
    if (/\{\{.*?\}\}|\[.*?\]/.test(selText)) {
      slotSelection.value.visible = false
      return
    }
    const range = sel.getRangeAt(0)
    const container = document.querySelector('.template-text-box')
    if (!container || !container.contains(range.commonAncestorContainer)) {
      slotSelection.value.visible = false
      return
    }
    const rect = range.getBoundingClientRect()
    slotSelection.value = {
      text: selText,
      left: rect.left + rect.width / 2,
      top: rect.top - 40,
      visible: true,
    }
  }, 10)
}

const openNewSlotModal = async () => {
  const selText = slotSelection.value.text
  if (!selText) return
  slotSelection.value.visible = false
  let suggestions = []
  try {
    await loadEntitySchemas()
    suggestions = suggestEntityBindings(selText)
  } catch (e) {
    console.warn('实体推荐加载失败', e)
  }
  newSlotForm.value = {
    name: '',
    value: selText,
    entity_ref: '',
    suggestions,
  }
  newSlotModalVisible.value = true
}

const confirmNewSlot = () => {
  const para = selectedParagraph.value
  const { name, value, entity_ref } = newSlotForm.value
  if (!name.trim()) {
    message.warning('请输入 Slot 名称')
    return
  }
  if (!para?.template) return
  if (!para.template.slots) para.template.slots = []
  if (para.template.slots.some(s => s.name === name.trim())) {
    message.warning('已存在同名 Slot')
    return
  }
  // 替换泛化模板中的选中文字为 {{name}}
  const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const gen = para.template.generalized || ''
  if (!new RegExp(escaped).test(gen)) {
    message.warning('未在模板文本中找到选中文字')
    return
  }
  para.template.generalized = gen.replace(new RegExp(escaped), `{{${name.trim()}}}`)
  para.template.slots.push({
    name: name.trim(),
    type: 'parameter',
    value,
    entity_ref: entity_ref || '',
    description: '',
    suggested_source: '手动抽取',
  })
  newSlotModalVisible.value = false
  message.success(`已创建 Slot "${name.trim()}"${entity_ref ? '，并绑定 ' + entity_ref : ''}`)
}

// ========== 校验相关 ==========
const validationReport = ref(null)
const validating = ref(false)

// ========== 实体发现 ==========
const discoveringEntities = ref(false)

// ========== 步骤完成追踪 ==========
const stepCompleted = ref({ parse: false, entities: false, commit: false })

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
        const pathTitle = titleMap.has(key) ? `${segment} ${titleMap.get(key)}` : segment
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

const scrollToParagraph = (paraId) => {
  if (!paraId) return
  const para = sourceParagraphs.value.find(p => p.id === paraId)
  if (para) {
    handleParagraphClick(para)
    // 滚动到对应段落
    setTimeout(() => {
      const el = document.querySelector(`.paragraph.selected`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 100)
  }
}

// ========== 运行校验 ==========
const runValidation = async () => {
  if (!taskDetail.value?.id) return
  validating.value = true
  try {
    const res = await domainFactoryApi.validateTask(taskDetail.value.id)
    validationReport.value = res.report
    message.success(
      validationReport.value.passed
        ? '校验通过，无错误'
        : `校验完成：${validationReport.value.summary.total_errors} 个错误，${validationReport.value.summary.total_warnings} 个警告`
    )
  } catch (e) {
    message.error('校验失败：' + (e.message || e))
  } finally {
    validating.value = false
  }
}

// ========== 触发实体发现 ==========
const triggerEntityDiscovery = async () => {
  if (!taskDetail.value?.id) return
  discoveringEntities.value = true
  try {
    const res = await domainFactoryApi.discoverEntities(taskDetail.value.id)
    const total = res.result?.total || 0
    const bound = res.result?.bound || 0
    if (total > 0 || bound > 0) {
      // 直接把识别结果应用到实体确认 tab，进入后即可查看，无需再次 LLM 提取
      applyEntityProposals(res.result.proposals || [])
      const parts = []
      if (bound > 0) parts.push(`已自动绑定 ${bound} 个 slot`)
      if (total > 0) parts.push(`识别出 ${total} 个新实体/属性建议，请前往「领域实体确认」tab 确认`)
      message.success(parts.join('；'))
      // 绑定结果已写 DB，刷新任务详情让 Tab 1 slot chips 显示最新绑定状态
      if (bound > 0) {
        const detail = await domainFactoryApi.getTaskDetail(taskDetail.value.id)
        taskDetail.value = detail
      }
    } else {
      message.info('未发现新实体，所有 slot 均已绑定或候选不足')
    }
  } catch (e) {
    message.error('实体发现失败：' + (e.message || e))
  } finally {
    discoveringEntities.value = false
  }
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
    // 从任务元数据加载已有的实体建议（智能识别实体的结果），不触发 LLM
    loadEntityProposalsFromMetadata(detail)
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
  activeSlotName.value = ''
  tableDetailExpanded.value = true
  tableSchemaExpanded.value = false
  tableStructRowsExpanded.value = false
}

// ========== 原始表格区域拖拽调整高度 ==========
const onTableDetailResizeStart = (e) => {
  e.preventDefault()
  isResizingTableDetail.value = true
  const startY = e.clientY
  const startHeight = tableDetailHeight.value
  const onMove = (ev) => {
    if (!isResizingTableDetail.value) return
    const delta = ev.clientY - startY
    tableDetailHeight.value = Math.max(100, startHeight + delta)
  }
  const onUp = () => {
    isResizingTableDetail.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

const handleToggleEditMode = async (checked) => {
  if (!checked) {
    // 退出 JSON 模式：解析并保存
    try {
      const parsed = JSON.parse(jsonEditValue.value)
      Object.assign(selectedParagraph.value, parsed)
    } catch {
      message.error('JSON 格式错误，请检查')
      detailEditMode.value = true
      return
    }
    const saved = await doSaveParagraphs()
    if (saved) stepCompleted.value.parse = true
    detailEditMode.value = false
  } else {
    // 进入 JSON 模式
    jsonEditValue.value = JSON.stringify(selectedParagraph.value, null, 2)
    detailEditMode.value = true
  }
}

// ========== Tab 切换 ==========
const STEP_KEYS = ['parse', 'entities', 'commit']
const currentStep = computed(() => STEP_KEYS.indexOf(activeTab.value))

const goToStep = (index) => {
  const key = STEP_KEYS[index]
  if (!key) return
  activeTab.value = key
  if (key === 'parse') selectedParagraph.value = null
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

const removeSlot = (paraId, slotName) => {
  const para = sourceParagraphs.value.find(p => p.id === paraId)
  if (!para?.template?.slots) return
  const idx = para.template.slots.findIndex(s => s.name === slotName)
  if (idx === -1) return
  const slot = para.template.slots[idx]
  const restoreValue = slot.value || ''
  const escaped = slotName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  para.template.slots.splice(idx, 1)
  if (para.template.generalized) {
    // 同时匹配 {{name}} 和 [name] 两种占位格式
    para.template.generalized = para.template.generalized
      .replace(new RegExp(`\\{\\{${escaped}\\}\\}`, 'g'), restoreValue)
      .replace(new RegExp(`\\[${escaped}\\]`, 'g'), restoreValue)
    if (!restoreValue) {
      para.template.generalized = para.template.generalized
        .replace(/[，、]+\s*[，、]+/g, '，')
        .replace(/[，、]\s*(?=[～。；：\n])/g, '')
        .replace(/(?<=[～。；：\n])\s*[，、]/g, '')
    }
    if (para.template.slots.length === 0) {
      const cleanText = para.template.generalized.replace(/[，、。；：！\s]/g, '')
      const originalClean = (para.content || '').replace(/[，、。；：！\s]/g, '')
      if (cleanText.length < originalClean.length * 0.3) {
        para.template.generalized = para.content || para.template.generalized
      }
    }
  }
}

// ========== 删除段落 ==========
const deleteParagraph = (paraId) => {
  const para = sourceParagraphs.value.find(p => p.id === paraId)
  if (!para) return
  Modal.confirm({
    title: '确认删除段落？',
    content: () => {
      const preview = (para.content || para.title || '').slice(0, 80)
      return h('p', {}, `将删除段落: "${preview}${(para.content || '').length > 80 ? '...' : ''}"`)
    },
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      const idx = sourceParagraphs.value.findIndex(p => p.id === paraId)
      if (idx === -1) return
      sourceParagraphs.value.splice(idx, 1)
      reviewedParagraphIds.value.delete(paraId)
      if (selectedParagraph.value?.id === paraId) {
        selectedParagraph.value = null
      }
      // 同步删除 structured_blocks 中的对应条目
      const blockIdx = structuredBlocks.value.findIndex(b => b.paragraph_id === paraId || b.id === paraId)
      if (blockIdx !== -1) {
        structuredBlocks.value.splice(blockIdx, 1)
      }
      const ok = await doSaveParagraphs()
      if (ok) {
        stepCompleted.value.parse = true
        message.success('段落已删除')
      }
    }
  })
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
const entityPagination = reactive({ current: 1, pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条`, pageSizeOptions: ['5', '10', '20', '50'] })

const handleTableChange = (pag) => {
  entityPagination.current = pag.current
  entityPagination.pageSize = pag.pageSize
}

const entityTableColumns = [
  { title: '类型', key: 'type', width: 80 },
  { title: '名称', key: 'name_cn', ellipsis: true },
  { title: '同义词', key: 'synonyms', ellipsis: true },
  { title: '置信度', key: 'confidence', width: 80 },
  { title: '操作', key: 'action', width: 120 },
]

// 从任务 metadata 读取实体建议（智能识别实体的结果），纯读取不触发 LLM
const loadEntityProposalsFromMetadata = (detail) => {
  const proposals = detail?.template_metadata?.entity_proposals || []
  if (!proposals.length) return
  applyEntityProposals(proposals)
}

// 将 proposals 应用到实体确认 tab 的展示状态
const applyEntityProposals = (proposals) => {
  selectedEntities.value = []
  entityPagination.current = 1
  proposals.forEach((e, i) => { e._row_id = (e.entity_key || e.target_entity_key || '') + '_' + (e.proposed_property?.key || e.name_cn || '') + '_' + i })
  unrecognizedEntities.value = proposals
  matchedCount.value = proposals.filter(e => e.suggestion_type === 'add_property').length
  newCount.value = proposals.filter(e => e.suggestion_type === 'new_entity').length
  const groups = {}
  const cats = new Set()
  proposals.forEach(e => {
    const cat = e.category || e.target_entity_name || '其他'
    cats.add(cat)
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(e)
  })
  groupedUnrecognizedEntities.value = groups
  entityCategories.value = Array.from(cats)
  if (cats.size > 0) activeEntityCategory.value = Array.from(cats)[0]
}

const openEntityEditModal = (record) => {
  editingEntity.value = { ...record }
  entityEditModalVisible.value = true
}

// 保存后从建议列表本地移除（不触发 LLM 重新提取）
const removeProposalsLocally = (savedItems) => {
  const savedIds = new Set(savedItems.map(e => e._row_id))
  const remaining = unrecognizedEntities.value.filter(e => !savedIds.has(e._row_id))
  applyEntityProposals(remaining)
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
    removeProposalsLocally([entity])
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
    removeProposalsLocally([record])
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
    const saved = [...selectedEntities.value]
    selectedEntities.value = []
    removeProposalsLocally(saved)
    stepCompleted.value.entities = true
  } catch {
    message.error('批量保存失败')
  }
}


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
    reviewedParagraphIds.value = new Set()
    unrecognizedEntities.value = []
    groupedUnrecognizedEntities.value = {}
    stepCompleted.value = { parse: false, entities: false, commit: false }
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
    <!-- ========== Header: 标题 + 步骤导航 + 状态栏 ========== -->
    <div class="workbench-header">
      <div class="header-top">
        <h3>ETL 清洗工作台</h3>
        <a-space :size="12" class="header-status">
          <a-tag v-if="domainLabel" color="blue">{{ domainLabel }}</a-tag>
          <a-tag v-if="reportTypeLabel" color="green">{{ reportTypeLabel }}</a-tag>
          <span class="status-item">AI 置信度: {{ taskDetail.ai_confidence || 0 }}%</span>
          <span class="status-item" v-if="reviewProgress.total > 0">
            审核: {{ reviewProgress.reviewed }}/{{ reviewProgress.total }}
          </span>
        </a-space>
        <div class="flow-steps">
          <div
            v-for="(step, idx) in [
              { key: 'parse', title: '段落分类审核' },
              { key: 'entities', title: '领域实体确认' },
              { key: 'commit', title: '入库确认' },
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
            <span v-if="idx < 2" class="flow-step-arrow">›</span>
          </div>
        </div>
      </div>
      <p>{{ taskDetail.file_name }}</p>
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
            <a-button size="small" type="primary" @click="runValidation" :loading="validating">
              运行校验
            </a-button>
            <a-button size="small" @click="triggerEntityDiscovery" :loading="discoveringEntities">
              智能识别实体
            </a-button>
          </a-space>
        </div>

        <div v-if="reviewProgress.total > 0" class="review-progress">
          <a-progress :percent="reviewProgress.percent" :stroke-color="reviewProgress.percent >= 80 ? '#52c41a' : '#1677ff'" size="small" :format="() => `${reviewProgress.reviewed}/${reviewProgress.total}`" />
        </div>

        <!-- 校验结果面板 -->
        <div v-if="validationReport" class="validation-panel">
          <div class="validation-header">
            <span v-if="validationReport.passed" style="color: #52c41a; font-weight: 600">校验通过</span>
            <span v-else style="color: #ff4d4f; font-weight: 600">校验未通过</span>
            <span class="validation-summary">
              {{ validationReport.summary.total_errors }} 错误 · {{ validationReport.summary.total_warnings }} 警告 ·
              {{ validationReport.summary.total_paragraphs }} 段
              <span v-if="validationReport.summary.checked_at" style="color: var(--gray-400); margin-left: 6px">
                {{ new Date(validationReport.summary.checked_at).toLocaleTimeString() }}
              </span>
            </span>
          </div>
          <div v-if="validationReport.errors.length" class="validation-errors">
            <div v-for="(err, i) in validationReport.errors" :key="'err' + i" class="validation-item error-item" @click="scrollToParagraph(err.paragraph_id)">
              <span class="vi-icon"></span>
              <span class="vi-msg">{{ err.message }}</span>
            </div>
          </div>
          <div v-if="validationReport.warnings.length" class="validation-warnings">
            <div v-for="(w, i) in validationReport.warnings.slice(0, 10)" :key="'warn' + i" class="validation-item warn-item" @click="w.paragraph_ids?.length && scrollToParagraph(w.paragraph_ids[0])">
              <span class="vi-icon"></span>
              <span class="vi-msg">{{ w.message }}</span>
              <span v-if="w.slot_name" class="vi-tag">{{ w.slot_name }}</span>
            </div>
            <div v-if="validationReport.warnings.length > 10" class="validation-more">
              ...还有 {{ validationReport.warnings.length - 10 }} 个警告
            </div>
          </div>
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
                  <div class="para-content" :class="{ 'table-content-clamped': para.is_table || para.classify_type === 'table' }">{{ para.content || para.title }}</div>
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
                  <span v-if="selectedParagraph" style="display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--gray-500)">
                    JSON
                    <a-switch
                      :checked="detailEditMode"
                      size="small"
                      @change="(val) => handleToggleEditMode(val)"
                    />
                  </span>
                  <a-button v-if="selectedParagraph" size="small" :loading="saving" @click="async () => { if (detailEditMode) { await handleToggleEditMode(false) } else { const ok = await doSaveParagraphs(); if (ok) message.success('已保存') } }">保存</a-button>
                  <a-button v-if="selectedParagraph" size="small" danger @click="deleteParagraph(selectedParagraph.id)">删除段落</a-button>
                </a-space>
              </template>

              <div v-if="!selectedParagraph" class="detail-empty">
                <FileText :size="36" :stroke-width="1.2" style="color: var(--gray-300, #c0c4cc)" />
                <a-empty description="请点击段落查看详情" :image="false" />
              </div>

              <!-- JSON 编辑模式 -->
              <div v-else-if="detailEditMode" class="detail-section">
                <div class="detail-label" style="margin-bottom: 4px">段落结构化 JSON</div>
                <a-textarea v-model:value="jsonEditValue" :auto-size="{ minRows: 8, maxRows: 24 }" style="font-family: monospace; font-size: 12px" />
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
                <!-- Panel 1: 原始表格 (可拖拽调整高度) -->
                <div class="collapse-panel">
                  <div class="collapse-header" @click="tableDetailExpanded = !tableDetailExpanded">
                    <span class="collapse-title">原始表格</span>
                    <UpOutlined v-if="tableDetailExpanded" style="font-size: 10px" />
                    <DownOutlined v-else style="font-size: 10px" />
                  </div>
                  <div v-show="tableDetailExpanded" class="collapse-body table-detail-body" :style="{ height: tableDetailHeight + 'px' }">
                    <div class="table-detail-content">
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
                    <div
                      class="table-detail-resize-handle"
                      @mousedown="onTableDetailResizeStart"
                    >
                      <div class="resize-grip" />
                    </div>
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
              <div v-else-if="selectedParagraph.classify_type === 'parameter'" class="detail-section parameter-detail-section">
                <!-- 原文区域 -->
                <div class="param-subsection">
                  <div class="detail-label" style="margin-bottom: 4px">原文</div>
                  <div class="detail-text-block param-text-block">{{ selectedParagraph.content }}</div>
                </div>
                <template v-if="selectedParagraph.template?.generalized">
                  <!-- 泛化模板区域 -->
                  <div class="param-subsection">
                    <div class="detail-label" style="margin-bottom: 4px">泛化模板 <span style="font-weight: normal; color: var(--gray-400); font-size: 11px">（选中文字可新建 Slot）</span></div>
                    <div
                      class="detail-text-block template-text-box param-text-block"
                      @click="onTemplateTextClick"
                      @mouseup="onTemplateMouseUp"
                      v-html="highlightedTemplateHtml"
                    ></div>
                    <!-- 选中文字新建 Slot 浮动按钮 -->
                    <div
                      v-if="slotSelection.visible"
                      class="slot-create-popup"
                      :style="{ left: slotSelection.left + 'px', top: slotSelection.top + 'px' }"
                    >
                      <a-button size="small" type="primary" @mousedown.prevent @click="openNewSlotModal">新建 Slot</a-button>
                    </div>
                  </div>
                  <!-- Slot 区域 -->
                  <div class="param-subsection">
                    <div v-if="selectedParagraph.template.slots?.length" class="detail-label" style="margin-bottom: 4px">Slot ({{ selectedParagraph.template.slots.length }})</div>
                    <div v-if="selectedParagraph.template.slots?.length" class="slot-chips-list param-slot-list">
                      <span v-for="slot in selectedParagraph.template.slots" :key="slot.name" class="slot-chip">
                        <a-tag :color="(SLOT_TYPE_MAP[slot.type] || {}).color || 'blue'" size="small">{{ slot.name }}</a-tag>
                        <span v-if="slot.entity_ref" class="slot-chip-ref bound">{{ slot.entity_ref }}</span>
                        <span v-else class="slot-chip-ref unbound">未绑定</span>
                        <a-button type="text" size="small" class="slot-chip-del" @click.stop="removeSlot(selectedParagraph.id, slot.name)"><X :size="11" /></a-button>
                      </span>
                    </div>
                    <a-empty v-else description="暂无 Slot" :image="false" style="padding: 4px 0" />
                  </div>
                  <div v-if="selectedParagraph.template.quality_score != null" class="detail-field" style="margin-top: 6px; flex-shrink: 0">
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

        <!-- 新建 Slot 弹窗 -->
        <a-modal v-model:open="newSlotModalVisible" title="新建 Slot" ok-text="创建" cancel-text="取消" @ok="confirmNewSlot" width="480px">
          <a-form layout="vertical">
            <a-form-item label="原文文字">
              <a-input :value="newSlotForm.value" disabled />
            </a-form-item>
            <a-form-item label="Slot 名称" required>
              <a-input v-model:value="newSlotForm.name" placeholder="如：年平均气温" />
            </a-form-item>
            <a-form-item label="绑定实体属性（可选）">
              <a-select v-model:value="newSlotForm.entity_ref" placeholder="选择推荐绑定或留空不绑定" allow-clear style="width: 100%">
                <a-select-option v-for="s in newSlotForm.suggestions" :key="s.entity_ref" :value="s.entity_ref">
                  {{ s.label }}
                  <span :style="{ color: s.score >= 0.7 ? '#52c41a' : '#faad14', fontSize: '11px', marginLeft: '6px' }">{{ Math.round(s.score * 100) }}%</span>
                </a-select-option>
              </a-select>
              <div v-if="!newSlotForm.suggestions.length" style="font-size: 11px; color: var(--gray-400); margin-top: 4px">无匹配的实体属性推荐，可留空</div>
            </a-form-item>
          </a-form>
        </a-modal>

      </div>

      <!-- ================================================================ -->
      <!-- Step 2: 领域实体确认                                                -->
      <!-- ================================================================ -->
      <div v-show="activeTab === 'entities'" class="flow-content">
        <a-card title="LLM 建议的新实体" :loading="loadingUnrecognizedEntities">
          <template #extra>
            <a-space>
              <a-button size="small" style="font-size: 13px" @click="triggerEntityDiscovery" :loading="discoveringEntities" :disabled="!taskDetail?.id">重新分析</a-button>
              <a-button type="primary" size="small" style="font-size: 13px" @click="batchSaveEntities" :disabled="!selectedEntities.length">确认并保存 ({{ selectedEntities.length }})</a-button>
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
                    selectedRowKeys: selectedEntities.filter(e => entities.some(d => d._row_id === e._row_id)).map(e => e._row_id),
                    onSelect: (record, selected) => {
                      if (selected) { if (!selectedEntities.find(e => e._row_id === record._row_id)) selectedEntities.push(record) }
                      else { const idx = selectedEntities.findIndex(e => e._row_id === record._row_id); if (idx !== -1) selectedEntities.splice(idx, 1) }
                    },
                    onSelectAll: (selected, selectedRows) => {
                      if (selected) { selectedRows.forEach(r => { if (!selectedEntities.find(e => e._row_id === r._row_id)) selectedEntities.push(r) }) }
                      else { const ids = new Set(selectedRows.map(r => r._row_id)); for (let i = selectedEntities.length - 1; i >= 0; i--) { if (ids.has(selectedEntities[i]._row_id)) selectedEntities.splice(i, 1) } }
                    }
                  }"
                  :pagination="entityPagination"
                  row-key="_row_id"
                  size="small"
                  @change="handleTableChange"
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
                        <a-button type="link" size="small" style="font-size: 13px" @click="openEntityEditModal(record)">编辑</a-button>
                        <a-button type="link" size="small" style="font-size: 13px" @click="saveEntityDirectly(record)">确认保存</a-button>
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
            <div v-if="validationReport && !validationReport.passed" class="commit-validation-warn">
              校验未通过（{{ validationReport.summary.total_errors }} 个错误），建议返回
              <a-button type="link" size="small" @click="activeTab = 'parse'" style="padding: 0">Tab 1</a-button>
              修正后再入库
            </div>
            <div v-else-if="validationReport?.passed" class="commit-validation-ok">
              校验通过，可以入库
            </div>
            <div v-else class="commit-validation-hint">
              建议先在 Tab 1 运行校验
            </div>
            <a-button type="primary" size="large" danger @click="handleCommit" :disabled="!selectedKnowledgeBaseId" :loading="saving">
              确认入库
            </a-button>
          </div>
        </a-card>

      </div>

    </div>
  </div>
</template>

<style lang="less" scoped>
.etl-workbench {
  margin: 10px;
  max-width: 100%;
  overflow-x: hidden;
  user-select: text;

  :deep(.ant-card) { max-width: 100%; overflow: hidden; }
  :deep(table) { max-width: 100%; table-layout: fixed; word-wrap: break-word; }
}

.loading-state, .empty-state {
  display: flex; align-items: center; justify-content: center;
  height: 400px; background: var(--gray-0); border-radius: 12px;
}
.empty-state {
  flex-direction: column; gap: 12px;
  color: var(--gray-500); font-size: 13px;
}
.empty-state-icon {
  color: var(--gray-300, #c0c4cc);
}

.workbench-header {
  background: var(--gray-0); padding: 16px 20px 0;
  border-radius: 12px 12px 0 0; border: 1px solid var(--gray-150); border-bottom: none;
  h3 { margin: 0; font-size: 20px; font-weight: 600; }
  p { margin: 4px 0 0; color: var(--gray-500); font-size: 13px; }
}
.header-top { display: flex; align-items: center; gap: 16px; }

.header-status {
  flex-shrink: 0;
  .status-item { font-size: 13px; color: var(--gray-600); }
}

.flow-steps { display: flex; align-items: center; gap: 0; margin-left: auto; }
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
  background: var(--gray-0);
  padding: 10px;
  border: 1px solid var(--gray-150); border-top: none; border-radius: 0 0 12px 12px;
  max-width: 100%; overflow: hidden;
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

.validation-panel {
  margin-bottom: 12px; padding: 10px 14px; border-radius: 6px;
  background: var(--gray-50, #fafafa); border: 1px solid var(--gray-200, #e8e8e8);
  .validation-header { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
  .validation-summary { font-size: 12px; color: var(--gray-600); }
  .validation-errors { margin-bottom: 4px; }
  .validation-warnings { }
  .validation-more { font-size: 11px; color: var(--gray-400); padding-left: 18px; }
  .validation-item {
    display: flex; align-items: baseline; gap: 6px; padding: 3px 0; font-size: 12px;
    cursor: default; line-height: 1.5;
    &.error-item { color: var(--red-600, #cf1322); }
    &.warn-item { color: var(--orange-600, #d46b08); cursor: pointer; &:hover { text-decoration: underline; } }
    .vi-icon { font-size: 11px; flex-shrink: 0; }
    .vi-msg { flex: 1; }
    .vi-tag { font-size: 10px; background: var(--orange-50); padding: 0 4px; border-radius: 2px; flex-shrink: 0; }
  }
}

.parse-row { }

.paragraph-viewer-card {
  height: 560px; display: flex; flex-direction: column;
  :deep(.ant-card-body) { flex: 1; display: flex; flex-direction: column; overflow-y: auto; min-height: 0; }
}

.detail-panel-card {
  height: 560px; display: flex; flex-direction: column;
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
  .table-content-clamped { max-height: 15em; overflow: hidden; }
  .para-summary { color: var(--gray-500); font-size: 11px; line-height: 1.4; margin-top: 3px; padding-left: 4px; border-left: 2px solid var(--gray-200); }
}

// 详情面板
.detail-section {
  flex: 1; display: flex; flex-direction: column; min-height: 0;
}

// parameter 类型三等分布局
.parameter-detail-section {
  gap: 0;
  .param-subsection {
    flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden;
  }
  .param-text-block {
    flex: 1; max-height: none; overflow-y: auto;
  }
  .param-slot-list {
    flex: 1; overflow-y: auto; min-height: 0; align-content: flex-start;
  }
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
  .slot-chip-ref {
    font-size: 11px;
    margin: 0 2px;
    &.bound { color: #52c41a; cursor: default; }
    &.unbound { color: var(--gray-400, #bfbfbf); cursor: default; }
  }
}

.slot-chip-del { padding: 0 2px; color: var(--gray-400); min-width: auto; height: auto; &:hover { color: #ff4d4f; } }

.template-text-box {
  max-height: 100px;
  user-select: text; cursor: text;
  :deep(mark) {
    background: var(--color-warning-50); border: 1px solid var(--color-warning-100); border-radius: 3px; padding: 0 2px;
    cursor: pointer; transition: all 0.15s;
    &:hover { background: var(--color-warning-100); border-color: var(--color-warning-500); }
    &.slot-active { background: var(--color-warning-500); border-color: var(--color-warning-700); color: #fff; }
  }
}

.slot-create-popup {
  position: fixed; z-index: 1000; transform: translateX(-50%);
  background: var(--gray-0); border-radius: 6px; padding: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

// ========== Tab 2: Slot 变量校验 ==========

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
    &.template-text { background: var(--color-success-50); border: 1px solid var(--color-success-100); user-select: text; cursor: text; }
  }
}

.slot-extract-popup {
  position: fixed;
  z-index: 1000;
  transform: translateX(-50%);
  display: flex;
  gap: 6px;
  padding: 4px;
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
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

// 实体确认 tab 字体统一 13px
.flow-content :deep(.ant-table) { font-size: 13px; }
.flow-content :deep(.ant-table-cell) { font-size: 13px; }
.flow-content :deep(.ant-tabs-tab) { font-size: 13px; }
.flow-content :deep(.ant-tag) { font-size: 12px; }

.stat-card {
  text-align: center;
  .stat-value { font-size: 28px; font-weight: 700; color: var(--gray-800); }
  .stat-label { font-size: 12px; color: var(--gray-500); margin-top: 4px; }
}

.commit-actions {
  display: flex; flex-direction: column; align-items: center; padding: 16px 0; gap: 10px;
}
.commit-validation-warn { font-size: 13px; color: var(--red-600, #cf1322); background: var(--red-50, #fff1f0); padding: 6px 14px; border-radius: 4px; }
.commit-validation-ok { font-size: 13px; color: var(--color-success-700); background: var(--color-success-50); padding: 6px 14px; border-radius: 4px; }
.commit-validation-hint { font-size: 12px; color: var(--gray-500); }

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
    td, th { border: 1px solid var(--gray-300); padding: 6px 10px; text-align: left; }
    th { background-color: var(--gray-25); font-weight: 600; }
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

// 原始表格可拖拽区域
.table-detail-body {
  position: relative; display: flex; flex-direction: column; overflow: hidden;
  .table-detail-content {
    flex: 1; overflow: auto; min-height: 0;
  }
}
.table-detail-resize-handle {
  height: 6px; cursor: ns-resize; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 2px;
  &:hover, &:active { background: rgba(24, 144, 255, 0.08); }
  .resize-grip {
    width: 32px; height: 3px; border-radius: 2px; background: var(--gray-300);
    transition: background 0.15s;
  }
  &:hover .resize-grip { background: var(--blue-400, #4096ff); }
}
</style>
