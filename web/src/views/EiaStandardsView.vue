<template>
  <div class="eia-standards-page">
    <div class="page-header">
      <div class="page-header-main">
        <button class="back-btn" aria-label="返回数据工厂总览" @click="router.push('/domain-factory/eia-data')">
          <ArrowLeft :size="18" />
        </button>
        <div>
          <h2>标准与限值库</h2>
          <p class="page-subtitle">标准注册表 62 条 · 人工核实编号/年份/名称 · 限值查找表只读</p>
        </div>
      </div>
    </div>

    <StandardsPanel />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@lucide/vue'
import StandardsPanel from '@/components/eia-data/StandardsPanel.vue'

const router = useRouter()
</script>

<style lang="less" scoped>
.eia-standards-page {
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
