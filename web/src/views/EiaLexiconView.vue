<template>
  <div class="eia-lexicon-page">
    <div class="page-header">
      <div class="page-header-main">
        <button class="back-btn" aria-label="返回数据工厂总览" @click="router.push('/domain-factory/eia-data')">
          <ArrowLeft :size="18" />
        </button>
        <div>
          <h2>
            数值护栏词表
            <span class="title-tip" tabindex="0">
              <Info :size="14" aria-hidden="true" />
              <span class="tip-bubble">
                基于 31 份煤矿环评报告语料自动扫描、经人工裁决确认的「量词口径 →
                语料区间」清单；approved 口径经导出物化，挂载为写手各节的数值护栏。<br />
                写报告时的作用：写前逐项对账——语料高频量缺失标 [待确认]，防漏项臆造；现值偏离语料
                P5–P95 区间标 [待复核]，拦截量纲/进位错误；领域惯例常量直接钉死，防杜撰变体。
              </span>
            </span>
          </h2>
          <p class="page-subtitle">语料扫描候选 · 人工确认与拆分 · 导出物化为管线覆盖层</p>
        </div>
      </div>
    </div>

    <LexiconPanel />
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft, Info } from '@lucide/vue'
import LexiconPanel from '@/components/eia-data/LexiconPanel.vue'

const router = useRouter()
</script>

<style lang="less" scoped>
.eia-lexicon-page {
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

.title-tip {
  position: relative;
  display: inline-flex;
  align-items: center;
  vertical-align: 2px;
  margin-left: 6px;
  color: var(--gray-400);
  cursor: help;
  outline: none;
  transition: color 0.2s;

  &:hover,
  &:focus-visible {
    color: var(--main-600);
  }

  .tip-bubble {
    position: absolute;
    top: calc(100% + 10px);
    left: -10px;
    z-index: 20;
    display: none;
    width: 380px;
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--gray-800);
    color: #fff;
    font-size: 12px;
    font-weight: 400;
    line-height: 1.7;
    text-align: left;
    box-shadow: 0 4px 12px rgb(0 0 0 / 18%);

    &::before {
      content: '';
      position: absolute;
      top: -4px;
      left: 12px;
      width: 8px;
      height: 8px;
      background: inherit;
      transform: rotate(45deg);
    }
  }

  &:hover .tip-bubble,
  &:focus-visible .tip-bubble {
    display: block;
  }
}

.page-subtitle {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--gray-500);
}
</style>
