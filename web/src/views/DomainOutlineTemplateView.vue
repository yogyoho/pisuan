<template>
  <div class="ewp domain-outline-template-view">
    <!-- 页头（EIA page-head 配方） -->
    <div class="page-head">
      <div class="ph-icon">
        <BookOpen :size="18" />
      </div>
      <div>
        <h2>大纲模板</h2>
        <div class="ph-sub">管理报告章节大纲模板，定义各章节的编写目的、内容契约和子章节结构</div>
      </div>
      <div class="ph-actions">
        <a-upload :show-upload-list="false" :before-upload="onExtractFile" accept=".docx,.pdf">
          <button class="btn btn-pri" :disabled="extracting">
            <FileSearch :size="14" /> 从报告提取大纲
          </button>
        </a-upload>
      </div>
    </div>
    <div class="outline-body">
      <OutlineTemplate ref="outlineRef" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { BookOpen, FileSearch } from '@lucide/vue'
import OutlineTemplate from '@/components/domain-factory/OutlineTemplate.vue'

const outlineRef = ref(null)
const extracting = ref(false)

const onExtractFile = async (file) => {
  extracting.value = true
  try {
    await outlineRef.value?.handleExtract(file)
  } finally {
    extracting.value = false
  }
  return false
}
</script>

<style lang="less" scoped>
/* 公共配方（page-head/btn）在 factory-core/factory-ui.less；本页只需撑满画布的双栏工作台 */
.domain-outline-template-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.outline-body {
  flex: 1;
  min-height: 0;
}
</style>

<style lang="less" src="../components/factory-core/factory-ui.less"></style>
