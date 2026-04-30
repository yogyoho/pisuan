<script setup>
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, EditOutlined, SaveOutlined } from '@ant-design/icons-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

const props = defineProps({
  domains: { type: Array, default: () => [] },
  selectedDomain: { type: String, default: '' }
})

const emit = defineEmits(['update:domain'])

const schemaLoading = ref(false)
const variableList = ref([])
const chapterTree = ref([])
const saving = ref(false)
const hasChanges = ref(false)

const domainOptions = computed(() => {
  if (!Array.isArray(props.domains)) return []
  return props.domains.map(d => ({
    label: d.name,
    value: d.code || d.id || d.name
  }))
})

const dataTypes = [
  { label: 'String', value: 'string' },
  { label: 'Float', value: 'float' },
  { label: 'Integer', value: 'integer' },
  { label: 'Boolean', value: 'boolean' },
  { label: 'Date', value: 'date' }
]

const widgetTypes = [
  { label: 'Input', value: 'Input' },
  { label: 'InputNumber', value: 'InputNumber' },
  { label: 'Textarea', value: 'Textarea' },
  { label: 'Select', value: 'Select' },
  { label: 'DatePicker', value: 'DatePicker' }
]

const groupOptions = [
  { label: '基础信息', value: '基础信息' },
  { label: '工程参数', value: '工程参数' },
  { label: '空间数据', value: '空间数据' },
  { label: '监测数据', value: '监测数据' },
  { label: '环境现状', value: '环境现状' },
  { label: '其他', value: '其他' }
]

const defaultVariable = () => ({
  key: '',
  label: '',
  data_type: 'string',
  widget: 'Input',
  unit: '',
  group: '基础信息',
  required: false,
  prompt: '',
  source: '',
  sample: ''
})

const editingVariable = ref(null)
const showVariableModal = ref(false)

const fetchSchema = async () => {
  const domainId = props.selectedDomain
  if (!domainId || domainId === '__all__') {
    variableList.value = []
    chapterTree.value = []
    return
  }
  schemaLoading.value = true
  try {
    const res = await domainFactoryApi.fetchSchemas(domainId)
    variableList.value = res?.variables || []
    chapterTree.value = res?.chapters || []
  } catch (e) {
    console.error('Failed to fetch schema:', e)
    message.error('加载 Schema 失败')
  } finally {
    schemaLoading.value = false
  }
}

