<template>
  <a-modal
    v-model:open="visible"
    :title="`表格编辑${filename ? ' · ' + filename : ''}`"
    width="1080px"
    :mask-closable="false"
    :confirm-loading="saving"
    :ok-button-props="{ disabled: !tables.length }"
    ok-text="保存"
    cancel-text="取消"
    wrap-class-name="table-edit"
    @ok="handleSave"
    @cancel="handleClose"
  >
    <div v-if="loading" class="te-loading">
      <a-spin />
    </div>
    <div v-else-if="!tables.length" class="te-empty">该文档未找到表格</div>
    <template v-else>
      <div class="te-toolbar">
        <span class="te-toolbar-label">表格</span>
        <a-select v-model:value="currentIndex" class="te-switcher" size="small">
          <a-select-option v-for="(table, i) in tables" :key="i" :value="i">
            表格 {{ i + 1 }} / {{ tables.length }}
          </a-select-option>
        </a-select>
        <a-button v-if="isRowDirty" size="small" @click="resetCurrent">还原当前表格</a-button>
      </div>
      <div class="te-panes">
        <div class="te-pane te-preview" v-html="previewHtml"></div>
        <textarea
          v-model="currentHtml"
          class="te-pane te-editor"
          spellcheck="false"
          placeholder="<table>...</table>"
        />
      </div>
      <div class="te-hint">保存直接更新 markdown 正源；知识库检索需重新入库后生效</div>
    </template>
  </a-modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import DOMPurify from 'dompurify'
import { documentApi } from '@/apis/knowledge_api'

const props = defineProps({
  open: { type: Boolean, default: false },
  kbId: { type: String, default: '' },
  fileId: { type: String, default: '' },
  filename: { type: String, default: '' }
})

const emit = defineEmits(['update:open', 'saved'])

const TABLE_BLOCK_RE = /<table\b[^>]*>[\s\S]*?<\/table>/gi
const CONTAINER_TAGS = /^(table|thead|tbody|tfoot|tr)$/

// 单行 OCR 产物格式化为换行缩进展示（td/th 内容保持行内；不产生空行以免打断 markdown html 块）
const formatTableHtml = (html) => {
  const tokens =
    String(html || '')
      .replace(/>\s+</g, '><')
      .match(/<[^>]+>|[^<]+/g) || []
  const lines = []
  let depth = 0
  for (const token of tokens) {
    if (!token.startsWith('<')) {
      const text = token.trim()
      if (text) {
        if (lines.length) lines[lines.length - 1] += text
        else lines.push(text)
      }
      continue
    }
    const name = token.match(/^<\/?([a-zA-Z0-9]+)/)?.[1]?.toLowerCase() || ''
    if (token.startsWith('</')) {
      if (CONTAINER_TAGS.test(name)) depth = Math.max(depth - 1, 0)
      if (CONTAINER_TAGS.test(name) || !lines.length) lines.push('  '.repeat(depth) + token)
      else lines[lines.length - 1] += token
    } else {
      lines.push('  '.repeat(depth) + token)
      if (CONTAINER_TAGS.test(name) && !/\/>$/.test(token)) depth += 1
    }
  }
  return lines.join('\n')
}

const visible = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value)
})

const loading = ref(false)
const saving = ref(false)
const rawContent = ref('')
const tables = ref([]) // 原文表格块 [{ start, end, html }]
const edited = ref([]) // 各表格编辑态 html
const currentIndex = ref(0)

const currentHtml = computed({
  get: () => edited.value[currentIndex.value] ?? '',
  set: (value) => {
    edited.value[currentIndex.value] = value
  }
})

const isRowDirty = computed(
  () =>
    tables.value.length > 0 &&
    edited.value[currentIndex.value] !== tables.value[currentIndex.value].formatted
)

const dirty = computed(() => tables.value.some((table, i) => edited.value[i] !== table.formatted))

const previewHtml = computed(() =>
  DOMPurify.sanitize(currentHtml.value, {
    ADD_ATTR: ['colspan', 'rowspan', 'style', 'class']
  })
)

const loadContent = async () => {
  if (!props.kbId || !props.fileId) return
  loading.value = true
  tables.value = []
  edited.value = []
  currentIndex.value = 0
  try {
    const data = await documentApi.getDocumentContent(props.kbId, props.fileId)
    const content = data?.content || ''
    rawContent.value = content
    const matches = []
    TABLE_BLOCK_RE.lastIndex = 0
    let match
    while ((match = TABLE_BLOCK_RE.exec(content)) !== null) {
      matches.push({ start: match.index, end: match.index + match[0].length, html: match[0] })
    }
    tables.value = matches.map((table) => ({ ...table, formatted: formatTableHtml(table.html) }))
    edited.value = tables.value.map((table) => table.formatted)
  } catch (error) {
    message.error(error?.response?.data?.detail || '加载文档内容失败')
    visible.value = false
  } finally {
    loading.value = false
  }
}

const resetCurrent = () => {
  edited.value[currentIndex.value] = tables.value[currentIndex.value].html
}

const buildContent = () => {
  let out = ''
  let cursor = 0
  tables.value.forEach((table, i) => {
    // 未被编辑的表保持原文写回，避免格式化噪音进入 markdown
    const value = edited.value[i] === table.formatted ? table.html : edited.value[i]
    out += rawContent.value.slice(cursor, table.start) + value
    cursor = table.end
  })
  return out + rawContent.value.slice(cursor)
}

const handleSave = async () => {
  if (!dirty.value) {
    visible.value = false
    return
  }
  saving.value = true
  try {
    const response = await documentApi.updateDocumentContent(
      props.kbId,
      props.fileId,
      buildContent()
    )
    message.success(response?.message || 'markdown 已更新')
    emit('saved')
    visible.value = false
  } catch (error) {
    message.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const handleClose = () => {
  if (!dirty.value) return
  Modal.confirm({
    title: '有未保存的修改',
    content: '关闭将丢失当前编辑内容，确认关闭？',
    okText: '丢弃修改并关闭',
    okType: 'danger',
    cancelText: '继续编辑',
    onOk: () => {
      visible.value = false
    }
  })
}

watch(
  () => props.open,
  (open) => {
    if (open) loadContent()
  }
)
</script>

<style lang="less" scoped>
.te-loading,
.te-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--gray-500);
}

.te-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;

  .te-toolbar-label {
    font-size: 13px;
    color: var(--gray-600);
  }

  .te-switcher {
    min-width: 160px;
  }
}

.te-panes {
  display: flex;
  gap: 12px;
  height: 56vh;
}

.te-pane {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
}

.te-preview {
  overflow: auto;
  padding: 12px;
  background: var(--gray-25);

  :deep(table) {
    border-collapse: collapse;
    width: 100%;

    th,
    td {
      border: 1px solid var(--gray-300);
      padding: 4px 8px;
      font-size: 12px;
    }

    th {
      background: var(--gray-100);
      font-weight: 600;
    }
  }
}

.te-editor {
  resize: none;
  padding: 10px 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--gray-800);
  background: var(--gray-25);
  outline: none;

  &:focus {
    border-color: var(--primary-400);
  }
}

.te-hint {
  margin-top: 10px;
  font-size: 12px;
  color: var(--gray-500);
}
</style>
