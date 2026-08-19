<template>
  <div class="domain-outline-template-view">
    <div class="page-header">
      <div>
        <div class="header-title-row">
          <a-button type="text" @click="handleBack" class="back-btn">
            <template #icon><ArrowLeftOutlined /></template>
            返回
          </a-button>
          <h2>大纲模板</h2>
        </div>
        <p class="subtitle">
          管理报告章节大纲模板，定义各章节的编写目的、内容契约和子章节结构
        </p>
      </div>
      <div class="header-actions">
        <a-upload
          :show-upload-list="false"
          :before-upload="onExtractFile"
          accept=".docx,.pdf"
        >
          <a-button type="primary" :loading="extracting">
            <template #icon><FileSearchOutlined /></template>
            从报告提取大纲
          </a-button>
        </a-upload>
      </div>
    </div>
    <OutlineTemplate ref="outlineRef" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeftOutlined, FileSearchOutlined } from '@ant-design/icons-vue'
import OutlineTemplate from '@/components/domain-factory/OutlineTemplate.vue'

const router = useRouter()
const outlineRef = ref(null)
const extracting = ref(false)

const handleBack = () => {
  router.push('/domain-factory')
}

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
.domain-outline-template-view {
  padding: 24px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--gray-50);
  overflow: hidden;

  .page-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
    background: var(--gray-0);
    padding: 20px 24px;
    border-radius: 8px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

    .header-title-row {
      display: flex;
      align-items: center;
      gap: 12px;

      .back-btn {
        display: flex;
        align-items: center;
        gap: 4px;
        color: var(--gray-600);
        padding: 4px 8px;
        height: auto;

        &:hover {
          color: var(--main-color);
          background: var(--gray-50);
        }
      }
    }

    h2 {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
      color: var(--gray-1000);
    }

    .subtitle {
      margin: 4px 0 0;
      font-size: 13px;
      color: var(--gray-600);
    }
  }
}
</style>
