import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { domainEntityBuilderApi } from '@/apis/domain_entity_builder_api'

// 去领域化：本页固定通用域作用域，避免多域数据串台
const DOMAIN_CODE = 'general'

// 与后端 validate_key 同口径：非空、无空白与点号、≤64 字符
export const KEY_PATTERN = /^[^\s.。]{1,64}$/

export const VALUE_TYPE_OPTIONS = [
  'String',
  'Integer',
  'Float',
  'Boolean',
  'Enum',
  'Object',
  'List'
]

// 泛化 prompt 的属性上限，与后端 `_load_entity_schema_variables(max_items=60)` 同口径
export const PROMPT_PROPERTY_LIMIT = 60

// 按码点比较：实测与 PG `ORDER BY category, name_cn`（en_US.utf8）逐行一致（71/71）
const compareText = (a, b) => {
  const left = a || ''
  const right = b || ''
  return left < right ? -1 : left > right ? 1 : 0
}

/**
 * 泛化 prompt 覆盖测算：后端逐实体（category、name_cn 排序）累计有 name_cn 的属性，
 * 取前 PROMPT_PROPERTY_LIMIT 个写进泛化提示词，其余属性 LLM 看不到。
 * 这里复算同一份集合，供页面标注「进 prompt / 被截断」。
 */
export const computePromptCoverage = (entities, limit = PROMPT_PROPERTY_LIMIT) => {
  const ordered = [...(entities || [])].sort(
    (a, b) => compareText(a.category, b.category) || compareText(a.name_cn, b.name_cn)
  )
  const coveredRefs = new Set()
  const byEntity = {}
  let covered = 0
  let eligible = 0
  for (const entity of ordered) {
    let hit = 0
    for (const prop of entity.properties || []) {
      if (!prop?.key || !(prop.name_cn || '').trim()) continue
      eligible += 1
      if (covered >= limit) continue
      coveredRefs.add(`${entity.entity_key}.${prop.key}`)
      covered += 1
      hit += 1
    }
    byEntity[entity.entity_id] = hit
  }
  return { limit, covered, eligible, coveredRefs, byEntity }
}

export const normalizeValueType = (value) => {
  if (!value || typeof value !== 'string') return 'String'
  if (value.startsWith('List')) {
    if (value.includes('<Object>')) return 'Object'
    if (value.includes('<String>')) return 'String'
    if (value.includes('<Integer>')) return 'Integer'
    if (value.includes('<Float>')) return 'Float'
    return 'List'
  }
  return VALUE_TYPE_OPTIONS.includes(value) ? value : 'String'
}

