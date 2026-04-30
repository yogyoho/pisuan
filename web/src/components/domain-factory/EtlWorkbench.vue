<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { DeleteOutlined } from '@ant-design/icons-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { databaseApi } from '@/apis/knowledge_api'
import { entityTypeApi } from '@/apis/entity_type_api'
import { useTaskerStore } from '@/stores/tasker'

const props = defineProps({
  task: { type: Object, default: null }
})

const emit = defineEmits(['task-completed', 'task-updated'])

const taskerStore = useTaskerStore()

// ========== 基础状态 ==========
const loading = ref(false)
const saving = ref(false)
const taskDetail = ref(null)
const formValues = ref({})
const activeTab = ref('basic')

// ========== 段落相关状态 ==========
const selectedParagraph = ref(null)
const paragraphJsonDraft = ref('{}')
const paragraphJsonError = ref('')

// ========== 表格相关状态 ==========
const structuredBlocks = ref([])
const structuredJsonDraft = ref('{}')
const structuredHtmlDraft = ref('')
const selectedTable = ref(null)

// ========== 模板相关状态 ==========
const templateDraft = ref({
  original: '',
  generalized: '',
  slots: [],
  metadata: {
    chapter: '',
    tags: []
  }
})
const templateTextarea = ref(null)
const metadataOptions = ref({
  chapters: [],
  tags: []
})
const chapterTree = ref([])
const chapterTreeExpandedKeys = ref([])
const selectedChapter = ref([])
const selectedChapterNode = ref(null)
const chapterParagraphs = ref([])

// ========== 未识别实体相关 ==========
const unrecognizedEntities = ref([])
const groupedUnrecognizedEntities = ref({})
const loadingUnrecognizedEntities = ref(false)
const selectedEntities = ref([])
const entityCategories = ref([])
const entityEditModalVisible = ref(false)
const editingEntity = ref(null)
const activeEntityCategory = ref('')

// ========== 知识库相关 ==========
const lightragKnowledgeBases = ref([])
const selectedKnowledgeBaseId = ref(null)
const loadingKnowledgeBases = ref(false)

// ========== 添加字段弹窗 ==========
const addFieldModalVisible = ref(false)
const newField = ref({
  key: '',
  label: '',
  group: '基础信息',
  unit: '',
  type: 'text',
  widget: 'Input',
  required: false,
  sample: ''
})

// ========== 计算属性 ==========
const schemaFields = computed(() => taskDetail.value?.form_schema || [])

const sourceParagraphs = computed(() => taskDetail.value?.source_paragraphs || [])

const fieldGroups = computed(() => {
  const groups = {}
  schemaFields.value.forEach(field => {
    const group = field.group || '其他'
    if (!groups[group]) groups[group] = []
    groups[group].push(field)
  })
  return groups
})

const highlightedTemplate = computed(() => {
  if (!templateDraft.value || !templateDraft.value.generalized) return ''
  const generalized = String(templateDraft.value.generalized || '')
  return generalized.replace(/(\{\{[^}]+\}\})/g, '<mark>$1</mark>')
})

// 解析 Markdown 表格
// 注意：后端的 _parse_markdown_to_paragraphs 会跳过分隔符行，
// 所以 source_paragraphs 中的表格行不包含分隔符行，
// 这里需要正确处理两种情况：包含分隔符行和不包含分隔符行
const parseMarkdownTable = (md) => {
  const rawLines = (md || '').split('\n').map(l => l.trim()).filter(l => l)
  if (rawLines.length < 2) return { columns: [], rows: [] }

  // 过滤掉分隔符行（| --- | --- | 或类似格式）
  const separatorPattern = /^\|[:\-]+\|[:\-]*\|$/
  const lines = rawLines.filter(l => !separatorPattern.test(l.trim()))
  
  if (lines.length < 1) return { columns: [], rows: [] }

  // 第一行作为表头
  const headerLine = lines[0]
  const header = headerLine
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(s => s.trim())
    .filter(s => s)  // 过滤空单元格

  // 其余行作为数据行（不假设第二行是分隔符）
  const rows = []
  lines.slice(1).forEach(line => {
    if (!line.startsWith('|')) return
    const cols = line
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map(s => s.trim())
    if (!cols.length) return
    const row = {}
    header.forEach((h, idx) => {
      const key = h || `col_${idx + 1}`
      row[key] = cols[idx] ?? ''
    })
    rows.push(row)
  })

  const columns = header.map((h, idx) => {
    const key = h || `col_${idx + 1}`
    return { title: h || `列${idx + 1}`, dataIndex: key }
  })

  return { columns, rows }
}

// 检测 HTML 表格
const isHtmlTable = (content) => {
  return content?.trim().startsWith('<table')
}

// 检测 Markdown 表格
const isMarkdownTable = (content) => {
  if (!content) return false
  const lines = content.split('\n').filter(l => l.trim())
  if (lines.length < 2) return false
  const tableLines = lines.filter(l => {
    const t = l.trim()
    return t.startsWith('|') && t.endsWith('|')
  })
  return tableLines.length >= 2
}

// 生成 HTML 表格（格式化缩进）
const generateTableHtml = (headers, rows) => {
  if (!headers?.length || !rows?.length) return null

  const escapeHtml = (str) => {
    if (str === null || str === undefined) return ''
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
  }

  // 生成表头
  const headerCells = headers.map(h => `    <th>${escapeHtml(h)}</th>`).join('\n')
  const headerRow = `  <tr>\n${headerCells}\n  </tr>`

  // 生成表格行
  const bodyRows = rows.map(row => {
    const cells = headers.map(h => `      <td>${escapeHtml(row[h] ?? '')}</td>`).join('\n')
    return `    <tr>\n${cells}\n    </tr>`
  }).join('\n')

  return `<table>
  <thead>
${headerRow}
  </thead>
  <tbody>
${bodyRows}
  </tbody>
</table>`
}

// 获取表格列表
const tableParagraphs = computed(() => {
  return sourceParagraphs.value.filter(p => {
    if (p.is_table && p.content) return true
    if (p.content && typeof p.content === 'string') {
      const trimmed = p.content.trim()
      if (trimmed.startsWith('<table')) return true
      const lines = p.content.split('\n').filter(l => l.trim())
      const tableLines = lines.filter(l => {
        const t = l.trim()
        return t.startsWith('|') && t.endsWith('|')
      })
      return tableLines.length >= 2
    }
    return false
  })
})

