<template>
  <div class="eia-expectations-page">
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
            备料清单
            <span class="title-tip" tabindex="0">
              <Info :size="14" aria-hidden="true" />
              <span class="tip-bubble">
                data_expectations 基线：13 章应备数据族与取数路径（source_hint）。
                写手按取数路径对账备料——PPS
                项目参数、知识库、附件资料等；缺失时按清单向业主/设计方索取。
              </span>
            </span>
          </h2>
          <p class="page-subtitle">分章应备数据族 · 取数路径基线（管线生成，只读）</p>
        </div>
      </div>
    </div>

    <ExpectationsPanel />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft, Info } from '@lucide/vue'
import ExpectationsPanel from '@/components/eia-data/ExpectationsPanel.vue'

const router = useRouter()
</script>

<style lang="less" scoped>
.eia-expectations-page {
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
