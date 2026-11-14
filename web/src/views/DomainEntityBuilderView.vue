<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { Bot, Box, Download, FileText, Inbox, Layers, Plus, Trash2, Upload } from '@lucide/vue'
import { useEntitySchemas } from '@/composables/useEntitySchemas'
import CategoryManager from '@/components/domain-factory/entity/CategoryManager.vue'
import EntityEditor from '@/components/domain-factory/entity/EntityEditor.vue'
import EntityExtractWizard from '@/components/domain-factory/entity/EntityExtractWizard.vue'
import EntityJsonModal from '@/components/domain-factory/entity/EntityJsonModal.vue'
import EntityTrashDrawer from '@/components/domain-factory/entity/EntityTrashDrawer.vue'
import EntityTree from '@/components/domain-factory/entity/EntityTree.vue'

const route = useRoute()
const router = useRouter()
const {
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
  fetchUsage,
  cloneEntity,
  exportConfig,
  previewImport,
  importConfig
} = useEntitySchemas()

const selectedKeys = computed(() =>
  selectedEntity.value ? [`entity_${selectedEntity.value.entity_id}`] : []
)
const entityKeys = computed(() => schemas.value.map((item) => item.entity_key).filter(Boolean))

const importModalVisible = ref(false)
const importFileList = ref([])
const jsonModalVisible = ref(false)
const jsonContent = ref('')
const cloneModalVisible = ref(false)
const cloneNewKey = ref('')
const cloneNewName = ref('')
const extractVisible = ref(false)
const categoryManagerVisible = ref(false)
const trashDrawerVisible = ref(false)
const pendingEntityKey = ref(null)

// ---- 脏状态守卫：切换实体/新建/克隆/导入/离开页面统一先确认 ----
const confirmDiscard = () =>
  new Promise((resolve) => {
    if (!isDirty.value) return resolve(true)
    Modal.confirm({
      title: '有未保存的修改',
      content: '继续操作将丢失当前编辑内容，确定放弃吗？',
      okText: '放弃修改',
      cancelText: '继续编辑',
      okButtonProps: { danger: true },
      onOk: () => resolve(true),
      onCancel: () => resolve(false)
    })
  })