// 原始表格
const originalTables = computed(() => {
  // 优先从 structured_blocks 获取表格（包含完整的 html_content）
  if (structuredBlocks.value?.length > 0) {
    const tableBlocks = structuredBlocks.value.filter(t => t.type === 'table')
    if (tableBlocks.length > 0) {
      return tableBlocks.map((t, idx) => {
        const headers = t.headers || []
        // 后端返回的 rows 可能是 list[list[str]] 或 list[dict]
        const rawRows = t.rows || []
        let rows = rawRows
        let columns = []

        // 如果 rows 是二维数组（list[list[str]]），需要转换为 list[dict] 格式
        if (rawRows.length > 0 && Array.isArray(rawRows[0])) {
          rows = rawRows.map(row => {
            const rowObj = {}
            headers.forEach((h, i) => {
              rowObj[h] = row[i] ?? ''
            })
            return rowObj
          })
          columns = headers.map(h => ({ title: h, dataIndex: h }))
        } else if (rawRows.length > 0 && typeof rawRows[0] === 'object') {
          // 如果已经是 list[dict] 格式
          const firstRow = rawRows[0] || {}
          columns = Object.keys(firstRow).map(k => ({ title: k, dataIndex: k }))
        }

        // 尝试生成 HTML 内容
        let htmlContent = t.html_content || null
        if (!htmlContent && rows.length) {
          // 如果有 headers，使用 headers 生成 HTML
          if (headers.length) {
            htmlContent = generateTableHtml(headers, rows)
          } else if (typeof rows[0] === 'object') {
            // 如果没有 headers 但 rows 是 dict 格式，尝试从第一行提取 key 作为 headers
            const firstRow = rows[0]
            const headerKeys = Object.keys(firstRow)
            if (headerKeys.length) {
              const generatedHeaders = headerKeys.map((k, i) => headers[i] || k)
              htmlContent = generateTableHtml(generatedHeaders, rows)
            }
          }
        }

        return {
          key: t.key || t.id || `blk_${idx + 1}`,
          type: t.caption || t.type || `表格 ${idx + 1}`,
          rows,
          columns,
          htmlContent
        }
      })
    }
  }
  
  // 回退：从 source_paragraphs 构建表格
  const tables = []
  tableParagraphs.value.forEach((p, idx) => {
    const isHtml = isHtmlTable(p.content)
    if (isHtml) {
      tables.push({
        key: p.id || `tbl_${idx + 1}`,
        type: p.title || `表格 ${idx + 1}`,
        htmlContent: p.content,
        rows: [],
        columns: []
      })
    } else {
      const parsed = parseMarkdownTable(p.content)
      if (parsed.rows.length) {
        tables.push({
          key: p.id || `tbl_${idx + 1}`,
          type: p.title || `表格 ${idx + 1}`,
          rows: parsed.rows,
          columns: parsed.columns,
          htmlContent: null
        })
      }
    }
  })
  return tables
})

// ========== 方法 ==========

// 获取任务详情
const fetchTaskDetail = async (taskId) => {
  loading.value = true
  try {
    const detail = await domainFactoryApi.getTaskDetail(taskId)
    taskDetail.value = detail
    
    // 初始化表单值
    const schema = detail?.form_schema || []
    const values = {}
    schema.forEach(field => {
      if (field.suggestion !== undefined && field.suggestion !== null) {
        values[field.key] = field.suggestion
      }
    })
    formValues.value = values
    
    // 初始化结构化数据
    structuredBlocks.value = detail?.structured_blocks || []
    
    // 初始化模板数据
    const templateOriginal = detail?.template?.original
    const templateGeneralized = detail?.template?.generalized
    const templateSlots = detail?.template?.slots || []
    templateDraft.value = {
      original: templateOriginal ? String(templateOriginal) : '',
      generalized: templateGeneralized ? String(templateGeneralized) : '',
      slots: Array.isArray(templateSlots) ? templateSlots : [],
      metadata: detail?.template?.metadata || { chapter: '', tags: [] }
    }
    metadataOptions.value = detail?.metadata_options || { chapters: [], tags: [] }
    
    // 构建章节树
    if (detail?.source_paragraphs?.length > 0) {
      chapterTree.value = buildChapterTree(detail.source_paragraphs)
      chapterTreeExpandedKeys.value = collectTreeKeys(chapterTree.value)
    }
    
    // 异步加载未识别实体
    setTimeout(() => {
      loadUnrecognizedEntities(taskId).catch(() => {})
    }, 100)
  } catch (e) {
    console.error('Failed to fetch task detail:', e)
    message.error('加载任务详情失败')
  } finally {
    loading.value = false
  }
}

// 构建章节树
const buildChapterTree = (paragraphs) => {
  const treeMap = new Map()
  const rootNodes = []

  paragraphs.forEach(para => {
    const rawPath = para.section_path || para.path || []
    const sectionPath = Array.isArray(rawPath) ? rawPath.map(p => String(p)) : [String(rawPath || '')]

    if (!sectionPath.length || !sectionPath[0]) {
      const key = 'uncategorized'
      if (!treeMap.has(key)) {
        const node = { key, title: '未分类段落', children: [], paragraphs: [] }
        treeMap.set(key, node)
        rootNodes.push(node)
      }
      treeMap.get(key).paragraphs.push(para)
      return
    }

    let currentPath = []
    sectionPath.forEach((segment) => {
      currentPath.push(segment)
      const key = currentPath.join('.')

      if (!treeMap.has(key)) {
        const node = { key, title: segment, children: [], paragraphs: [] }
        treeMap.set(key, node)
        if (currentPath.length === 1) {
          rootNodes.push(node)
        } else {
          const parentKey = currentPath.slice(0, -1).join('.')
          const parent = treeMap.get(parentKey)
          if (parent) parent.children.push(node)
        }
      }
      if (currentPath.length === sectionPath.length) {
        treeMap.get(key).paragraphs.push(para)
        if (para.is_title && para.title) {
          treeMap.get(key).title = para.title
        }
      }
    })
  })

  return rootNodes
}

// 收集树节点所有 key
const collectTreeKeys = (nodes) => {
  const keys = []
  const stack = [...nodes]
  while (stack.length > 0) {
    const node = stack.pop()
    if (node?.key) keys.push(node.key)
    if (Array.isArray(node?.children) && node.children.length > 0) {
      for (let i = node.children.length - 1; i >= 0; i--) {
        stack.push(node.children[i])
      }
    }
  }
  return keys
}

// 查找树节点
const findNodeInTree = (nodes, targetKey) => {
  for (const node of nodes || []) {
    if (node.key === targetKey) return node
    if (node.children?.length) {
      const found = findNodeInTree(node.children, targetKey)
      if (found) return found
    }
  }
  return null
}

// 收集章节下所有段落
const collectChapterParagraphs = (node) => {
  if (!node) return []
  const paras = [...(node.paragraphs || [])]
  if (node.children?.length) {
    node.children.forEach(child => {
      paras.push(...collectChapterParagraphs(child))
    })
  }
  return paras
}

// 从模板提取插槽
const extractSlotsFromTemplate = (templateText) => {
  if (!templateText) return []
  const slotPattern = /\{\{([^}]+)\}\}/g
  const slots = new Set()
  let match
  while ((match = slotPattern.exec(templateText)) !== null) {
    const name = (match[1] || '').trim()
    if (name) slots.add(name)
  }
  return Array.from(slots).map(name => ({ name, source: '', status: 'pending' }))
}

