<script setup>
import { watch } from 'vue'
import { Modal } from 'ant-design-vue'
import { RotateCcw, Trash2 } from '@lucide/vue'

// 回收站：软删实体列表。恢复与彻底删除都交给页面（composable 里带 reload 与提示），
// 本组件只负责展示与二次确认，避免状态在两处维护。
const props = defineProps({
  trash: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  categories: { type: Array, default: () => [] }
})
const emit = defineEmits(['restore', 'purge', 'open'])

const open = defineModel('open', { type: Boolean, default: false })

// 每次打开都重新拉取：回收站内容会随他人操作变化
watch(open, (visible) => {
  if (visible) emit('open')
})

const categoryLabel = (code) =>
  props.categories.find((item) => item.code === code)?.name_cn || code || '未分类'

const formatTime = (value) => (value ? new Date(value).toLocaleString('zh-CN') : '-')

const confirmPurge = (entity) => {
  Modal.confirm({
    title: `彻底删除「${entity.name_cn || entity.entity_key}」？`,
    content:
      '彻底删除后该实体定义（含属性与关系规则）从库中移除，无法恢复；模板与报告参数里的引用会变成悬空字符串。',
    okText: '彻底删除',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: () => emit('purge', entity.entity_id)
  })
}
</script>

<template>
  <a-drawer v-model:open="open" title="回收站" :width="520" placement="right">
    <p class="hint">
      删除的实体先进入回收站，可随时恢复到原分类；彻底删除才是不可逆操作。回收站里的实体不参与
      实体树、泛化提示词、导出与引用扫描。
    </p>
    <a-spin :spinning="loading">
      <div class="trash-list">
        <div v-for="entity in trash" :key="entity.entity_id" class="trash-row">
          <div class="meta">
            <div class="name">{{ entity.name_cn || entity.entity_key }}</div>
            <div class="sub">
              <code>{{ entity.entity_key }}</code>
              <span>· {{ categoryLabel(entity.category) }}</span>
              <span>· 删除于 {{ formatTime(entity.deleted_at) }}</span>
            </div>
          </div>
          <div class="actions">
            <button class="btn btn-sec" @click="emit('restore', entity.entity_id)">
              <RotateCcw :size="14" /> 恢复
            </button>
            <button class="btn btn-sec danger" @click="confirmPurge(entity)">
              <Trash2 :size="14" /> 彻底删除
            </button>
          </div>
        </div>
        <a-empty v-if="!trash.length && !loading" description="回收站是空的" />
      </div>
    </a-spin>
  </a-drawer>
</template>

<style scoped lang="less">
.hint {
  margin: 0 0 12px;
  color: var(--gray-600);
  font-size: 12px;
  line-height: 1.7;
}

.trash-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trash-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid var(--gray-150);
  border-radius: 6px;

  .meta {
    min-width: 0;

    .name {
      font-weight: 500;
      color: var(--gray-900);
    }

    .sub {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 2px;
      color: var(--gray-500);
      font-size: 12px;

      code {
        color: var(--gray-600);
      }
    }
  }

  .actions {
    display: flex;
    flex-shrink: 0;
    gap: 8px;

    .btn.danger:hover {
      color: var(--color-error-500);
      border-color: var(--color-error-500);
    }
  }
}
</style>