const handleBeforeUnload = (event) => {
  if (!isDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => (isDirty.value ? confirmDiscard() : true))

// ---- 树与选择 ----
const handleTreeSelect = async (key) => {
  if (!key || key === selectedKeys.value[0]) return
  if (!(await confirmDiscard())) return
  if (key.startsWith('new_')) {
    handleCreateEntity(key.slice('new_'.length))
    return
  }
  if (key.startsWith('entity_')) {
    const entity = schemas.value.find((item) => item.entity_id === key.slice('entity_'.length))
    if (entity) select(entity)
    return
  }
  clearSelection()
}

const handleCreateEntity = (domainId = null) => {
  const domain = domainId
    ? taxonomy.value?.domains?.find((item) => item.domain_id === domainId)
    : null
  startCreate(domain?.categories?.[0]?.category_name)
}

const handleTreeDelete = (entityId) => {
  const entity = schemas.value.find((item) => item.entity_id === entityId)
  if (entity) void confirmDelete(entity)
}

// ---- 编辑器操作 ----
const handleCancel = () => resetDraft()

const DELETE_IMPACT_LABELS = [
  ['templates', '段落模板'],
  ['pending_tasks', '待审核任务'],
  ['report_pps', '报告参数'],
  ['facts', '区域事实']
]

/** 删除前先取引用影响面：取不到就不删，避免在引用关系未知时误删。 */
const confirmDelete = async (entity) => {
  if (!entity?.entity_id) return
  let entityUsage
  try {
    entityUsage = await fetchUsage(entity.entity_id)
  } catch (e) {
    console.error('获取引用影响面失败', e)
    message.error(e?.message || '获取引用影响面失败，已取消删除')
    return
  }
  const totals = entityUsage?.totals || {}
  const hits = DELETE_IMPACT_LABELS.filter(([key]) => totals[key]).map(
    ([key, label]) => `${label} ${totals[key]}`
  )
  Modal.confirm({
    title: `删除实体「${entity.name_cn || entity.entity_key}」？`,
    content: hits.length
      ? `当前被引用：${hits.join('、')}。移入回收站后这些引用会变成悬空字符串，存量模板与待审核任务无法再定位该实体；需要时可在「回收站」恢复。`
      : '该实体当前没有任何引用。删除后进入「回收站」，可随时恢复。',
    okText: '移入回收站',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: () => removeEntity(entity.entity_id)
  })
}

const handleDelete = () => void confirmDelete(draft.value)

const handleClone = async () => {
  if (!(await confirmDiscard())) return
  cloneNewKey.value = draft.value.entity_key + '_copy'
  cloneNewName.value = draft.value.name_cn + '（副本）'
  cloneModalVisible.value = true
}

const handleConfirmClone = async () => {
  if (await cloneEntity(cloneNewKey.value, cloneNewName.value)) cloneModalVisible.value = false
}

const handleViewJson = () => {
  if (!draft.value) {
    message.warning('请先选择一个实体')
    return
  }
  jsonContent.value = JSON.stringify(draft.value, null, 2)
  jsonModalVisible.value = true
}

// ---- 导入 / 导出 ----
const handleImport = async () => {
  if (!(await confirmDiscard())) return
  importFileList.value = []
  importModalVisible.value = true
}

const handleBeforeUpload = () => false

const IMPORT_REJECT_PREVIEW = 5

const describeRejects = (rejected) =>
  rejected
    .slice(0, IMPORT_REJECT_PREVIEW)
    .map(
      (item) => `${item.entity_key || item.name_cn || `第 ${item.index + 1} 条`}：${item.reason}`
    )
    .join('；')

/** 先预检再确认：导入会覆盖同名实体定义，不先给出影响面不写库。 */
const handleConfirmImport = async () => {
  if (!importFileList.value.length) {
    message.error('请选择文件')
    return
  }
  const text = await importFileList.value[0].originFileObj.text()
  let configData
  try {
    configData = JSON.parse(text)
  } catch (e) {
    console.error('导入失败', e)
    message.error('导入失败：文件格式错误')
    return
  }

  let preview
  try {
    preview = await previewImport(configData)
  } catch (e) {
    console.error('导入预检失败', e)
    message.error('导入预检失败：' + (e?.message || '文件内容不符合配置格式'))
    return
  }

  const { created = 0, updated = 0, rejected = [] } = preview || {}
  const rejectText = rejected.length
    ? `拒绝 ${rejected.length} 条：${describeRejects(rejected)}${rejected.length > IMPORT_REJECT_PREVIEW ? ' 等' : ''}。`
    : ''
  if (!created && !updated) {
    message.error(`没有可导入的实体。${rejectText}`)
    return
  }

  Modal.confirm({
    title: '确认导入实体配置？',
    content:
      `新增 ${created} 个实体，更新 ${updated} 个实体。${rejectText}` +
      '更新按 entity_key 对齐，会用文件内容覆盖同名实体的定义，并重映射待审核任务；' +
      '段落模板与报告参数里的旧属性引用会变成悬空字符串。分类字典独立管理，导入不消费文件里的 taxonomy。',
    okText: '导入',
    cancelText: '取消',
    onOk: async () => {
      if (await importConfig(configData)) importModalVisible.value = false
    }
  })
}

const handleExtractImported = () => load({ preserveDraft: true })

// ---- 深链：?entity_key=xxx ----
onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  pendingEntityKey.value = route.query.entity_key || null
  await load()
  if (pendingEntityKey.value && selectByKey(pendingEntityKey.value)) pendingEntityKey.value = null
})

onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))

watch(
  () => route.query.entity_key,
  async (key) => {
    if (!key || key === draft.value?.entity_key) return
    if (!(await confirmDiscard())) {
      if (draft.value?.entity_key) {
        router.replace({ query: { ...route.query, entity_key: draft.value.entity_key } })
      }
      return
    }
    if (schemas.value.length) selectByKey(key)
    else pendingEntityKey.value = key
  }
)
</script>