// 处理章节点击
const handleChapterClick = (selectedKeys) => {
  if (!selectedKeys?.length) {
    selectedChapter.value = []
    selectedChapterNode.value = null
    chapterParagraphs.value = []
    templateDraft.value = { original: '', generalized: '', slots: [], metadata: { chapter: '', tags: [] } }
    return
  }

  const key = selectedKeys[0]
  const node = findNodeInTree(chapterTree.value, key)
  if (!node) return

  selectedChapter.value = [key]
  selectedChapterNode.value = node
  chapterParagraphs.value = collectChapterParagraphs(node)

  // 拼接原文
  const chapterOriginalText = chapterParagraphs.value
    .map(p => p.is_title && p.title ? String(p.title) : String(p.content || ''))
    .filter(c => c?.trim())
    .join('\n\n')

  // 收集段落模板
  const chapterGeneralizedParts = []
  const allSlotsMap = new Map()
  let hasParagraphTemplate = false

  for (const para of chapterParagraphs.value) {
    const candidate = para.template || para.generalized || null
    const paraGeneralized = candidate?.generalized || candidate || ''
    if (paraGeneralized?.trim()) {
      hasParagraphTemplate = true
      chapterGeneralizedParts.push(String(paraGeneralized).trim())
      const paraSlots = candidate?.slots || extractSlotsFromTemplate(String(paraGeneralized))
      paraSlots.forEach(slot => {
        const slotName = typeof slot === 'string' ? slot : slot.name || slot
        if (slotName && !allSlotsMap.has(slotName)) {
          allSlotsMap.set(slotName, typeof slot === 'string' ? { name: slot, source: '', status: 'pending' } : slot)
        }
      })
    }
  }

  if (hasParagraphTemplate && chapterGeneralizedParts.length > 0) {
    templateDraft.value = {
      original: chapterOriginalText,
      generalized: chapterGeneralizedParts.join('\n\n'),
      slots: Array.from(allSlotsMap.values()),
      metadata: { chapter: node.title, tags: [] }
    }
    return
  }

  // 回退到全局模板
  if (taskDetail.value?.template) {
    const globalTemplate = taskDetail.value.template
    const generalized = String(globalTemplate.generalized || '')
    let slots = globalTemplate.slots || []
    if (!slots?.length) slots = extractSlotsFromTemplate(generalized)
    templateDraft.value = {
      original: chapterOriginalText || generalized,
      generalized,
      slots: Array.isArray(slots) ? slots : [],
      metadata: globalTemplate.metadata || { chapter: node.title, tags: [] }
    }
    return
  }

  templateDraft.value = {
    original: chapterOriginalText,
    generalized: '',
    slots: [],
    metadata: { chapter: node.title, tags: [] }
  }
}

// 段落点击
const handleParagraphClick = (para) => {
  selectedParagraph.value = para
  paragraphJsonDraft.value = JSON.stringify(para, null, 2)
  paragraphJsonError.value = ''
}

// 验证 JSON
const validateJson = () => {
  if (!paragraphJsonDraft.value.trim()) {
    paragraphJsonError.value = ''
    return false
  }
  try {
    JSON.parse(paragraphJsonDraft.value)
    paragraphJsonError.value = ''
    return true
  } catch (error) {
    paragraphJsonError.value = `JSON 格式错误: ${error.message}`
    return false
  }
}

// 应用 JSON 修改
const handleApplyJson = () => {
  if (!selectedParagraph.value) return
  if (!validateJson()) {
    message.error('JSON 格式错误，请修正后再应用')
    return
  }
  try {
    const updatedPara = JSON.parse(paragraphJsonDraft.value)
    if (!updatedPara.id) updatedPara.id = selectedParagraph.value.id
    Object.assign(selectedParagraph.value, updatedPara)
    
    if (taskDetail.value?.source_paragraphs) {
      const index = taskDetail.value.source_paragraphs.findIndex(p => p.id === selectedParagraph.value.id)
      if (index !== -1) {
        Object.assign(taskDetail.value.source_paragraphs[index], updatedPara)
      }
    }
    message.success('JSON 修改已应用到分片')
  } catch (error) {
    message.error('应用 JSON 失败: ' + error.message)
  }
}

// 重置 JSON
const handleResetJson = () => {
  if (selectedParagraph.value) {
    paragraphJsonDraft.value = JSON.stringify(selectedParagraph.value, null, 2)
    paragraphJsonError.value = ''
  }
}

// 表格点击
const handleTableClick = (table) => {
  selectedTable.value = table
  // 始终设置 structuredHtmlDraft 为字符串，htmlContent 为 null/undefined 时设为空字符串
  if (table.htmlContent !== undefined && table.htmlContent !== null) {
    structuredHtmlDraft.value = table.htmlContent
    structuredJsonDraft.value = ''
  } else if (table.rows?.length) {
    structuredJsonDraft.value = JSON.stringify([{ key: table.key, type: table.type, rows: table.rows || [] }], null, 2)
    structuredHtmlDraft.value = ''
  } else {
    structuredJsonDraft.value = ''
    structuredHtmlDraft.value = ''
  }
}

// 格式化 HTML
const formatHtml = () => {
  if (!structuredHtmlDraft.value.trim()) {
    message.warning('没有可格式化的 HTML 内容')
    return
  }
  try {
    const html = structuredHtmlDraft.value.trim()
    const formatted = formatHtmlString(html, 2)
    structuredHtmlDraft.value = formatted
    message.success('HTML 格式化成功')
  } catch (e) {
    message.error('HTML 格式化失败：' + e.message)
  }
}

// HTML 格式化函数
const formatHtmlString = (html, indentSize = 2) => {
  let formatted = ''
  let indent = 0
  const indentStr = ' '.repeat(indentSize)
  
  // 移除多余的空白
  html = html.replace(/>\s+</g, '><').trim()
  
  // 分割标签
  const tokens = html.split(/(<[^>]+>)/)
  
  for (const token of tokens) {
    if (!token.trim()) continue
    
    if (token.match(/^<\/\w/)) {
      // 闭合标签，减少缩进
      indent = Math.max(0, indent - 1)
      formatted += indentStr.repeat(indent) + token + '\n'
    } else if (token.match(/^<\w[^>]*[^\/]>$/)) {
      // 开始标签
      formatted += indentStr.repeat(indent) + token + '\n'
      indent++
    } else if (token.match(/^<\w[^>]*\/>$/)) {
      // 自闭合标签
      formatted += indentStr.repeat(indent) + token + '\n'
    } else if (token.trim()) {
      // 文本内容
      formatted += indentStr.repeat(indent) + token.trim() + '\n'
    }
  }
  
  return formatted.trim()
}

// 应用 HTML
const handleApplyHtml = () => {
  if (!selectedTable.value) {
    message.warning('请先选择要编辑的表格')
    return
  }
  if (!structuredHtmlDraft.value.trim()) {
    message.warning('HTML 内容不能为空')
    return
  }
  if (!structuredHtmlDraft.value.trim().startsWith('<table')) {
    message.error('HTML 格式错误，必须以 <table 开头')
    return
  }
  selectedTable.value.htmlContent = structuredHtmlDraft.value
  if (taskDetail.value?.source_paragraphs) {
    const index = taskDetail.value.source_paragraphs.findIndex(p => p.id === selectedTable.value.key)
    if (index !== -1) {
      taskDetail.value.source_paragraphs[index].content = structuredHtmlDraft.value
    }
  }
  message.success('HTML 已应用到表格')
}

