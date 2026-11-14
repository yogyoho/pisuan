<script setup>
import { computed, ref, watch } from 'vue'
import { Search, Trash2 } from '@lucide/vue'

const props = defineProps({
  treeData: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  selectedKeys: { type: Array, default: () => [] }
})

const emit = defineEmits(['select', 'delete'])

const searchKeyword = ref('')
const expandedKeys = ref([])
const autoExpandParent = ref(true)

// 数据刷新后展开全部分类；用户手动的展开/收起在 handleExpand 里覆盖
watch(
  () => props.treeData,
  (nodes) => {
    if (nodes.length) expandedKeys.value = nodes.map((node) => node.key)
  },
  { immediate: true }
)

// 选中的实体可能有更深层级的父节点：确保其所在分类是展开的
watch(
  () => props.selectedKeys,
  (keys) => {
    const key = keys[0]
    if (!key?.startsWith('entity_')) return
    const parent = props.treeData.find((domain) =>
      domain.children?.some((child) => child.key === key)
    )
    if (parent && !expandedKeys.value.includes(parent.key)) {
      expandedKeys.value = [...expandedKeys.value, parent.key]
    }
  },
  { immediate: true }
)

const filteredTreeData = computed(() => {
  if (!searchKeyword.value) return props.treeData
  const keyword = searchKeyword.value.toLowerCase()
  const filter = (nodes) =>
    nodes
      .map((node) => {
        const match = (node.search_text || node.title).toLowerCase().includes(keyword)
        const filtered = node.children ? filter(node.children) : []
        if (match || filtered.length) {
          return { ...node, children: filtered.length ? filtered : node.children }
        }
        return null
      })
      .filter((node) => node !== null)
  return filter(props.treeData)
})

const handleSearch = () => {
  if (searchKeyword.value) autoExpandParent.value = true
}

// 标题命中高亮：按关键词切段，命中段用 <mark> 包起来（文本插值，不走 v-html）
const highlightParts = (text) => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  const source = text || ''
  if (!keyword || !source) return [{ text: source, hit: false }]
  const lower = source.toLowerCase()
  const parts = []
  let cursor = 0
  while (cursor < source.length) {
    const index = lower.indexOf(keyword, cursor)
    if (index < 0) {
      parts.push({ text: source.slice(cursor), hit: false })
      break
    }
    if (index > cursor) parts.push({ text: source.slice(cursor, index), hit: false })
    parts.push({ text: source.slice(index, index + keyword.length), hit: true })
    cursor = index + keyword.length
  }
  return parts
}

const handleExpand = (keys) => {
  expandedKeys.value = keys
  autoExpandParent.value = false
}

const handleSelect = (keys) => {
  emit('select', keys?.[0] || '')
}

const handleDelete = (entityId) => emit('delete', entityId)
</script>

<template>
  <div class="left-panel">
    <div class="panel-header">
      <a-input
        v-model:value="searchKeyword"
        placeholder="搜索实体..."
        allow-clear
        @change="handleSearch"
      >
        <template #prefix><Search :size="14" /></template>
      </a-input>
    </div>
    <div class="taxonomy-tree">
      <a-spin :spinning="loading">
        <a-tree
          v-if="treeData.length > 0"
          :tree-data="filteredTreeData"
          :selected-keys="selectedKeys"
          :expanded-keys="expandedKeys"
          :auto-expand-parent="autoExpandParent"
          @select="handleSelect"
          @expand="handleExpand"
        >
          <template #title="{ title, count, entity_id, isNew }">
            <div class="tree-node-row">
              <span :class="['tree-node-title', { 'is-new': isNew }]">
                <template v-for="(part, index) in highlightParts(title)" :key="index">
                  <mark v-if="part.hit">{{ part.text }}</mark>
                  <template v-else>{{ part.text }}</template>
                </template>
              </span>
              <span v-if="count != null" class="tree-node-count">({{ count }})</span>
              <a-popconfirm
                v-if="entity_id && !isNew"
                title="确定删除此实体？"
                ok-text="删除"
                cancel-text="取消"
                placement="right"
                @confirm.stop="handleDelete(entity_id)"
              >
                <Trash2 :size="12" class="tree-delete-icon" @click.stop />
              </a-popconfirm>
            </div>
          </template>
        </a-tree>
        <a-empty v-else description="暂无分类数据" />
      </a-spin>
    </div>
  </div>
</template>

<style scoped lang="less">
.left-panel {
  width: 340px;
  background: var(--gray-0);
  border-radius: 8px;
  border: 1px solid var(--gray-150);
  padding: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;

  .panel-header {
    margin-bottom: 16px;
  }
  .taxonomy-tree {
    flex: 1;
    overflow-y: auto;
    .tree-node-row {
      display: flex;
      align-items: center;
      gap: 4px;
      .tree-node-title {
        font-weight: 500;
        mark {
          padding: 0 1px;
          border-radius: 2px;
          background: var(--color-warning-100);
          color: inherit;
        }
        &.is-new {
          color: var(--main-color);
          font-style: italic;
        }
      }
      .tree-node-count {
        color: var(--gray-600);
        font-size: 12px;
      }
      .tree-delete-icon {
        color: var(--gray-400);
        margin-left: auto;
        opacity: 0;
        transition: opacity 0.2s;
        &:hover {
          color: var(--color-error-500);
        }
      }
      &:hover .tree-delete-icon {
        opacity: 1;
      }
    }
  }
}
</style>
