<script setup>
import { message } from 'ant-design-vue'
import { Copy, Download } from '@lucide/vue'

const open = defineModel('open', { type: Boolean, default: false })

const props = defineProps({
  content: { type: String, default: '' },
  filename: { type: String, default: 'entity' }
})

const handleCopyJson = async () => {
  try {
    await navigator.clipboard.writeText(props.content)
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败')
  }
}

const handleDownloadJson = () => {
  const blob = new Blob([props.content], { type: 'application/json' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${props.filename}_${Date.now()}.json`
  link.click()
  URL.revokeObjectURL(link.href)
  message.success('JSON文件下载成功')
}
</script>

<template>
  <a-modal v-model:open="open" title="实体元数据JSON" width="900px" :footer="null">
    <div class="json-viewer">
      <div class="json-actions">
        <a-space>
          <a-button type="default" @click="handleCopyJson"
            ><template #icon><Copy :size="14" /></template>复制</a-button
          >
          <a-button type="default" @click="handleDownloadJson"
            ><template #icon><Download :size="14" /></template>下载</a-button
          >
        </a-space>
      </div>
      <pre class="json-content">{{ content }}</pre>
    </div>
  </a-modal>
</template>

<style scoped lang="less">
.json-viewer {
  .json-actions {
    margin-bottom: 16px;
    display: flex;
    justify-content: flex-end;
  }
  .json-content {
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    padding: 16px;
    max-height: 600px;
    overflow: auto;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-wrap: break-word;
    color: var(--gray-1000);
  }
}
</style>