// 保存结构化数据
const handleSaveStructured = async () => {
  if (!taskDetail.value?.id) return
  saving.value = true
  try {
    await domainFactoryApi.saveTaskStep(taskDetail.value.id, {
      step: 'structured',
      payload: {
        structured_blocks: structuredBlocks.value,
        source_paragraphs: taskDetail.value.source_paragraphs
      }
    })
    message.success('表格数据已保存')
    emit('task-updated')
  } catch (e) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 插入插槽
const insertSlot = () => {
  const textarea = templateTextarea.value
  if (!textarea) return
  const selectionStart = textarea.selectionStart
  const selectionEnd = textarea.selectionEnd
  const selectedText = templateDraft.value.generalized.slice(selectionStart, selectionEnd)
  Modal.confirm({
    title: '创建插槽',
    content: `选择文本：${selectedText || '(未选择)'}`,
    okText: '创建',
    cancelText: '取消',
    onOk: () => {
      const slotName = window.prompt('输入插槽名称（如 Location_Desc）')
      if (!slotName) return
      const before = templateDraft.value.generalized.slice(0, selectionStart)
      const after = templateDraft.value.generalized.slice(selectionEnd)
      templateDraft.value.generalized = `${before}{{${slotName}}}${after}`
      templateDraft.value.slots.push({ name: slotName, source: '', status: 'pending' })
    }
  })
}

// 保存模板
const handleSaveTemplate = async () => {
  if (!taskDetail.value?.id) return
  saving.value = true
  try {
    await domainFactoryApi.saveTaskStep(taskDetail.value.id, {
      step: 'template',
      payload: templateDraft.value
    })
    message.success('模板草稿已保存')
    emit('task-updated')
  } catch (e) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 保存基础信息
const handleSave = async () => {
  if (!taskDetail.value?.id) return
  saving.value = true
  try {
    await domainFactoryApi.saveTaskStep(taskDetail.value.id, {
      step: 'basic',
      payload: formValues.value
    })
    message.success('基础信息已保存')
    emit('task-updated')
  } catch (e) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 加载知识库列表
const loadLightragKnowledgeBases = async () => {
  loadingKnowledgeBases.value = true
  try {
    const response = await databaseApi.getDatabases()
    lightragKnowledgeBases.value = (response.databases || []).filter(
      db => db.kb_type === 'lightrag' || db.type === 'lightrag'
    )
    if (lightragKnowledgeBases.value.length === 1) {
      selectedKnowledgeBaseId.value = lightragKnowledgeBases.value[0].db_id || lightragKnowledgeBases.value[0].id
    }
  } catch (e) {
    console.error('加载知识库列表失败', e)
  } finally {
    loadingKnowledgeBases.value = false
  }
}

// 提交入库
const handleCommit = async () => {
  if (!taskDetail.value?.id) return
  if (!selectedKnowledgeBaseId.value) {
    message.warning('请先选择目标知识库')
    return
  }
  Modal.confirm({
    title: '确认入库？',
    content: () => {
      const selectedKB = lightragKnowledgeBases.value.find(
        kb => (kb.db_id || kb.id) === selectedKnowledgeBaseId.value
      )
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
        // 保存所有步骤
        await domainFactoryApi.saveTaskStep(taskDetail.value.id, { step: 'basic', payload: formValues.value })
        await domainFactoryApi.saveTaskStep(taskDetail.value.id, {
          step: 'structured',
          payload: { structured_blocks: structuredBlocks.value, source_paragraphs: taskDetail.value.source_paragraphs }
        })
        await domainFactoryApi.saveTaskStep(taskDetail.value.id, { step: 'template', payload: templateDraft.value })
        
        const result = await domainFactoryApi.commitTask(taskDetail.value.id, {
          form: formValues.value,
          structured: structuredBlocks.value,
          template: templateDraft.value,
          knowledge_base_id: selectedKnowledgeBaseId.value
        })

        if (result?.task?.ingest_task_id) {
          const selectedKB = lightragKnowledgeBases.value.find(
            kb => (kb.db_id || kb.id) === selectedKnowledgeBaseId.value
          )
          taskerStore.registerQueuedTask({
            task_id: result.task.ingest_task_id,
            name: `知识工厂入库: ${taskDetail.value?.file_name || '未知文件'}`,
            task_type: 'domain_factory_commit',
            message: '数据正在同步到 LightRAG 知识库',
            payload: {
              task_id: taskDetail.value.id,
              knowledge_base_id: selectedKnowledgeBaseId.value,
              knowledge_base_name: selectedKB?.name || '',
              file_name: taskDetail.value?.file_name || ''
            }
          })
          message.success('已成功入库，数据正在同步到知识库，请在任务中心查看进度')
        } else {
          message.success('已成功入库')
        }
        emit('task-completed')
      } catch (e) {
        message.error('入库失败')
      } finally {
        saving.value = false
      }
    }
  })
}

// 加载未识别实体
const loadUnrecognizedEntities = async (taskId) => {
  if (!taskId) return
  loadingUnrecognizedEntities.value = true
  try {
    const res = await domainFactoryApi.getUnrecognizedEntities(taskId, 20)
    unrecognizedEntities.value = res.entities || []
    updateGroupedEntities()
  } catch (e) {
    console.error('加载未识别实体失败:', e)
  } finally {
    loadingUnrecognizedEntities.value = false
  }
}

// 加载实体分类
const loadEntityCategories = async () => {
  try {
    const res = await entityTypeApi.listCategories()
    entityCategories.value = res.categories || []
  } catch (e) {
    entityCategories.value = ['基础工程实体', '敏感目标与空间实体', '环境要素与影响实体', '措施与法规实体', '其他']
  }
}

// 更新分组数据
const updateGroupedEntities = () => {
  const grouped = {}
  unrecognizedEntities.value.forEach(entity => {
    const category = entity.category || '其他'
    if (!grouped[category]) grouped[category] = []
    grouped[category].push(entity)
  })
  groupedUnrecognizedEntities.value = grouped
  if (!activeEntityCategory.value && Object.keys(grouped).length > 0) {
    activeEntityCategory.value = Object.keys(grouped)[0]
  }
}

// 打开实体编辑弹窗
const openEntityEditModal = (entity) => {
  editingEntity.value = {
    ...entity,
    keywords: entity.keywords || [],
    examples: entity.examples || [entity.name]
  }
  entityEditModalVisible.value = true
}

// 保存实体
const saveEntity = async () => {
  if (!editingEntity.value?.name) {
    message.warning('请填写实体名称')
    return
  }
  try {
    await entityTypeApi.createEntityType({
      name: editingEntity.value.name,
      category: editingEntity.value.category || '其他',
      description: editingEntity.value.description || '',
      examples: editingEntity.value.examples || [editingEntity.value.name],
      keywords: editingEntity.value.keywords || [],
      metadata: editingEntity.value.metadata || {}
    })
    message.success('实体已保存到实体类型库')
    entityEditModalVisible.value = false
    editingEntity.value = null
    const index = unrecognizedEntities.value.findIndex(e => e.name === editingEntity.value?.name)
    if (index !== -1) {
      unrecognizedEntities.value.splice(index, 1)
      updateGroupedEntities()
    }
  } catch (e) {
    message.error('保存实体失败: ' + (e.message || '未知错误'))
  }
}

// 直接保存实体
const saveEntityDirectly = async (entity) => {
  try {
    await entityTypeApi.createEntityType({
      name: entity.name,
      category: entity.category || '其他',
      description: entity.description || '',
      examples: entity.examples || [entity.name],
      keywords: entity.keywords || [],
      metadata: entity.metadata || {}
    })
    message.success('实体已保存到实体类型库')
    const index = unrecognizedEntities.value.findIndex(e => e.name === entity.name)
    if (index !== -1) unrecognizedEntities.value.splice(index, 1)
    updateGroupedEntities()
    const selectedIndex = selectedEntities.value.findIndex(e => e.name === entity.name)
    if (selectedIndex !== -1) selectedEntities.value.splice(selectedIndex, 1)
  } catch (e) {
    message.error('保存实体失败: ' + (e.message || '未知错误'))
  }
}

// 批量保存
const batchSaveEntities = async () => {
  if (!selectedEntities.value.length) {
    message.warning('请选择要保存的实体')
    return
  }
  try {
    const promises = selectedEntities.value.map(entity =>
      entityTypeApi.createEntityType({
        name: entity.name,
        category: entity.category || '其他',
        description: entity.description || '',
        examples: entity.examples || [entity.name],
        keywords: entity.keywords || [],
        metadata: entity.metadata || {}
      })
    )
    await Promise.all(promises)
    message.success(`成功保存 ${selectedEntities.value.length} 个实体到实体类型库`)
    selectedEntities.value.forEach(entity => {
      const index = unrecognizedEntities.value.findIndex(e => e.name === entity.name)
      if (index !== -1) unrecognizedEntities.value.splice(index, 1)
    })
    selectedEntities.value = []
    updateGroupedEntities()
  } catch (e) {
    message.error('批量保存实体失败: ' + (e.message || '未知错误'))
  }
}

// 打开添加字段弹窗
const openAddFieldModal = () => {
  newField.value = {
    key: '',
    label: '',
    group: '基础信息',
    unit: '',
    type: 'text',
    widget: 'Input',
    required: false,
    sample: selectedParagraph.value?.content?.slice(0, 50) || ''
  }
  addFieldModalVisible.value = true
}

// 确认添加字段
const handleAddFieldConfirm = () => {
  if (!newField.value.label) {
    message.warning('请填写字段标签')
    return
  }
  const key = newField.value.key || newField.value.label.replace(/\s+/g, '_')
  const exists = schemaFields.value.find(f => f.key === key)
  if (exists) {
    message.warning('该字段已存在')
    return
  }
  const anchorId = selectedParagraph.value?.id || null
  taskDetail.value.form_schema.push({
    key,
    label: newField.value.label,
    type: newField.value.type || 'text',
    widget: newField.value.widget || 'Input',
    unit: newField.value.unit || '',
    group: newField.value.group || '基础信息',
    required: !!newField.value.required,
    confidence: 0.5,
    value: '',
    source: '人工新增字段（ETL 校验台）',
    sample: newField.value.sample || '',
    anchor_id: anchorId
  })
  formValues.value[key] = ''
  addFieldModalVisible.value = false
  message.success('字段已添加')
}

// 获取置信度颜色
const getConfidenceColor = (val) => {
  if (val === null || val === undefined) return 'var(--gray-400)'
  if (val >= 0.8) return '#52c41a'
  if (val >= 0.5) return '#faad14'
  return '#ff4d4f'
}

// 滚动到锚点
const scrollToAnchor = async (id) => {
  if (!id) return
  await nextTick()
  const el = document.querySelector(`[data-anchor="${id}"]`)
  if (el) {
    el.classList.add('active')
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setTimeout(() => el.classList.remove('active'), 800)
  }
}

// 监听任务变化
watch(() => props.task, (newTask) => {
  if (newTask?.id) {
    activeTab.value = 'basic'
    fetchTaskDetail(newTask.id)
  } else {
    taskDetail.value = null
    formValues.value = {}
  }
}, { immediate: true })

onMounted(() => {
  loadLightragKnowledgeBases()
  loadEntityCategories()
})

// 使用 h 函数
import { h } from 'vue'
</script>

<template>
  <div class="etl-workbench">
    <a-spin :spinning="loading">
      <div v-if="!taskDetail" class="empty-state">
        <p>请从「数据源管理」选择一个任务开始处理</p>
      </div>
      <div v-else>
        <!-- Header -->
        <div class="workbench-header">
          <div>
            <h3>当前任务：{{ task?.file_name }}</h3>
            <p>
              领域：{{ task?.domain_label || task?.domain }} | 步骤：1.基础信息 -> 2.结构化 -> 3.模板泛化 -> 4.未识别实体
            </p>
          </div>
          <a-space>
            <a-select
              v-model:value="selectedKnowledgeBaseId"
              placeholder="选择目标知识库"
              style="width: 200px"
              :loading="loadingKnowledgeBases"
              :options="lightragKnowledgeBases.map(kb => ({ label: kb.name, value: kb.db_id || kb.id }))"
              allow-clear
            />
            <a-button @click="handleSaveTemplate" :disabled="!taskDetail">保存草稿</a-button>
            <a-button
              type="primary"
              danger
              @click="handleCommit"
              :disabled="!taskDetail || !selectedKnowledgeBaseId"
            >确认入库</a-button>
          </a-space>
        </div>

        <!-- 步骤指示器 -->
        <a-steps
          :current="['basic', 'tables', 'templates', 'entities'].indexOf(activeTab)"
          :items="[{ title: '基础信息' }, { title: '结构化数据' }, { title: '模板泛化' }, { title: '未识别实体' }]"
          size="small"
          class="workbench-steps"
        />

        <!-- Tab 内容 -->
        <a-tabs v-model:activeKey="activeTab" class="workbench-tabs">
          <!-- Tab 1: 基础信息提取校验 -->
          <a-tab-pane key="basic" tab="1. 基础信息提取校验">
            <a-row :gutter="16">
              <a-col :span="12">
                <a-card title="原文查看器" class="paragraph-viewer-card">
                  <div class="scroll-pane">
                    <div
                      v-for="para in sourceParagraphs"
                      :key="para.id"
                      class="paragraph"
                      :class="{ selected: selectedParagraph && selectedParagraph.id === para.id }"
                      :data-anchor="para.id"
                      @click="handleParagraphClick(para)"
                    >
                      <div class="para-title">
                        <span>{{ para.title }}</span>
                        <a-tag v-if="para.is_title" size="small" color="green">标题</a-tag>
                        <a-tag v-if="para.is_table" size="small" color="blue">表格</a-tag>
                        <a-tag
                          v-if="para.section_path?.length"
                          size="small"
                          color="default"
                          class="para-section-tag"
                        >
                          路径：{{ Array.isArray(para.section_path) ? para.section_path.join('.') : para.section_path }}
                        </a-tag>
                      </div>
                      <div v-if="isHtmlTable(para.content)" v-html="para.content" class="html-table-container"></div>
                      <div v-else class="para-content">{{ para.content }}</div>
                    </div>
                  </div>
                </a-card>
              </a-col>
              <a-col :span="12">
                <a-card title="分片JSON数据" class="paragraph-json-card">
                  <div v-if="selectedParagraph" class="json-editor-wrapper">
                    <a-textarea
                      v-model:value="paragraphJsonDraft"
                      :rows="20"
                      class="json-editor-textarea"
                      :class="{ 'json-error': paragraphJsonError }"
                      placeholder="编辑 JSON 数据..."
                      @blur="validateJson"
                    />
                    <div v-if="paragraphJsonError" class="json-error-message">
                      <a-alert type="error" :message="paragraphJsonError" show-icon size="small" />
                    </div>
                    <div class="json-actions">
                      <a-button size="small" type="primary" @click="handleApplyJson" :disabled="!!paragraphJsonError">
                        应用修改
                      </a-button>
                      <a-button size="small" @click="handleResetJson">重置</a-button>
                      <a-button size="small" @click="openAddFieldModal">添加字段</a-button>
                    </div>
                  </div>
                  <div v-else class="json-empty">
                    <a-empty description="请先选择左侧的段落" :image="false" />
                  </div>
                </a-card>
              </a-col>
            </a-row>

            <!-- 提取字段列表 -->
            <a-card title="提取字段" style="margin-top: 16px">
              <div class="form-content">
                <div v-if="!schemaFields.length" class="no-schema">
                  暂无字段配置
                </div>
                <div v-else class="schema-groups">
                  <div v-for="(fields, group) in fieldGroups" :key="group" class="field-group">
                    <div class="group-title">{{ group }}</div>
                    <div class="field-list">
                      <div v-for="field in fields" :key="field.key" class="field-item">
                        <div class="field-label">
                          <span>{{ field.label }}</span>
                          <span v-if="field.required" class="required">*</span>
                          <span v-if="field.unit" class="unit">{{ field.unit }}</span>
                        </div>
                        <div class="field-input">
                          <a-input
                            v-if="!field.options"
                            v-model:value="formValues[field.key]"
                            :placeholder="field.prompt || field.label"
                            :status="field.warning ? 'warning' : undefined"
                          />
                          <a-select
                            v-else
                            v-model:value="formValues[field.key]"
                            :options="field.options.map(o => ({ label: o, value: o }))"
                            placeholder="请选择"
                            style="width: 100%"
                          />
                        </div>
                        <div class="field-meta">
                          <span
                            v-if="field.confidence != null"
                            class="confidence"
                            :style="{ color: getConfidenceColor(field.confidence) }"
                          >
                            置信度: {{ Math.round((field.confidence || 0) * 100) }}%
                          </span>
                          <span v-if="field.warning" class="warning-msg">{{ field.warning }}</span>
                          <span v-if="field.source" class="source-info">{{ field.source }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </a-card>
          </a-tab-pane>

          <!-- Tab 2: 表格提取校验 -->
          <a-tab-pane key="tables" tab="2. 表格提取校验">
            <a-row :gutter="16" class="tables-row">
              <a-col :span="13" class="tables-col">
                <a-card title="原文表格" class="tables-card">
                  <div class="scroll-pane">
                    <div v-if="originalTables.length === 0" class="empty-tables">
                      <a-empty description="暂无表格数据" :image="false" />
                    </div>
                    <div
                      v-for="table in originalTables"
                      :key="table.key"
                      class="table-block"
                      :class="{ selected: selectedTable && selectedTable.key === table.key }"
                      @click="handleTableClick(table)"
                    >
                      <h4>{{ table.type }} · {{ table.rows?.length || 0 }} 条</h4>
                      <div v-if="table.htmlContent !== undefined && table.htmlContent !== null" v-html="table.htmlContent" class="html-table-container"></div>
                      <a-table
                        v-else-if="table.rows?.length"
                        :data-source="table.rows"
                        :pagination="false"
                        size="small"
                        :columns="table.columns"
                      />
                    </div>
                  </div>
                </a-card>
              </a-col>
              <a-col :span="11" class="tables-col">
                <a-card title="HTML 表格预览" class="tables-card">
                  <div class="json-toolbar">
                    <span v-if="selectedTable">当前编辑：{{ selectedTable.type }}</span>
                    <span v-else>请点击左侧表格进行编辑</span>
                    <a-space>
                      <a-button size="small" @click="formatHtml" :disabled="!structuredHtmlDraft">格式化</a-button>
                      <a-button size="small" @click="handleApplyHtml" :disabled="!selectedTable">应用 HTML</a-button>
                    </a-space>
                  </div>
                  <!-- HTML 实时预览 -->
                  <div v-if="structuredHtmlDraft" class="html-preview-wrapper">
                    <div class="html-preview-label">预览效果：</div>
                    <div class="html-preview-content html-table-container" v-html="structuredHtmlDraft"></div>
                  </div>
                  <div v-else-if="selectedTable && !structuredHtmlDraft" class="html-preview-empty">
                    <a-empty description="暂无 HTML 预览" :image="false" />
                  </div>
                  <textarea
                    v-model="structuredHtmlDraft"
                    class="json-editor"
                    spellcheck="false"
                    :placeholder="selectedTable ? '编辑当前表格的 HTML 代码' : '请先选择左侧表格'"
                  ></textarea>
                  <div class="panel-actions">
                    <a-button
                      type="primary"
                      @click="handleSaveStructured"
                      :loading="saving"
                      :disabled="!selectedTable"
                    >保存表格数据</a-button>
                  </div>
                </a-card>
              </a-col>
            </a-row>
          </a-tab-pane>

          <!-- Tab 3: 模板泛化 -->
          <a-tab-pane key="templates" tab="3. 模板泛化与插槽编辑">
            <a-row :gutter="16">
              <a-col :span="8">
                <a-card title="目录章节">
                  <div class="chapter-tree-wrapper">
                    <a-tree
                      v-model:selectedKeys="selectedChapter"
                      v-model:expandedKeys="chapterTreeExpandedKeys"
                      :tree-data="chapterTree"
                      :field-names="{ children: 'children', title: 'title', key: 'key' }"
                      @select="handleChapterClick"
                    >
                      <template #title="{ title, dataRef }">
                        <span>{{ dataRef?.title || title || dataRef?.key || '未命名章节' }}</span>
                        <a-tag
                          v-if="dataRef?.paragraphs?.length"
                          size="small"
                          color="blue"
                          style="margin-left: 8px"
                        >
                          {{ dataRef.paragraphs.length }} 段
                        </a-tag>
                      </template>
                    </a-tree>
                  </div>
                </a-card>

                <a-card title="LLM 自动泛化结果" class="mt16" v-if="selectedChapterNode">
                  <div class="template-header">
                    <div>
                      <h4 style="margin: 0">{{ selectedChapterNode.title }}</h4>
                      <span style="color: var(--gray-500); font-size: 12px">
                        共 {{ chapterParagraphs.length }} 个段落
                      </span>
                    </div>
                    <a-space>
                      <a-button size="small" @click="insertSlot">插入插槽</a-button>
                      <a-button size="small" @click="() => templateDraft.generalized = templateDraft.original">
                        恢复原文
                      </a-button>
                    </a-space>
                  </div>
                  <textarea
                    ref="templateTextarea"
                    v-model="templateDraft.generalized"
                    class="template-textarea"
                    spellcheck="false"
                    :placeholder="templateDraft.original ? '编辑模板内容，使用 {{Slot_Name}} 格式插入插槽' : '请先选择包含原文的章节'"
                  ></textarea>
                  
                  <div class="slot-list" v-if="templateDraft.slots?.length">
                    <div class="slot-row" v-for="slot in templateDraft.slots" :key="slot.name">
                      <div class="slot-name">{{ slot.name }}</div>
                      <a-select v-model:value="slot.source" placeholder="选择数据来源" style="flex: 1">
                        <a-select-option value="空间数据">空间数据</a-select-option>
                        <a-select-option value="临时变量">临时变量(需补录)</a-select-option>
                        <a-select-option value="智能体推理">智能体推理生成</a-select-option>
                      </a-select>
                    </div>
                  </div>
                  <div v-else class="slot-empty">
                    <a-empty description="暂无插槽，可在模板中使用 {{Slot_Name}} 格式插入" :image="false" />
                  </div>
                  
                  <a-divider />
                  <a-form layout="vertical">
                    <a-form-item label="适用章节">
                      <a-select
                        v-model:value="templateDraft.metadata.chapter"
                        :options="metadataOptions.chapters?.map(item => ({ label: item, value: item }))"
                        show-search
                        allow-clear
                      />
                    </a-form-item>
                    <a-form-item label="适用场景">
                      <a-select
                        v-model:value="templateDraft.metadata.tags"
                        mode="multiple"
                        :options="metadataOptions.tags?.map(item => ({ label: item, value: item }))"
                        allow-clear
                      />
                    </a-form-item>
                  </a-form>
                  <div class="panel-actions">
                    <a-button type="primary" @click="handleSaveTemplate" :loading="saving">
                      保存模板草稿
                    </a-button>
                  </div>
                </a-card>

                <a-card title="LLM 自动泛化结果" class="mt16" v-else>
                  <a-empty description="请从左侧选择章节以查看和编辑模板" :image="false" />
                </a-card>
              </a-col>
              <a-col :span="16">
                <a-card title="Diff 预览" v-if="selectedChapterNode">
                  <div class="diff-view" v-if="templateDraft.original || templateDraft.generalized">
                    <div class="diff-original">
                      <h5>原文</h5>
                      <p v-if="templateDraft.original">{{ templateDraft.original }}</p>
                      <p v-else class="empty-text">暂无原文数据</p>
                    </div>
                    <div class="diff-template">
                      <h5>模板</h5>
                      <p v-if="highlightedTemplate" v-html="highlightedTemplate"></p>
                      <p v-else class="empty-text">暂无模板数据</p>
                    </div>
                  </div>
                  <a-empty v-else description="该章节暂无模板数据" :image="false" />
                </a-card>
                <a-card title="Diff 预览" class="mt16" v-else>
                  <a-empty description="请从左侧选择章节" :image="false" />
                </a-card>
              </a-col>
            </a-row>
          </a-tab-pane>

          <!-- Tab 4: 未识别实体 -->
          <a-tab-pane key="entities" tab="4. 未识别实体">
            <a-card title="未识别实体列表" :loading="loadingUnrecognizedEntities">
              <template #extra>
                <a-space>
                  <a-button size="small" @click="loadUnrecognizedEntities(taskDetail?.id)" :disabled="!taskDetail?.id">
                    重新提取
                  </a-button>
                  <a-button type="primary" size="small" @click="batchSaveEntities" :disabled="!selectedEntities.length">
                    批量保存 ({{ selectedEntities.length }})
                  </a-button>
                </a-space>
              </template>

              <a-alert
                v-if="unrecognizedEntities.length === 0 && !loadingUnrecognizedEntities"
                message="未发现未识别的实体"
                description="文档中的所有实体都已存在于实体类型库中，或文档中未包含可识别的实体。"
                type="info"
                show-icon
                style="margin-bottom: 16px"
              />

              <div v-else>
                <a-tabs v-model:activeKey="activeEntityCategory" type="card">
                  <a-tab-pane
                    v-for="(entities, category) in groupedUnrecognizedEntities"
                    :key="category"
                    :tab="`${category} (${entities.length})`"
                  >
                    <a-table
                      :data-source="entities"
                      :columns="[
                        { title: '实体名称', dataIndex: 'name', key: 'name', width: 150, ellipsis: true },
                        { title: '分类', dataIndex: 'category', key: 'category', width: 100 },
                        { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
                        { title: '上下文', dataIndex: 'context', key: 'context', ellipsis: true, width: 150 },
                        { title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 80 },
                        { title: '操作', key: 'action', width: 100 }
                      ]"
                      :row-selection="{
                        selectedRowKeys: selectedEntities.map(e => e.name),
                        onSelect: (record, selected) => {
                          if (selected) selectedEntities.push(record)
                          else {
                            const idx = selectedEntities.findIndex(e => e.name === record.name)
                            if (idx !== -1) selectedEntities.splice(idx, 1)
                          }
                        }
                      }"
                      :pagination="{ pageSize: 10 }"
                      row-key="name"
                      size="small"
                    >
                      <template #bodyCell="{ column, record }">
                        <template v-if="column.key === 'confidence'">
                          <span
                            :style="{ color: Math.round(record.confidence * 100) >= 80 ? '#52c41a' : Math.round(record.confidence * 100) >= 60 ? '#faad14' : '#ff4d4f' }"
                          >
                            {{ Math.round(record.confidence * 100) }}%
                          </span>
                        </template>
                        <template v-else-if="column.key === 'action'">
                          <a-space>
                            <a-button type="link" size="small" @click="openEntityEditModal(record)">编辑</a-button>
                            <a-button type="link" size="small" @click="saveEntityDirectly(record)">保存</a-button>
                          </a-space>
                        </template>
                      </template>
                    </a-table>
                  </a-tab-pane>
                </a-tabs>
              </div>
            </a-card>

            <!-- 编辑实体弹窗 -->
            <a-modal
              v-model:open="entityEditModalVisible"
              title="编辑实体信息"
              ok-text="保存到实体类型库"
              cancel-text="取消"
              @ok="saveEntity"
              width="600px"
            >
              <a-form layout="vertical" v-if="editingEntity">
                <a-form-item label="实体名称" required>
                  <a-input v-model:value="editingEntity.name" placeholder="请输入实体名称" />
                </a-form-item>
                <a-form-item label="分类" required>
                  <a-select
                    v-model:value="editingEntity.category"
                    placeholder="请选择分类"
                    :options="entityCategories.map(cat => ({ label: cat, value: cat }))"
                    show-search
                    allow-clear
                  />
                </a-form-item>
                <a-form-item label="描述">
                  <a-textarea v-model:value="editingEntity.description" placeholder="请输入实体描述" :rows="3" />
                </a-form-item>
                <a-form-item label="上下文">
                  <a-textarea :value="editingEntity.context" placeholder="实体出现的上下文" :rows="2" disabled />
                </a-form-item>
              </a-form>
            </a-modal>
          </a-tab-pane>
        </a-tabs>

        <!-- 添加字段弹窗 -->
        <a-modal
          v-model:open="addFieldModalVisible"
          title="手动添加领域字段"
          @ok="handleAddFieldConfirm"
          :confirm-loading="loading"
        >
          <a-form layout="vertical">
            <a-form-item label="字段标签" required>
              <a-input v-model:value="newField.label" placeholder="例如：服务年限" />
            </a-form-item>
            <a-form-item label="分组">
              <a-select v-model:value="newField.group" :options="[
                { label: '基础信息', value: '基础信息' },
                { label: '工程参数', value: '工程参数' },
                { label: '空间数据', value: '空间数据' },
                { label: '其他', value: '其他' }
              ]" />
            </a-form-item>
            <a-form-item label="数据类型">
              <a-select v-model:value="newField.type" :options="[
                { label: '文本', value: 'text' },
                { label: '数字', value: 'number' },
                { label: '选择', value: 'select' }
              ]" />
            </a-form-item>
            <a-form-item label="控件类型">
              <a-select v-model:value="newField.widget" :options="[
                { label: 'Input', value: 'Input' },
                { label: 'InputNumber', value: 'InputNumber' },
                { label: 'Select', value: 'Select' },
                { label: 'Textarea', value: 'Textarea' }
              ]" />
            </a-form-item>
            <a-form-item label="单位">
              <a-input v-model:value="newField.unit" placeholder="例如：Mt/a, 年, mm" />
            </a-form-item>
            <a-form-item>
              <a-checkbox v-model:checked="newField.required">必填</a-checkbox>
            </a-form-item>
          </a-form>
        </a-modal>
      </div>
    </a-spin>
  </div>
