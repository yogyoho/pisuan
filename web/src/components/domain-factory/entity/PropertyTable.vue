<script setup>
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Info, Plus } from '@lucide/vue'

// 属性数组由父级实体草稿持有：本组件只做增删改，不重新赋值整个数组
const properties = defineModel('properties', { type: Array, default: () => [] })

const props = defineProps({
  entityKey: { type: String, default: '' },
  // 泛化 prompt 覆盖测算（composable 的 promptCoverage）
  promptCoverage: { type: Object, default: null }
})

const PROPERTY_VALUE_TYPES = ['String', 'Integer', 'Float', 'Boolean', 'Enum']

const propertyColumns = [
  { title: '属性键', dataIndex: 'key', key: 'key' },
  { title: '中文名称', dataIndex: 'name_cn', key: 'name_cn' },
  { title: '类型', dataIndex: 'value_type', key: 'value_type' },
  { title: '单位', dataIndex: 'unit', key: 'unit' },
  { title: '必填', dataIndex: 'required', key: 'required' },
  { title: '枚举选项', dataIndex: 'enum_options', key: 'enum_options' },
  { title: '提取提示词', dataIndex: 'extraction_hint', key: 'extraction_hint' },
  { title: '泛化 prompt', key: 'prompt', width: 110 },
  { title: '操作', key: 'actions', width: 120 }
]

const isPromptCovered = (record) =>
  Boolean(props.promptCoverage?.coveredRefs?.has(`${props.entityKey}.${record.key}`))

const ownCoveredCount = computed(
  () => properties.value.filter((prop) => isPromptCovered(prop)).length
)

const ownEligibleCount = computed(
  () => properties.value.filter((prop) => prop?.key && (prop.name_cn || '').trim()).length
)

const propertyModalVisible = ref(false)
const editingPropertyIndex = ref(-1)
const editingProperty = ref(emptyProperty())

function emptyProperty() {
  return {
    key: '',
    name_cn: '',
    value_type: 'String',
    unit: '',
    required: false,
    enum_options: [],
    min_value: null,
    max_value: null,
    description: '',
    extraction_hint: ''
  }
}

const handleAddProperty = () => {
  editingPropertyIndex.value = -1
  editingProperty.value = emptyProperty()
  propertyModalVisible.value = true
}

const handleEditProperty = (index) => {
  editingPropertyIndex.value = index
  editingProperty.value = JSON.parse(JSON.stringify(properties.value[index]))
  editingProperty.value.enum_options = editingProperty.value.enum_options || []
  propertyModalVisible.value = true
}

const handleDeleteProperty = (index) => {
  properties.value.splice(index, 1)
}

const handleSaveProperty = () => {
  try {
    if (!editingProperty.value.key || !editingProperty.value.name_cn) {
      message.error('请填写属性键和中文名称')
      return
    }
    if (
      editingProperty.value.value_type === 'Enum' &&
      !editingProperty.value.enum_options?.length
    ) {
      message.error('枚举类型必须提供枚举选项')
      return
    }
    const data = {
      key: editingProperty.value.key,
      name_cn: editingProperty.value.name_cn,
      value_type: editingProperty.value.value_type,
      unit: editingProperty.value.unit || null,
      required: editingProperty.value.required,
      enum_options: editingProperty.value.enum_options || null,
      min_value: editingProperty.value.min_value || null,
      max_value: editingProperty.value.max_value || null,
      description: editingProperty.value.description || '',
      extraction_hint: editingProperty.value.extraction_hint || ''
    }
    if (editingPropertyIndex.value >= 0) {
      properties.value[editingPropertyIndex.value] = data
    } else {
      properties.value.push(data)
    }
    propertyModalVisible.value = false
    message.success('属性保存成功')
  } catch (e) {
    console.error('保存属性失败', e)
    message.error('保存属性失败')
  }
}
</script>

