import { computed, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
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

// 按码点比较：中文名排序与后端 Python `name_cn` 排序同口径
const compareText = (a, b) => {
  const left = a || ''
  const right = b || ''
  return left < right ? -1 : left > right ? 1 : 0
}

/**
 * 泛化 prompt 覆盖测算：与后端 `_load_entity_schema_variables` 同口径——
 * 实体库扩容后预算按「实体轮转」分配：实体按分类字典 sort_order（categoryOrder 顺序）→
 * name_cn 排序，轮内属性 required 优先；第一轮每实体注入 1 条属性保证覆盖面，
 * 预算未满则第二轮各补第 2 条，依此往复，共 PROMPT_PROPERTY_LIMIT 条。
 * 未进的属性不会被泛化命中；排序靠后（分类顺序+名称）的实体要等前面的实体轮完。
 * 字典外分类（categoryOrder 里没有）排到最后，与后端 rank=1e6 一致。
 */
export const computePromptCoverage = (
  entities,
  limit = PROMPT_PROPERTY_LIMIT,
  categoryOrder = []
) => {
  const rank = new Map(categoryOrder.map((code, index) => [code, index]))
  const rankOf = (category) => (rank.has(category) ? rank.get(category) : 10 ** 6)
  const ordered = [...(entities || [])].sort(
    (a, b) => rankOf(a.category) - rankOf(b.category) || compareText(a.name_cn, b.name_cn)
  )
  const perEntity = []
  let eligible = 0
  for (const entity of ordered) {
    const props = (entity.properties || []).filter((p) => p?.key && (p.name_cn || '').trim())
    eligible += props.length
    const sorted = [...props].sort((a, b) => (b.required ? 1 : 0) - (a.required ? 1 : 0))
    perEntity.push({ entityId: entity.entity_id, refs: sorted.map((p) => `${entity.entity_key}.${p.key}`) })
  }
  const coveredRefs = new Set()
  let round = 0
  while (coveredRefs.size < limit) {
    let took = false
    for (const item of perEntity) {
      if (coveredRefs.size >= limit) break
      if (round < item.refs.length) {
        coveredRefs.add(item.refs[round])
        took = true
      }
    }
    if (!took) break
    round += 1
  }
  const byEntity = {}
  for (const item of perEntity) {
    byEntity[item.entityId] = item.refs.filter((r) => coveredRefs.has(r)).length
  }
  return { limit, covered: coveredRefs.size, eligible, coveredRefs, byEntity }
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
  // 分类字典（含停用/空分类），树序与 prompt 截断序的来源
  const categories = ref([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const selectedEntity = ref(null) // 已落库实体，取消编辑时回滚的依据
  const draft = ref(null) // 编辑中的副本
  const baselineJson = ref('')

  // 回收站：软删实体与数量（数量跟着列表响应走，抽屉内容按需加载）
  const trash = ref([])
  const trashTotal = ref(0)
  const trashLoading = ref(false)

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

  const promptCoverage = computed(() =>
    computePromptCoverage(
      schemas.value,
      PROMPT_PROPERTY_LIMIT,
      categories.value.map((item) => item.code)
    )
  )

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
    // 分类字典为准：value 是存储用 code，label 用中文名（不再把 code 暴露给用户）。
    // 停用分类不再提供新建入口，但已被实体使用的仍列出，避免编辑旧实体时选不到分类。
    const used = new Set(schemas.value.map((entity) => entity.category))
    const fromDict = categories.value
      .filter((item) => item.is_active || used.has(item.code))
      .map((item) => ({
        label: item.is_active ? item.name_cn : `${item.name_cn}（已停用）`,
        value: item.code
      }))
    if (fromDict.length) return fromDict
    // 字典未加载（后端旧版本）时回落到 taxonomy
    const options = []
    taxonomy.value?.domains?.forEach((domain) => {
      domain.categories?.forEach((category) => {
        if (category.category_name && !options.some((o) => o.value === category.category_name)) {
          options.push({
            label: category.category_label || domain.domain_name || category.category_name,
            value: category.category_name
          })
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
    const fallback = categories.value.find((item) => item.is_active)?.code
    selectedEntity.value = null
    draft.value = emptyDraft(category || fallback)
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
      const [taxRes, schemasRes, categoriesRes] = await Promise.all([
        domainEntityBuilderApi.getTaxonomy(DOMAIN_CODE),
        domainEntityBuilderApi.listEntitySchemas(null, DOMAIN_CODE),
        domainEntityBuilderApi.listCategories()
      ])
      if (taxRes.success) taxonomy.value = taxRes.data
      if (schemasRes.success) {
        schemas.value = schemasRes.data.entity_schemas || []
        trashTotal.value = schemasRes.data.trash_total || 0
      }
      if (categoriesRes.success) categories.value = categoriesRes.data || []
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

  const isVersionConflict = (e) => e?.response?.data?.detail?.code === 'ENTITY_VERSION_CONFLICT'

  /** 并发保存冲突：由人选择覆盖（force）或重新加载，绝不静默覆盖。 */
  const resolveVersionConflict = (e) =>
    new Promise((resolve) => {
      Modal.confirm({
        title: '实体已被他人保存',
        content: `${e?.message || '你的编辑基于旧版本'}。覆盖保存会用当前编辑内容顶掉对方的修改；重新加载会丢弃本次编辑。`,
        okText: '覆盖保存',
        cancelText: '重新加载',
        okButtonProps: { danger: true },
        onOk: async () => {
          await save({ force: true })
          resolve()
        },
        onCancel: async () => {
          await load({ entityKey: draft.value?.entity_key })
          resolve()
        }
      })
    })

  const save = async ({ force = false } = {}) => {
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
        await domainEntityBuilderApi.updateEntitySchema(draft.value.entity_id, {
          ...draft.value,
          // 乐观锁：带回加载时的版本，不一致时后端 409（force 表示已确认覆盖）
          expected_updated_at: draft.value.updated_at || null,
          force
        })
        message.success('实体更新成功')
      } else {
        await domainEntityBuilderApi.createEntitySchema(draft.value)
        message.success('实体创建成功')
      }
      await load({ entityKey: draft.value.entity_key }) // 保存后保持选中，同时把基线置净
    } catch (e) {
      if (isVersionConflict(e)) {
        await resolveVersionConflict(e)
        return
      }
      console.error('保存失败', e)
      message.error(e?.message || '保存失败')
    } finally {
      saving.value = false
    }
  }

  // ---- 回收站 ----
  const loadTrash = async () => {
    trashLoading.value = true
    try {
      const res = await domainEntityBuilderApi.listTrashEntities(DOMAIN_CODE)
      if (res.success) {
        trash.value = res.data.entities || []
        trashTotal.value = res.data.total ?? trash.value.length
      }
    } catch (e) {
      console.error('加载回收站失败', e)
      message.error(e?.message || '加载回收站失败')
    } finally {
      trashLoading.value = false
    }
  }

  const restoreEntity = async (entityId) => {
    try {
      await domainEntityBuilderApi.restoreEntitySchema(entityId)
      message.success('实体已恢复')
      await loadTrash()
      await load({ preserveDraft: true })
    } catch (e) {
      console.error('恢复失败', e)
      message.error(e?.message || '恢复失败')
    }
  }

  const purgeEntity = async (entityId) => {
    try {
      await domainEntityBuilderApi.purgeEntitySchema(entityId)
      message.success('实体已彻底删除')
      await loadTrash()
      await load({ preserveDraft: true })
    } catch (e) {
      console.error('彻底删除失败', e)
      message.error(e?.message || '彻底删除失败')
    }
  }

  const removeEntity = async (entityId) => {
    try {
      await domainEntityBuilderApi.deleteEntitySchema(entityId)
      message.success('实体已移入回收站，可在回收站恢复')
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

  /** 导入影响面预检：返回 {created, updated, rejected, total}，不写库 */
  const previewImport = (configData) =>
    domainEntityBuilderApi.importConfig(configData, { dryRun: true })

  const importConfig = async (configData) => {
    try {
      const res = await domainEntityBuilderApi.importConfig(configData)
      message.success(res.message || '配置导入成功')
      const rejected = res.rejected || []
      if (rejected.length) {
        message.warning(`${rejected.length} 条被拒绝：${rejected[0].reason}`)
      }
      clearSelection()
      await load()
      return true
    } catch (e) {
      console.error('导入失败', e)
      message.error('导入失败：' + (e?.message || '文件格式错误'))
      return false
    }
  }

  // ---- 分类字典操作：成功后统一 reload，树/选择器/覆盖测算同源更新 ----
  const createCategory = async (payload) => {
    try {
      await domainEntityBuilderApi.createCategory(payload)
      message.success('分类已新增')
      await load({ preserveDraft: true })
      return true
    } catch (e) {
      console.error('新增分类失败', e)
      message.error(e?.message || '新增分类失败')
      return false
    }
  }

  const updateCategory = async (code, payload) => {
    try {
      await domainEntityBuilderApi.updateCategory(code, payload)
      message.success('分类已更新')
      await load({ preserveDraft: true })
      return true
    } catch (e) {
      console.error('更新分类失败', e)
      message.error(e?.message || '更新分类失败')
      return false
    }
  }

  const deleteCategory = async (code) => {
    try {
      await domainEntityBuilderApi.deleteCategory(code)
      message.success('分类已删除')
      await load({ preserveDraft: true })
      return true
    } catch (e) {
      console.error('删除分类失败', e)
      message.error(e?.message || '删除分类失败')
      return false
    }
  }

  /** 在字典顺序里把分类上移/下移一格并整体重排（sort_order 由后端重算）。 */
  const moveCategory = async (code, direction) => {
    const codes = categories.value.map((item) => item.code)
    const index = codes.indexOf(code)
    const target = index + (direction === 'up' ? -1 : 1)
    if (index < 0 || target < 0 || target >= codes.length) return
    ;[codes[index], codes[target]] = [codes[target], codes[index]]
    try {
      await domainEntityBuilderApi.reorderCategories(codes)
      await load({ preserveDraft: true })
    } catch (e) {
      console.error('分类排序失败', e)
      message.error(e?.message || '分类排序失败')
    }
  }

  return {
    taxonomy,
    schemas,
    categories,
    loading,
    saving,
    error,
    selectedEntity,
    draft,
    isDirty,
    trash,
    trashTotal,
    trashLoading,
    loadTrash,
    restoreEntity,
    purgeEntity,
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
    previewImport,
    importConfig,
    createCategory,
    updateCategory,
    deleteCategory,
    moveCategory
  }
}