</template>

<style lang="less" scoped>
.etl-workbench {
  margin-top: 16px;
  max-width: 100%;
  overflow-x: hidden;

  // 确保所有子元素不超过容器宽度
  :deep(.ant-card) {
    max-width: 100%;
    overflow: hidden;
  }

  // 确保表格不会撑开容器
  :deep(table) {
    max-width: 100%;
    table-layout: fixed;
    word-wrap: break-word;
  }
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: var(--gray-500);
  font-size: 14px;
  background: #fff;
  border-radius: 12px;
}

.workbench-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  padding: 16px 20px;
  border-radius: 12px 12px 0 0;
  border: 1px solid var(--gray-150);
  border-bottom: none;

  h3 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
  }

  p {
    margin: 4px 0 0;
    color: var(--gray-500);
    font-size: 13px;
  }
}

.workbench-steps {
  background: #fff;
  padding: 12px 20px;
  border: 1px solid var(--gray-150);
  border-top: none;
  border-radius: 0;
}

.workbench-tabs {
  background: #fff;
  padding: 16px 20px;
  border: 1px solid var(--gray-150);
  border-top: none;
  border-radius: 0 0 12px 12px;
  margin-bottom: 24px;
  max-width: 100%;
  overflow: hidden;

  :deep(.ant-tabs-nav) {
    margin-bottom: 16px;
  }

  :deep(.ant-tabs-content) {
    max-width: 100%;
    overflow-x: hidden;
  }
}