const handleSave = async () => {
  if (!props.selectedDomain || props.selectedDomain === '__all__') {
    message.warning('请先选择一个领域')
    return
  }
  saving.value = true
  try {
    await domainFactoryApi.saveSchema(props.selectedDomain, {
      variables: variableList.value,
      chapters: chapterTree.value
    })
    message.success('保存成功')
    hasChanges.value = false
  } catch (e) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

const openVariableModal = (variable = null) => {
  editingVariable.value = variable ? { ...variable } : defaultVariable()
  showVariableModal.value = true
}

const saveVariable = () => {
  if (!editingVariable.value.label) {
    message.warning('请输入字段标签')
    return
  }
  const key = editingVariable.value.key || editingVariable.value.label.replace(/\s+/g, '_')
  const variable = { ...editingVariable.value, key }
  if (editingVariable.value._isNew) {
    variableList.value.push(variable)
  } else {
    const idx = variableList.value.findIndex(v => v.key === editingVariable.value.key)
    if (idx >= 0) variableList.value[idx] = variable
  }
  showVariableModal.value = false
  hasChanges.value = true
}

const deleteVariable = (key) => {
  variableList.value = variableList.value.filter(v => v.key !== key)
  hasChanges.value = true
}

const addChapter = () => {
  const num = chapterTree.value.length + 1
  chapterTree.value.push({
    key: `ch${num}`,
    title: `${num}. 新章节`
  })
  hasChanges.value = true
}

const deleteChapter = (key) => {
  chapterTree.value = chapterTree.value.filter(c => c.key !== key)
  hasChanges.value = true
}

const updateChapterTitle = (item, newTitle) => {
  item.title = newTitle
  hasChanges.value = true
}

watch(() => props.selectedDomain, () => {
  hasChanges.value = false
  fetchSchema()
}, { immediate: true })

watch([variableList, chapterTree], () => {
}, { deep: true })
</script>

<template>
  <div class="schema-configurator">
    <!-- Header -->
    <div class="config-header">
      <div class="header-left">
        <span class="label">领域</span>
        <a-select
          :model-value="selectedDomain"
          :options="domainOptions"
          placeholder="选择一个领域"
          style="width: 200px"
          @change="val => emit('update:domain', val)"
        />
        <span v-if="selectedDomain && selectedDomain !== '__all__'" class="domain-tip">
          {{ domainOptions.find(o => o.value === selectedDomain)?.label }}
        </span>
      </div>
      <div class="header-right">
        <a-button v-if="hasChanges" type="link" @click="fetchSchema">放弃更改</a-button>
        <a-button
          type="primary"
          :loading="saving"
          :disabled="!selectedDomain || selectedDomain === '__all__'"
          @click="handleSave"
        >
          <SaveOutlined /> 保存配置
        </a-button>
      </div>
    </div>

    <a-spin :spinning="schemaLoading">
      <div v-if="!selectedDomain || selectedDomain === '__all__'" class="empty-tip">
        请先选择一个领域以配置 Schema
      </div>
      <div v-else class="config-layout">
        <!-- Variables Section -->
        <div class="config-section">
          <div class="section-header">
            <h3>变量字典</h3>
            <a-button size="small" @click="openVariableModal()">
              <PlusOutlined /> 添加字段
            </a-button>
          </div>
          <div class="section-desc">
            定义 ETL 提取表单字段，支持按组分类（基础信息、工程参数、空间数据等）
          </div>
          <div class="variable-table">
            <div v-if="!variableList.length" class="no-data">暂无字段，请添加</div>
            <div v-else class="variable-list">
              <div v-for="v in variableList" :key="v.key" class="variable-row">
                <div class="var-main">
                  <span class="var-label">{{ v.label }}</span>
                  <span class="var-key">{{ v.key }}</span>
                </div>
                <div class="var-meta">
                  <a-tag>{{ v.group || '基础信息' }}</a-tag>
                  <a-tag>{{ v.data_type }}</a-tag>
                  <a-tag v-if="v.unit">{{ v.unit }}</a-tag>
                </div>
                <div class="var-actions">
                  <a-button size="small" type="text" @click="openVariableModal(v)">
                    <EditOutlined />
                  </a-button>
                  <a-button size="small" type="text" danger @click="deleteVariable(v.key)">
                    <DeleteOutlined />
                  </a-button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Chapters Section -->
        <div class="config-section">
          <div class="section-header">
            <h3>报告章节结构</h3>
            <a-button size="small" @click="addChapter">
              <PlusOutlined /> 添加章节
            </a-button>
          </div>
          <div class="section-desc">
            定义该领域报告的章节结构，用于解析后关联到具体章节
          </div>
          <div class="chapter-tree">
            <div v-if="!chapterTree.length" class="no-data">暂无章节定义</div>
            <div v-else class="chapter-list">
              <div v-for="ch in chapterTree" :key="ch.key" class="chapter-item">
                <span class="chapter-num">{{ ch.key }}</span>
                <a-input
                  :value="ch.title"
                  class="chapter-title-input"
                  @change="e => updateChapterTitle(ch, e.target.value)"
                />
                <a-button size="small" type="text" danger @click="deleteChapter(ch.key)">
                  <DeleteOutlined />
                </a-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </a-spin>

    <!-- Variable Edit Modal -->
    <a-modal
      v-model:open="showVariableModal"
      :title="editingVariable?._isNew ? '添加字段' : '编辑字段'"
      @ok="saveVariable"
      ok-text="保存"
      width="500px"
    >
      <div class="variable-form" v-if="editingVariable">
        <div class="form-row">
          <div class="form-item">
            <label>字段标签 *</label>
            <a-input v-model:value="editingVariable.label" placeholder="如：项目名称" />
          </div>
          <div class="form-item">
            <label>字段 Key</label>
            <a-input v-model:value="editingVariable.key" placeholder="自动生成" disabled />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item">
            <label>数据类型</label>
            <a-select v-model:value="editingVariable.data_type" :options="dataTypes" style="width: 100%" />
          </div>
          <div class="form-item">
            <label>控件类型</label>
            <a-select v-model:value="editingVariable.widget" :options="widgetTypes" style="width: 100%" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item">
            <label>分组</label>
            <a-select v-model:value="editingVariable.group" :options="groupOptions" style="width: 100%" />
          </div>
          <div class="form-item">
            <label>单位</label>
            <a-input v-model:value="editingVariable.unit" placeholder="如：Mt/a, km²" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item full">
            <label>提取 Prompt</label>
            <a-input v-model:value="editingVariable.prompt" placeholder="AI 提取时的提示词" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item full">
            <label>必填</label>
            <a-switch v-model:checked="editingVariable.required" />
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style lang="less" scoped>
.schema-configurator {
  padding: 0;
}

.config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;

  .label {
    font-weight: 500;
    margin-right: 8px;
    font-size: 13px;
  }

  .domain-tip {
    margin-left: 8px;
    font-size: 12px;
    color: var(--gray-500, #999);
  }
}

.header-left {
  display: flex;
  align-items: center;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-tip {
  text-align: center;
  color: var(--gray-500, #999);
  padding: 60px 0;
  font-size: 14px;
}

.config-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.config-section {
  background: var(--color-bg-container, #fff);
  border: 1px solid var(--gray-150, #e8e8e8);
  border-radius: 12px;
  padding: 20px;

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;

    h3 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
    }
  }

  .section-desc {
    font-size: 12px;
    color: var(--gray-500, #999);
    margin-bottom: 16px;
  }
}

.variable-table {
  max-height: 400px;
  overflow-y: auto;
}

.no-data {
  text-align: center;
  color: var(--gray-400, #bbb);
  padding: 24px 0;
  font-size: 13px;
}

.variable-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.variable-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--gray-50, #fafafa);
  border-radius: 8px;
  border: 1px solid var(--gray-100, #f0f0f0);
  transition: border-color 0.2s;

  &:hover {
    border-color: var(--main-200, #1677ff);
  }

  .var-main {
    flex: 1;
    min-width: 0;
  }

  .var-label {
    font-size: 13px;
    font-weight: 500;
    display: block;
  }

  .var-key {
    font-size: 11px;
    color: var(--gray-400, #999);
    font-family: monospace;
  }

  .var-meta {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }

  .var-actions {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
  }
}

.chapter-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chapter-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--gray-50, #fafafa);
  border-radius: 8px;
  border: 1px solid var(--gray-100, #f0f0f0);

  .chapter-num {
    font-size: 12px;
    font-weight: 600;
    color: var(--main-color, #1677ff);
    width: 40px;
    flex-shrink: 0;
  }

  .chapter-title-input {
    flex: 1;
  }
}

.variable-form {
  .form-row {
    display: flex;
    gap: 12px;
    margin-bottom: 14px;

    .form-item {
      flex: 1;

      &.full {
        flex: none;
        width: 100%;
      }

      label {
        display: block;
        font-size: 12px;
        color: var(--gray-600, #555);
        margin-bottom: 6px;
        font-weight: 500;
      }
    }
  }
}
</style>
