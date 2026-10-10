<template>
  <div class="eia-meta-page">
    <div class="page-header">
      <div class="page-header-main">
        <button class="back-btn" aria-label="返回数据工厂总览" @click="router.push('/domain-factory/eia-data')">
          <ArrowLeft :size="18" />
        </button>
        <div>
          <h2>语料元数据标注</h2>
          <p class="page-subtitle">案例语料 31 份报告 · 自动抽取对照 · 人工标注年份与规模</p>
        </div>
      </div>
    </div>

    <MetaPanel />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@lucide/vue'
import MetaPanel from '@/components/eia-data/MetaPanel.vue'

const router = useRouter()
</script>

<style lang="less" scoped>
.eia-meta-page {
  padding: 20px 24px;
  max-width: 1440px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 16px;
}

.page-header-main {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  background: var(--main-0);
  color: var(--gray-600);
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    color: var(--main-600);
    border-color: var(--main-600);
  }
}

h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--gray-800);
}

.page-subtitle {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--gray-500);
}
</style>