.paragraph-viewer-card,
.paragraph-json-card,
.tables-card {
  height: 500px;
  display: flex;
  flex-direction: column;

  :deep(.ant-card-body) {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
  }
}

.scroll-pane {
  flex: 1;
  overflow-y: auto;
  padding-right: 8px;
  min-height: 0;
}

.paragraph {
  padding: 12px 0;
  border-bottom: 1px dashed var(--gray-150);
  cursor: pointer;

  &.selected {
    background-color: rgba(24, 144, 255, 0.06);
    border-left: 3px solid #1890ff;
    padding-left: 9px;
  }

  .para-title {
    font-weight: 600;
    margin-bottom: 6px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;

    .para-section-tag {
      font-weight: 400;
    }
  }

  .para-content {
    color: var(--gray-700);
    line-height: 1.6;
  }
}

.json-editor-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: hidden;

  .json-editor-textarea {
    flex: 1;
    width: 100%;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 12px;
    line-height: 1.5;
    background: #0b1120;
    color: #e5e7eb;
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    resize: none;

    &.json-error {
      border-color: #ff4d4f;
    }
  }
}

.json-error-message {
  margin-top: 4px;
}

.json-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.json-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  flex: 1;
}

.json-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--gray-500);
}

.json-editor {
  width: 100%;
  max-width: 100%;
  min-height: 360px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  padding: 12px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  overflow-wrap: break-word;
  word-break: break-word;
}

