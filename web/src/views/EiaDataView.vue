<template>
  <div class="eia-data-page">
    <div class="page-header">
      <div class="page-header-main">
        <button class="back-btn" aria-label="返回知识工厂" @click="router.push('/domain-factory')">
          <ArrowLeft :size="18" />
        </button>
        <div>
          <h2>环评域数据工厂</h2>
          <p class="page-subtitle">coal-eia-writer 技能数据集统计总览 · 语料与护栏数据资产一览</p>
        </div>
      </div>
    </div>

    <DatasetStatsPanel />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@lucide/vue'
import DatasetStatsPanel from '@/components/eia-data/DatasetStatsPanel.vue'

const router = useRouter()
</script>

<style lang="less" scoped>
.eia-data-page {
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