<template>
  <a-card title="属性结构定义" class="editor-section">
    <div v-if="promptCoverage" class="prompt-coverage-hint">
      <Info :size="13" />
      <span>
        泛化抽取只会把排序后前 {{ promptCoverage.limit }} 个属性写进提示词（通用域共
        {{ promptCoverage.eligible }} 个候选，已覆盖 {{ promptCoverage.covered }} 个）；本实体
        {{ ownCoveredCount }}/{{ ownEligibleCount }}
        进 prompt。未进的属性不会被泛化命中，改写进提示词靠前实体的属性或精简候选。
      </span>
    </div>
    <a-table :columns="propertyColumns" :data-source="properties" :pagination="false" size="small">
      <template #bodyCell="{ column, record, index }">
        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button type="link" size="small" @click="handleEditProperty(index)">编辑</a-button>
            <a-popconfirm title="删除此属性？" @confirm="handleDeleteProperty(index)">
              <a-button type="link" size="small" danger>删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
        <template v-else-if="column.key === 'value_type'">{{ record.value_type }}</template>
        <template v-else-if="column.key === 'required'">
          <a-tag :color="record.required ? 'red' : 'default'">{{
            record.required ? '必填' : '可选'
          }}</a-tag>
        </template>
        <template v-else-if="column.key === 'enum_options'">
          <span v-if="record.enum_options && record.enum_options.length">{{
            record.enum_options.join(', ')
          }}</span>
          <span v-else>-</span>
        </template>
        <template v-else-if="column.key === 'extraction_hint'">
          <a-tooltip v-if="record.extraction_hint" :title="record.extraction_hint">
            <span class="hint-cell">{{ record.extraction_hint }}</span>
          </a-tooltip>
          <span v-else class="muted">-</span>
        </template>
        <template v-else-if="column.key === 'prompt'">
          <a-tooltip
            :title="
              isPromptCovered(record)
                ? '按分类+名称排序后位于前 60 个属性内，会进入泛化抽取提示词'
                : '排序后在第 60 个之外，泛化抽取看不到该属性'
            "
          >
            <a-tag :color="isPromptCovered(record) ? 'blue' : 'default'">{{
              isPromptCovered(record) ? '进 prompt' : '未进'
            }}</a-tag>
          </a-tooltip>
        </template>
      </template>
    </a-table>
    <a-button type="dashed" block style="margin-top: 16px" @click="handleAddProperty">
      <template #icon><Plus :size="14" /></template>
      添加属性
    </a-button>

    <a-modal
      v-model:open="propertyModalVisible"
      title="属性定义"
      width="700px"
      @ok="handleSaveProperty"
    >
      <a-form :model="editingProperty" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="属性键" required>
              <a-input v-model:value="editingProperty.key" placeholder="例如：name" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="中文名称" required>
              <a-input v-model:value="editingProperty.name_cn" placeholder="例如：村庄名称" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="数据类型" required>
              <a-select v-model:value="editingProperty.value_type">
                <a-select-option v-for="type in PROPERTY_VALUE_TYPES" :key="type" :value="type">{{
                  type
                }}</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="单位">
              <a-input v-model:value="editingProperty.unit" placeholder="例如：m、人" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item>
          <a-checkbox v-model:checked="editingProperty.required">必填</a-checkbox>
        </a-form-item>
        <a-form-item v-if="editingProperty.value_type === 'Enum'" label="枚举选项" required>
          <a-select
            v-model:value="editingProperty.enum_options"
            mode="tags"
            placeholder="输入枚举选项，按回车添加"
            :token-separators="[',']"
            style="width: 100%"
          />
        </a-form-item>
        <a-row
          :gutter="16"
          v-if="editingProperty.value_type === 'Integer' || editingProperty.value_type === 'Float'"
        >
          <a-col :span="12">
            <a-form-item label="最小值">
              <a-input-number
                v-model:value="editingProperty.min_value"
                style="width: 100%"
                :precision="editingProperty.value_type === 'Float' ? 2 : 0"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="最大值">
              <a-input-number
                v-model:value="editingProperty.max_value"
                style="width: 100%"
                :precision="editingProperty.value_type === 'Float' ? 2 : 0"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-textarea
            v-model:value="editingProperty.description"
            :rows="2"
            placeholder="属性描述"
          />
        </a-form-item>
        <a-form-item label="提取提示词">
          <a-textarea
            v-model:value="editingProperty.extraction_hint"
            :rows="2"
            placeholder="用于指导LLM提取的提示词"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<style scoped lang="less">
.prompt-coverage-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--gray-50);
  color: var(--gray-600);
  font-size: 12px;
  line-height: 1.7;
}

.hint-cell {
  display: inline-block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  color: var(--gray-600);
}

.muted {
  color: var(--gray-400);
}
</style>