.table-block {
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: var(--gray-300);
    background-color: var(--gray-50);
  }

  &.selected {
    border-color: #1890ff;
    background-color: rgba(24, 144, 255, 0.06);
  }

  h4 {
    margin: 0 0 12px;
    font-size: 14px;
    font-weight: 600;
    color: var(--gray-700);
  }
}

.html-table-container {
  margin: 12px 0;
  overflow-x: auto;

  :deep(table) {
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;

    td, th {
      border: 1px solid #d9d9d9;
      padding: 8px 12px;
      text-align: left;
    }

    th {
      background-color: #fafafa;
      font-weight: 600;
    }
  }
}

.html-preview-wrapper {
  margin-bottom: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  overflow: hidden;
}

.html-preview-label {
  padding: 8px 12px;
  background: var(--gray-50);
  font-size: 12px;
  color: var(--gray-600);
  border-bottom: 1px solid var(--gray-200);
}

.html-preview-content {
  max-height: 200px;
  overflow-y: auto;
  padding: 12px;
  background: #fff;
}

.html-preview-empty {
  padding: 24px 0;
  margin-bottom: 12px;
  border: 1px dashed var(--gray-200);
  border-radius: 8px;
}

// 表格单元格样式优化 - 移除浏览器默认的 focus outline
.table-block {
  :deep(table) {
    td, th {
      outline: none;

      &:focus {
        outline: none;
      }
    }
  }
}