<template>
  <div class="ewp domain-entity-builder-view">
    <!-- 页头（EIA page-head 配方）：唯一主操作「新建实体」，其余降级次/文本钮 -->
    <div class="page-head">
      <div class="ph-icon">
        <Box :size="18" />
      </div>
      <div>
        <h2>领域实体构建器</h2>
        <div class="ph-sub">管理通用域层级分类体系和实体 Schema 定义，统一实体归属与提取口径</div>
      </div>
      <div class="ph-actions">
        <button class="btn btn-sec" @click="categoryManagerVisible = true">
          <Layers :size="14" /> 分类管理
        </button>
        <button
          class="btn btn-sec"
          :title="trashTotal ? `回收站里有 ${trashTotal} 个实体` : '回收站是空的'"
          @click="trashDrawerVisible = true"
        >
          <Trash2 :size="14" /> 回收站{{ trashTotal ? ` (${trashTotal})` : '' }}
        </button>
        <button class="btn btn-sec" @click="exportConfig"><Download :size="14" /> 导出</button>
        <button class="btn btn-sec" @click="handleImport"><Upload :size="14" /> 导入</button>
        <button class="btn btn-sec" @click="extractVisible = true">
          <Bot :size="14" /> AI 提取
        </button>
        <button class="btn btn-pri" @click="handleCreateEntity">
          <Plus :size="14" /> 新建实体
        </button>
      </div>
    </div>

    <a-alert
      v-if="error"
      type="error"
      show-icon
      class="alert"
      :message="error"
      closable
      @close="error = ''"
    />

    <div class="main-content">
      <EntityTree
        :tree-data="treeData"
        :loading="loading"
        :selected-keys="selectedKeys"
        @select="handleTreeSelect"
        @delete="handleTreeDelete"
      />

      <div class="right-panel">
        <div v-if="!draft" class="empty-state">
          <a-empty description="请从左侧选择实体开始编辑" />
          <div class="empty-actions">
            <button class="btn btn-pri" @click="handleCreateEntity">
              <Plus :size="14" /> 新建实体
            </button>
            <button class="btn btn-sec" @click="extractVisible = true">
              <Bot :size="14" /> 从文档提取实体
            </button>
            <button class="btn btn-sec" @click="router.push({ name: 'GeneralWorkbench' })">
              <FileText :size="14" /> 从报告学习
            </button>
          </div>
          <p class="empty-note">
            从报告学习：在知识工作台打开已解析报告，由模型提出实体与属性 schema
            提案，再回到本页采纳。
          </p>
        </div>
        <EntityEditor
          v-else
          v-model:entity="draft"
          :category-options="categoryOptions"
          :entity-keys="entityKeys"
          :prompt-coverage="promptCoverage"
          :usage="usage"
          :usage-loading="usageLoading"
          :usage-error="usageError"
          :saving="saving"
          @save="save"
          @cancel="handleCancel"
          @clone="handleClone"
          @view-json="handleViewJson"
          @delete="handleDelete"
        />
      </div>
    </div>

    <!-- 导入配置弹窗 -->
    <a-modal v-model:open="importModalVisible" title="导入配置" @ok="handleConfirmImport">
      <a-upload-dragger
        v-model:fileList="importFileList"
        :before-upload="handleBeforeUpload"
        accept=".json"
        :max-count="1"
      >
        <p class="ant-upload-drag-icon"><Inbox :size="48" /></p>
        <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p class="ant-upload-hint">
          支持 JSON 格式配置文件（导出的文件可直接回导；分类字典独立管理，文件里的 taxonomy
          不参与导入）
        </p>
      </a-upload-dragger>
    </a-modal>

    <!-- 克隆弹窗 -->
    <a-modal v-model:open="cloneModalVisible" title="克隆实体" @ok="handleConfirmClone">
      <a-form layout="vertical">
        <a-form-item label="新实体键 (entity_key)" required>
          <a-input v-model:value="cloneNewKey" placeholder="例如：sensitive_villages_v2" />
        </a-form-item>
        <a-form-item label="新中文名称" required>
          <a-input v-model:value="cloneNewName" placeholder="例如：敏感目标村庄（V2）" />
        </a-form-item>
      </a-form>
    </a-modal>

    <EntityJsonModal
      v-model:open="jsonModalVisible"
      :content="jsonContent"
      :filename="draft?.entity_key || 'entity'"
    />
    <EntityExtractWizard v-model:open="extractVisible" @imported="handleExtractImported" />
    <CategoryManager
      v-model:open="categoryManagerVisible"
      :categories="categories"
      @changed="load({ preserveDraft: true })"
    />
    <EntityTrashDrawer
      v-model:open="trashDrawerVisible"
      :trash="trash"
      :loading="trashLoading"
      :categories="categories"
      @open="loadTrash"
      @restore="restoreEntity"
      @purge="purgeEntity"
    />
  </div>
</template>

<style scoped lang="less">
.domain-entity-builder-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.alert {
  margin-bottom: 16px;
}

.main-content {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 12px;
  margin-top: 12px;
}

.right-panel {
  flex: 1;
  background: var(--gray-0);
  border-radius: 8px;
  border: 1px solid var(--gray-150);
  padding: 24px;
  overflow-y: auto;

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    height: 100%;

    .empty-actions {
      display: flex;
      gap: 8px;
    }

    .empty-note {
      max-width: 420px;
      margin: 0;
      color: var(--gray-500);
      font-size: 12px;
      line-height: 1.7;
      text-align: center;
    }
  }
}
</style>
