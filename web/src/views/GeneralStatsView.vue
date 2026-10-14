<!-- [pisuan-custom] 通用域「数据统计」屏：原首页 hero 三统计卡迁入（getContexts().stats 累计口径不变） -->
<template>
  <div class="stats-page">
    <div class="page-head">
      <span class="ph-icon"><ChartColumn :size="18" /></span>
      <div>
        <h1>数据统计</h1>
        <p>通用域加工沉淀的全平台累计口径</p>
      </div>
    </div>
    <div class="metric-card">
      <div class="metric-strip">
        <div v-for="m in metricCells" :key="m.key" class="metric-cell">
          <p class="m-label">{{ m.label }}</p>
          <p class="m-value">{{ stats[m.key] }}</p>
          <p class="m-desc">{{ m.desc }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive } from 'vue'
import { ChartColumn } from '@lucide/vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

const stats = reactive({ committed_tasks: 0, entity_count: 0, learned_templates: 0 })

const metricCells = [
  { key: 'committed_tasks', label: '已入库任务', desc: '完成加工链路并沉淀入库的任务' },
  { key: 'entity_count', label: '实体', desc: '结构化沉淀的实体资产' },
  { key: 'learned_templates', label: '学习模板', desc: '从语料中学到的章节模板' }
]

const fetchStats = async () => {
  try {
    const res = await domainFactoryApi.getContexts()
    if (res?.stats) Object.assign(stats, res.stats)
  } catch {
    // 静默失败，保持 0 值
  }
}

onMounted(fetchStats)
</script>

<style lang="less" scoped>
.stats-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px 24px;
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 10px;

  h1 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--gray-1000);
  }

  p {
    margin: 4px 0 0;
    font-size: 12px;
    color: var(--color-text-tertiary);
  }
}

.ph-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--main-50);
  color: var(--main-600);
}

.metric-card {
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  overflow: hidden;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.metric-cell {
  padding: 20px 24px;

  & + & {
    border-left: 1px solid var(--gray-150);
  }
}

.m-label {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.m-value {
  margin: 0 0 4px;
  font-size: 26px;
  font-weight: 800;
  color: var(--gray-1000);
  font-variant-numeric: tabular-nums;
}

.m-desc {
  margin: 0;
  font-size: 12px;
  color: var(--gray-500);
}

/* 暗色下数值/标签对比度随 token 翻转，无需额外覆写 */
</style>