.tables-row {
  .tables-col {
    display: flex;
    flex-direction: column;
  }
}

.mt16 {
  margin-top: 16px;
}

.chapter-tree-wrapper {
  max-height: 300px;
  overflow-y: auto;
}

.template-textarea {
  width: 100%;
  max-width: 100%;
  min-height: 150px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  padding: 12px;
  font-family: monospace;
  font-size: 13px;
  resize: vertical;
  margin-top: 12px;
  overflow-wrap: break-word;
  word-break: break-word;
}

.template-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;

  h4 {
    margin: 0;
  }
}

.slot-list {
  margin-top: 16px;
  max-height: 200px;
  overflow-y: auto;

  .slot-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    border: 1px solid var(--gray-200);
    border-radius: 4px;
    background: var(--gray-50);
    margin-bottom: 8px;

    .slot-name {
      font-size: 12px;
      font-weight: 500;
      font-family: monospace;
      color: var(--gray-600);
      min-width: 120px;
    }
  }
}

.slot-empty {
  margin-top: 16px;
  padding: 20px 0;
}

.diff-view {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  max-width: 100%;
  overflow: hidden;

  h5 {
    margin: 0 0 8px;
    font-weight: 600;
    color: var(--gray-700);
  }

  p {
    background: var(--gray-100);
    padding: 12px;
    border-radius: 8px;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.6;
    margin: 0;
    max-width: 100%;
    overflow-wrap: break-word;

    &.empty-text {
      color: var(--gray-400);
      font-style: italic;
      text-align: center;
    }
  }
}

mark {
  background: rgba(24, 144, 255, 0.2);
  padding: 0 2px;
  border-radius: 4px;
}

.panel-actions {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.form-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.no-schema {
  color: var(--gray-400);
  text-align: center;
  padding: 40px 0;
  font-size: 13px;
}

.schema-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.field-group {
  .group-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--main-color);
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--gray-100);
  }
}

.field-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field-item {
  .field-label {
    font-size: 12px;
    color: var(--gray-700);
    margin-bottom: 6px;

    .required {
      color: #ff4d4f;
      margin-left: 2px;
    }

    .unit {
      color: var(--gray-400);
      margin-left: 4px;
      font-size: 11px;
    }
  }

  .field-meta {
    font-size: 11px;
    margin-top: 4px;
    display: flex;
    gap: 8px;
    align-items: center;

    .confidence {
      font-weight: 500;
    }

    .warning-msg {
      color: #faad14;
    }

    .source-info {
      color: var(--gray-400);
      font-size: 10px;
    }
  }
}

.empty-tables {
  padding: 40px 0;
  text-align: center;
}
</style>
