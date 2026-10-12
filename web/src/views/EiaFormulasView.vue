<template>
  <div class="eia-formulas-page">
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
            公式参数
            <span class="title-tip" tabindex="0">
              <Info :size="14" aria-hidden="true" />
              <span class="tip-bubble">
                formulas.json（7 公式 / 23 个 user_input 参数）的参考值人工裁决：DB
                覆盖唯一真相，admin 导出物化行级写回 inputs 的 value；expr / derived_slots /
                结构恒只读。
              </span>
            </span>
          </h2>
          <p class="page-subtitle">公式参数参考值裁决 · 导出物化（expr 恒只读）</p>
        </div>
      </div>
    </div>

    <FormulasPanel />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft, Info } from '@lucide/vue'
import FormulasPanel from '@/components/eia-data/FormulasPanel.vue'

const router = useRouter()
</script>

<style lang="less" scoped>
.eia-formulas-page {
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
