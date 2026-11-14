<script setup>
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ArrowDown, ArrowUp, Plus, Trash2 } from '@lucide/vue'
import { domainEntityBuilderApi } from '@/apis/domain_entity_builder_api'

// 分类字典管理：改名 / 调序 / 停用 / 删除空分类 / 新增。
// 变更成功后 emit('changed')，由页面重新 load 实体树与覆盖测算。
const props = defineProps({
  categories: { type: Array, default: () => [] }
})
const emit = defineEmits(['changed'])

const open = defineModel('open', { type: Boolean, default: false })

const rows = ref([])
const newCode = ref('')
const newName = ref('')
const busy = ref(false)

// 本地行副本：输入框直接编辑，props 变化（保存成功后 reload）时整体重置
watch(
  () => props.categories,
  (list) => {
    rows.value = (list || []).map((item) => ({ ...item }))
  },
  { immediate: true, deep: true }
)

const codePattern = /^[a-z][a-z0-9_]{0,63}$/

const handleRename = async (row) => {
  const name = (row.name_cn || '').trim()
  if (!name) {
    message.error('分类名称不能为空')
    return
  }
  busy.value = true
  try {
    await domainEntityBuilderApi.updateCategory(row.code, { name_cn: name })
    message.success('分类名称已更新')
    emit('changed')
  } catch (e) {
    console.error('更新分类失败', e)
    message.error(e?.message || '更新分类失败')
  } finally {
    busy.value = false
  }
}

const handleToggleActive = async (row, checked) => {
  try {
    await domainEntityBuilderApi.updateCategory(row.code, { is_active: checked })
    message.success(checked ? '分类已启用' : '分类已停用')
    emit('changed')
  } catch (e) {
    console.error('切换分类状态失败', e)
    message.error(e?.message || '切换分类状态失败')
    row.is_active = !checked
  }
}

const handleRemove = async (row) => {
  if (row.entity_count > 0) {
    message.warning(`该分类下还有 ${row.entity_count} 个实体，先迁走或删除实体后再删分类`)
    return
  }
  busy.value = true
  try {
    await domainEntityBuilderApi.deleteCategory(row.code)
    message.success('分类已删除')
    emit('changed')
  } catch (e) {
    console.error('删除分类失败', e)
    message.error(e?.message || '删除分类失败')
  } finally {
    busy.value = false
  }
}

const handleMove = async (index, direction) => {
  const codes = rows.value.map((item) => item.code)
  const target = index + direction
  if (target < 0 || target >= codes.length) return
  ;[codes[index], codes[target]] = [codes[target], codes[index]]
  try {
    const res = await domainEntityBuilderApi.reorderCategories(codes)
    if (res.success) rows.value = res.data.map((item) => ({ ...item }))
    emit('changed')
  } catch (e) {
    console.error('分类排序失败', e)
    message.error(e?.message || '分类排序失败')
  }
}

const handleCreate = async () => {
  const code = (newCode.value || '').trim()
  const name = (newName.value || '').trim()
  if (!codePattern.test(code)) {
    message.error('分类 code 只能是小写字母开头的 snake_case（a-z0-9_，≤64 字符）')
    return
  }
  if (!name) {
    message.error('请填写分类名称')
    return
  }
  busy.value = true
  try {
    await domainEntityBuilderApi.createCategory({ code, name_cn: name })
    message.success('分类已新增')
    newCode.value = ''
    newName.value = ''
    emit('changed')
  } catch (e) {
    console.error('新增分类失败', e)
    message.error(e?.message || '新增分类失败')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <a-modal v-model:open="open" title="分类管理" :footer="null" :width="680">
    <p class="hint">
      分类顺序同时决定实体树顺序与泛化抽取提示词的属性取舍（按顺序累计前 60 个属性），
      调整顺序会直接影响哪些属性对模型可见。code 是实体的存储值，创建后不可修改。
    </p>
    <a-spin :spinning="busy">
      <div class="category-list">
        <div v-for="(row, index) in rows" :key="row.code" class="category-row">
          <div class="order-actions">
            <ArrowUp
              :size="14"
              :class="['op', { disabled: index === 0 }]"
              @click="handleMove(index, -1)"
            />
            <ArrowDown
              :size="14"
              :class="['op', { disabled: index === rows.length - 1 }]"
              @click="handleMove(index, 1)"
            />
          </div>
          <a-input
            v-model:value="row.name_cn"
            class="name-input"
            :disabled="!row.is_active"
            @blur="handleRename(row)"
            @press-enter="handleRename(row)"
          />
          <code class="category-code">{{ row.code }}</code>
          <span class="entity-count">{{ row.entity_count }} 个实体</span>
          <a-switch
            :checked="row.is_active"
            size="small"
            checked-children="启用"
            un-checked-children="停用"
            @change="(checked) => handleToggleActive(row, checked)"
          />
          <Trash2
            :size="14"
            :class="['op', 'delete', { disabled: row.entity_count > 0 }]"
            :title="row.entity_count > 0 ? '有实体的分类不能删除' : '删除分类'"
            @click="handleRemove(row)"
          />
        </div>
        <a-empty v-if="!rows.length" description="暂无分类" />
      </div>
    </a-spin>

    <div class="create-row">
      <a-input v-model:value="newCode" placeholder="code，如 pollution_source" class="code-input" />
      <a-input v-model:value="newName" placeholder="中文名称" />
      <button class="btn btn-sec" :disabled="busy" @click="handleCreate">
        <Plus :size="14" /> 新增分类
      </button>
    </div>
  </a-modal>
</template>

<style scoped lang="less">
.hint {
  margin: 0 0 12px;
  color: var(--gray-600);
  font-size: 12px;
  line-height: 1.7;
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 50vh;
  overflow-y: auto;
}

.category-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--gray-150);
  border-radius: 6px;

  .order-actions {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .op {
    color: var(--gray-500);
    cursor: pointer;
    &:hover {
      color: var(--main-color);
    }
    &.disabled {
      color: var(--gray-200);
      cursor: not-allowed;
    }
    &.delete:hover {
      color: var(--color-error-500);
    }
  }

  .name-input {
    flex: 1;
    min-width: 120px;
  }

  .category-code {
    color: var(--gray-500);
    font-size: 12px;
    white-space: nowrap;
  }

  .entity-count {
    color: var(--gray-600);
    font-size: 12px;
    white-space: nowrap;
  }
}

.create-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;

  .code-input {
    width: 220px;
  }
}
</style>