/** 编辑副本：JSON 深拷贝 + 值类型归一 + 规则条件/动作反序列化。 */
export const normalizeEntityForEditing = (entity) => {
  const copy = JSON.parse(JSON.stringify(entity))
  copy.value_type = normalizeValueType(copy.value_type)
  if (copy.properties?.length) {
    copy.properties = copy.properties.map((prop) => ({
      ...prop,
      value_type: normalizeValueType(prop.value_type)
    }))
  }
  if (copy.relation_rules?.length) {
    copy.relation_rules = copy.relation_rules.map((rule) => {
      const nr = {
        rule_id: rule.rule_id || `rule_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        rule_name: rule.rule_name || '未命名规则',
        condition: {},
        actions: [],
        description: rule.description || ''
      }
      if (rule.condition) {
        if (typeof rule.condition === 'string') {
          try {
            nr.condition = JSON.parse(rule.condition)
          } catch {
            nr.condition = {}
          }
        } else if (
          typeof rule.condition === 'object' &&
          rule.condition !== null &&
          !Array.isArray(rule.condition)
        ) {
          nr.condition = rule.condition
        }
      }
      if (rule.actions) {
        if (Array.isArray(rule.actions)) {
          nr.actions = rule.actions
        } else if (typeof rule.actions === 'string') {
          try {
            nr.actions = JSON.parse(rule.actions)
          } catch {
            nr.actions = []
          }
        }
      }
      return nr
    })
  }
  copy.domain_code = DOMAIN_CODE // 去领域化：实体归属统一通用域
  return copy
}

const emptyDraft = (category) => ({
  entity_id: null,
  entity_key: '',
  name_cn: '',
  category: category || 'project_basic',
  domain_code: DOMAIN_CODE,
  value_type: 'String',
  unit: '',
  is_list_type: false,
  description: '',
  synonyms: [],
  properties: [],
  relation_rules: [],
  metadata: {}
})

/** 保存前草稿校验：键长度/空白/点号、名称、分类、属性键重复。 */
export const validateEntityDraft = (draft) => {
  if (!KEY_PATTERN.test((draft.entity_key || '').trim())) {
    return '实体键不能为空、不能含空白或点号，且不超过 64 字符'
  }
  if (!draft.name_cn?.trim()) return '请填写中文名称'
  if (!draft.category) return '请选择分类'
  const seen = new Set()
  for (const [index, prop] of (draft.properties || []).entries()) {
    const key = (prop.key || '').trim()
    if (!KEY_PATTERN.test(key)) {
      return `第 ${index + 1} 个属性的键不能为空、不能含空白或点号`
    }
    if (seen.has(key.toLowerCase())) return `属性键 ${key} 重复`
    seen.add(key.toLowerCase())
  }
  return ''
}

/**
 * 实体构建器页面状态：加载、编辑副本与基线（脏状态）、CRUD、树数据。
 *
 * 脏状态用「草稿 JSON 快照」对比实现：`draft` 是深拷贝出的编辑副本，
 * `baselineJson` 是选中/保存时的快照，任何嵌套字段改动都会反映到 isDirty。
 * 组件内不自行 load；写操作统一走这里，加载后按 entity_key 恢复选中。
 */
export function useEntitySchemas() {
  const taxonomy = ref(null)
  const schemas = ref([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const selectedEntity = ref(null) // 已落库实体，取消编辑时回滚的依据
  const draft = ref(null) // 编辑中的副本
  const baselineJson = ref('')

  // 引用影响面（模板/待审核任务/报告参数/区域事实），按当前选中实体加载
  const usage = ref(null)
  const usageLoading = ref(false)
  const usageError = ref('')
  let usageReqId = 0

  const markClean = () => {
    baselineJson.value = draft.value ? JSON.stringify(draft.value) : ''
  }

  const isDirty = computed(
    () => Boolean(draft.value) && JSON.stringify(draft.value) !== baselineJson.value
  )

  const promptCoverage = computed(() => computePromptCoverage(schemas.value))

  const loadUsage = async (entityKey) => {
    const reqId = ++usageReqId
    usage.value = null
    usageError.value = ''
    if (!entityKey) {
      usageLoading.value = false
      return
    }
    usageLoading.value = true
    try {
      const res = await domainEntityBuilderApi.getEntityUsage(entityKey)
      if (reqId !== usageReqId) return
      usage.value = res.success ? res.data : null
      if (!res.success) usageError.value = '使用情况加载失败'
    } catch (e) {
      if (reqId !== usageReqId) return
      console.error('加载使用情况失败', e)
      usageError.value = e?.message || '使用情况加载失败'
    } finally {
      if (reqId === usageReqId) usageLoading.value = false
    }
  }

  // 删除前取最新影响面；失败时抛给调用方决定是否继续
  const fetchUsage = async (identifier) => {
    const res = await domainEntityBuilderApi.getEntityUsage(identifier)
    return res.data
  }

  const categoryOptions = computed(() => {
    const options = []
    taxonomy.value?.domains?.forEach((domain) => {
      domain.categories?.forEach((category) => {
        if (category.category_name && !options.some((o) => o.value === category.category_name)) {
          options.push({ label: category.category_name, value: category.category_name })
        }
      })
    })
    return options
  })

  const treeData = computed(() =>
    (taxonomy.value?.domains || [])
      .map((domain) => {
        const category = domain.categories?.[0]
        if (!category) return null
        const categoryName = category.category_name
        const entities = schemas.value.filter((entity) => (entity.category || '') === categoryName)
        return {
          title: domain.domain_name, // 计数在节点右侧单独渲染，避免重复
          key: domain.domain_id,
          count: entities.length,
          isLeaf: false,
          search_text: `${domain.domain_name} ${categoryName}`,
          children: [
            ...entities.map((entity) => ({
              title: entity.name_cn,
              key: `entity_${entity.entity_id}`,
              entity_id: entity.entity_id,
              entity_key: entity.entity_key,
              isLeaf: true,
              search_text: [entity.name_cn, entity.entity_key, entity.description]
                .concat(entity.synonyms || [])
                .filter(Boolean)
                .join(' ')
            })),
            {
              title: '+ 新建实体',
              key: `new_${domain.domain_id}`,
              category: categoryName,
              isLeaf: true,
              isNew: true,
              search_text: ''
            }
          ]
        }
      })
      .filter(Boolean)
  )

  const select = (entity) => {
    selectedEntity.value = entity
    draft.value = normalizeEntityForEditing(entity)
    markClean()
    void loadUsage(entity.entity_key)
  }

  const selectByKey = (entityKey) => {
    const entity = schemas.value.find(
      (item) =>
        item.entity_key === entityKey ||
        item.entity_id === entityKey ||
        item.entity_id === `${entityKey}_schema` ||
        item.metadata?.legacy_id === entityKey
    )
    if (!entity) return false
    select(entity)
    return true
  }

  const clearSelection = () => {
    selectedEntity.value = null
    draft.value = null
    markClean()
    void loadUsage(null)
  }

  const startCreate = (category) => {
    selectedEntity.value = null
    draft.value = emptyDraft(category)
    markClean()
    void loadUsage(null)
  }

  const resetDraft = () => {
    if (selectedEntity.value) select(selectedEntity.value)
    else clearSelection()
  }

  /**
   * 重新拉取分类与实体。
   * - entityKey：加载后按 key 选中（保存/克隆后保持选中）。
   * - preserveDraft：保留当前编辑副本（删除其他实体时不打断未保存修改）。
   */
  const load = async ({ entityKey = null, preserveDraft = false } = {}) => {
    loading.value = true
    error.value = ''
    try {
      const [taxRes, schemasRes] = await Promise.all([
        domainEntityBuilderApi.getTaxonomy(DOMAIN_CODE),
        domainEntityBuilderApi.listEntitySchemas(null, DOMAIN_CODE)
      ])
      if (taxRes.success) taxonomy.value = taxRes.data
      if (schemasRes.success) schemas.value = schemasRes.data.entity_schemas || []
      if (preserveDraft && draft.value) {
        const currentId = draft.value.entity_id
        selectedEntity.value =
          schemas.value.find((entity) => entity.entity_id === currentId) || null
      } else if (entityKey) {
        selectByKey(entityKey)
      }
    } catch (e) {
      console.error('加载数据失败', e)
      error.value = e?.message || '加载数据失败'
      message.error(error.value)
    } finally {
      loading.value = false
    }
  }

  const save = async () => {
    const invalid = validateEntityDraft(draft.value)
    if (invalid) {
      message.error(invalid)
      return
    }
    saving.value = true
    try {
      draft.value.entity_key = draft.value.entity_key.trim()
      draft.value.value_type = normalizeValueType(draft.value.value_type)
      draft.value.properties = (draft.value.properties || []).map((prop) => ({
        ...prop,
        key: (prop.key || '').trim(),
        value_type: normalizeValueType(prop.value_type)
      }))
      if (draft.value.entity_id) {
        await domainEntityBuilderApi.updateEntitySchema(draft.value.entity_id, draft.value)
        message.success('实体更新成功')
      } else {
        await domainEntityBuilderApi.createEntitySchema(draft.value)
        message.success('实体创建成功')
      }
      await load({ entityKey: draft.value.entity_key }) // 保存后保持选中，同时把基线置净
    } catch (e) {
      console.error('保存失败', e)
      message.error(e?.message || '保存失败')
    } finally {
      saving.value = false
    }
  }

  const removeEntity = async (entityId) => {
    try {
      await domainEntityBuilderApi.deleteEntitySchema(entityId)
      message.success('实体已删除')
      if (selectedEntity.value?.entity_id === entityId) clearSelection()
      await load({ preserveDraft: true })
    } catch (e) {
      console.error('删除失败', e)
      message.error(e?.message || '删除失败')
    }
  }

  const cloneEntity = async (newKey, newName) => {
    if (!newKey || !newName) {
      message.error('请填写新实体键和名称')
      return false
    }
    try {
      await domainEntityBuilderApi.cloneEntity(draft.value.entity_id, newKey, newName)
      message.success('实体克隆成功')
      await load({ entityKey: newKey })
      return true
    } catch (e) {
      console.error('克隆失败', e)
      message.error(e?.message || '克隆失败')
      return false
    }
  }

  const exportConfig = async () => {
    try {
      const res = await domainEntityBuilderApi.exportConfig(DOMAIN_CODE)
      if (!res.success) return
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `domain_entity_general_${Date.now()}.json`
      link.click()
      URL.revokeObjectURL(link.href)
      message.success('配置导出成功')
    } catch (e) {
      console.error('导出失败', e)
      message.error('导出失败')
    }
  }

  const importConfig = async (configData) => {
    try {
      await domainEntityBuilderApi.importConfig(configData)
      message.success('配置导入成功')
      clearSelection()
      await load()
      return true
    } catch (e) {
      console.error('导入失败', e)
      message.error('导入失败：' + (e?.message || '文件格式错误'))
      return false
    }
  }

  return {
    taxonomy,
    schemas,
    loading,
    saving,
    error,
    selectedEntity,
    draft,
    isDirty,
    usage,
    usageLoading,
    usageError,
    loadUsage,
    fetchUsage,
    promptCoverage,
    categoryOptions,
    treeData,
    load,
    select,
    selectByKey,
    clearSelection,
    startCreate,
    resetDraft,
    save,
    removeEntity,
    cloneEntity,
    exportConfig,
    importConfig
  }
}
