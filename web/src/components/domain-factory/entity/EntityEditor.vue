<script setup>
import { Copy, FileText } from '@lucide/vue'
import { VALUE_TYPE_OPTIONS } from '@/composables/useEntitySchemas'
import PropertyTable from './PropertyTable.vue'
import RelationRuleEditor from './RelationRuleEditor.vue'
import EntityUsagePanel from './EntityUsagePanel.vue'

// 实体草稿由页面持有（composable），本组件就地编辑嵌套字段
const entity = defineModel('entity', { type: Object, required: true })

defineProps({
  categoryOptions: { type: Array, default: () => [] },
  entityKeys: { type: Array, default: () => [] },
  promptCoverage: { type: Object, default: null },
  usage: { type: Object, default: null },
  usageLoading: { type: Boolean, default: false },
  usageError: { type: String, default: '' },
  saving: { type: Boolean, default: false }
})

const emit = defineEmits(['save', 'cancel', 'clone', 'view-json', 'delete'])
</script>

<template>
  <div class="schema-editor">
    <!-- 实体基本信息 -->
    <a-card title="基础元数据" class="editor-section">
      <a-form :model="entity" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="实体键 (entity_key)" required>
              <a-input
                v-model:value="entity.entity_key"
                placeholder="snake_case"
                :disabled="!!entity.entity_id"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="中文名称" required>
              <a-input v-model:value="entity.name_cn" placeholder="例如：设计生产能力" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="分类" required>
              <a-select
                v-model:value="entity.category"
                placeholder="请选择分类"
                :disabled="!!entity.entity_id"
                :options="categoryOptions"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="值类型">
              <a-select v-model:value="entity.value_type">
                <a-select-option v-for="type in VALUE_TYPE_OPTIONS" :key="type" :value="type">{{
                  type
                }}</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="单位">
              <a-input v-model:value="entity.unit" placeholder="Mt/a、万吨/年" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item>
              <a-checkbox v-model:checked="entity.is_list_type">
                列表型实体（一份报告可能有多个）
              </a-checkbox>
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="描述">
          <a-textarea
            v-model:value="entity.description"
            :rows="2"
            placeholder="描述该实体的用途和特点"
          />
        </a-form-item>

        <a-form-item label="同义词列表">
          <a-select
            v-model:value="entity.synonyms"
            mode="tags"
            placeholder="输入同义词，按回车添加"
            :token-separators="[',']"
            style="width: 100%"
          />
        </a-form-item>
      </a-form>
    </a-card>

    <PropertyTable
      v-model:properties="entity.properties"
      :entity-key="entity.entity_key"
      :prompt-coverage="promptCoverage"
      :usage="usage"
    />

    <RelationRuleEditor v-model:rules="entity.relation_rules" :entity-keys="entityKeys" />

    <EntityUsagePanel
      v-if="entity.entity_id"
      :usage="usage"
      :loading="usageLoading"
      :error="usageError"
    />

    <!-- 操作条（sticky：长属性表滚动时保存/取消始终可达） -->
    <div class="editor-actions">
      <a-space>
        <a-button type="primary" :loading="saving" @click="emit('save')">保存</a-button>
        <a-button @click="emit('cancel')">取消</a-button>
        <a-button v-if="entity.entity_id" type="default" @click="emit('clone')">
          <template #icon><Copy :size="14" /></template>
          克隆
        </a-button>
        <a-button v-if="entity.entity_id" type="default" @click="emit('view-json')">
          <template #icon><FileText :size="14" /></template>
          查看JSON
        </a-button>
        <a-button v-if="entity.entity_id" type="primary" danger @click="emit('delete')">
          删除
        </a-button>
      </a-space>
    </div>
  </div>
</template>

<style scoped lang="less">
.schema-editor {
  .editor-section {
    margin-bottom: 24px;
  }
  .editor-actions {
    position: sticky;
    bottom: 0;
    margin-top: 24px;
    padding: 16px 0;
    border-top: 1px solid var(--gray-200);
    background: var(--gray-0);
  }
}
</style>
