<template>
  <div class="eia-sections-page">
    <div class="page-header">
      <div class="page-header-main">
        <button
          class="back-btn"
          aria-label="返回数据工厂总览"
          @click="router.push('/domain-factory/eia-data')"
        >
          <ArrowLeft :size="18" />
        </button>
        <div>
          <h2>
            章节口径
            <span class="title-tip" tabindex="0">
              <Info :size="14" aria-hidden="true" />
              <span class="tip-bubble">
                section_expectations（节级明细，bank_compile 产物）与 stages forms（口径字段）的双
                tab 工作台：明细页只读呈现各章节应出现的数值口径全景；字段维护页由专家增改口径字段
                （DB 裁决），admin 导出物化回写 stages/*.json 后重跑 bank_compile 生效。
              </span>
            </span>
          </h2>
          <p class="page-subtitle">节级口径全景浏览 · 口径字段人工裁决与导出物化</p>
        </div>
      </div>
    </div>

    <SectionsPanel />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft, Info } from '@lucide/vue'
import SectionsPanel from '@/components/eia-data/SectionsPanel.vue'

const router = useRouter()
</script>

<style lang="less" scoped>
.eia-sections-page {
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
  border-radius: 6px;
  border: 1px solid var(--gray-200);
  background: var(--gray-0);
  color: var(--gray-600);
  cursor: pointer;
  flex: none;

  &:hover {
    color: var(--main-600);
    border-color: var(--main-500);
  }
}

h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.title-tip {
  position: relative;
  display: inline-flex;
  color: var(--gray-400);
  cursor: help;

  .tip-bubble {
    display: none;
    position: absolute;
    top: 22px;
    left: -12px;
    z-index: 20;
    width: 380px;
    padding: 10px 12px;
    border-radius: 6px;
    background: var(--gray-800);
    color: var(--gray-100);
    font-size: 12px;
    line-height: 1.7;
    box-shadow: var(--shadow-lg, 0 8px 24px rgba(0, 0, 0, 0.16));
  }

  &:hover .tip-bubble,
  &:focus .tip-bubble {
    display: block;
  }
}

.page-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--gray-500);
}
</style>
