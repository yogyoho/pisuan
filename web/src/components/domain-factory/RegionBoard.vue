<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { domainFactoryApi } from '@/apis/domain_factory_api'

// [pisuan-custom] W4 子页3：聚合看板（只读）。region>6 个时组件内重排 T2 形态（左树右详情），接口不变。
const emit = defineEmits(['jump-to-tasks', 'jump-to-facts'])
const loading = ref(false)
const board = ref(null)
const expandedKey = ref(null)

const SCOPE_CARDS = [
  { key: 'universal', label: 'universal' },
  { key: 'regional', label: 'regional' },
  { key: 'project', label: 'project' },
  { key: 'unassigned', label: '未判定' }
]

// stats 子对象兜底为空对象（demo fallback 返回 {stats:{}} 时不渲染崩）
const tbs = computed(() => board.value?.stats?.templates_by_scope || {})
const fbs = computed(() => board.value?.stats?.facts_by_status || {})
const tbr = computed(() => board.value?.stats?.tasks_by_region || [])

const templateColumns = [
  { title: '模板（章族）', dataIndex: 'chapter', ellipsis: true },
  { title: 'scope', key: 'scope', width: 110 },
  { title: 'region', key: 'region', width: 140 },
  { title: '归因集', dataIndex: 'contributing_count', width: 80 },
  { title: '更新时间', key: 'updated_at', width: 150 }
]

const fetchBoard = async () => {
  loading.value = true
  try {
    board.value = await domainFactoryApi.fetchRegionBoard()
  } catch (e) {
    message.error('加载聚合看板失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const regionLabel = (node) => node.region_label || node.region_key || '未归属'
const nodeKey = (node) => node.region_key ?? '__unassigned__'
const expandedNode = computed(() => (board.value?.region_tree || []).find((n) => nodeKey(n) === expandedKey.value))
const toggleExpand = (node) => {
  expandedKey.value = expandedKey.value === nodeKey(node) ? null : nodeKey(node)
}
const regionText = (r) => (r === 'mixed' ? 'mixed（多区域）' : r || '未归属')
const fmt = (v) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—')

onMounted(fetchBoard)
defineExpose({ refresh: fetchBoard })
</script>

<template>
  <div v-if="board" class="region-board">
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-title">模板 × scope</div>
        <div class="stat-body">
          <span v-for="c in SCOPE_CARDS" :key="c.key" class="stat-item">
            <b>{{ tbs[c.key] ?? 0 }}</b> {{ c.label }}
          </span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-title">任务 × region</div>
        <div class="stat-body">
          <span v-for="r in tbr" :key="r.region_key ?? '__none__'" class="stat-item">
            <b>{{ r.count }}</b> {{ r.region_label || r.region_key || '未归属' }}
          </span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-title">事实 × 状态</div>
        <div class="stat-body">
          <span class="stat-item"><b>{{ fbs.draft ?? 0 }}</b> draft</span>
          <span class="stat-item"><b>{{ fbs.confirmed ?? 0 }}</b> confirmed</span>
          <span class="stat-item"><b>{{ fbs.retired ?? 0 }}</b> retired</span>
        </div>
      </div>
    </div>

    <h4 class="section-title">模板聚合明细</h4>
    <a-table
      :data-source="board.templates"
      :columns="templateColumns"
      :loading="loading"
      :pagination="{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }"
      :locale="{ emptyText: '新任务回写后出现（存量模板 scope=NULL 为 W3 Q3 预期行为）' }"
      row-key="id"
      size="small"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'scope'">
          <a-tag v-if="record.scope" color="blue">{{ record.scope }}</a-tag>
          <a-tag v-else>未判定</a-tag>
        </template>
        <template v-else-if="column.key === 'region'">{{ regionText(record.region) }}</template>
        <template v-else-if="column.key === 'updated_at'">{{ fmt(record.updated_at) }}</template>
      </template>
    </a-table>

    <h4 class="section-title">区域下钻</h4>
    <div class="region-cards">
      <div
        v-for="node in board.region_tree"
        :key="nodeKey(node)"
        class="region-card"
        :class="{ active: expandedKey === nodeKey(node) }"
        @click="toggleExpand(node)"
      >
        <div class="region-name">{{ expandedKey === nodeKey(node) ? '▾' : '▸' }} {{ regionLabel(node) }}</div>
        <div class="region-badges">任务 {{ node.task_count }} · 事实 {{ node.fact_count }} · 模板 {{ node.template_count }}</div>
      </div>
    </div>
    <div v-if="expandedNode" class="region-detail">
      <p>
        事实分布：监测 {{ expandedNode.fact_counts_by_type.monitoring }} · 敏感目标
        {{ expandedNode.fact_counts_by_type.sensitive_target }} · 措施
        {{ expandedNode.fact_counts_by_type.measure }} · 约束
        {{ expandedNode.fact_counts_by_type.constraint }}
      </p>
      <p v-if="expandedNode.region_key">
        <a @click="emit('jump-to-tasks', { regionKey: expandedNode.region_key })">任务 {{ expandedNode.task_count }} →</a>
        <a style="margin-left: 16px" @click="emit('jump-to-facts', { regionKey: expandedNode.region_key })">事实 {{ expandedNode.fact_count }} →</a>
      </p>
      <p v-else class="detail-hint">未归属伪节点：改判任务后自动归位</p>
    </div>
  </div>
  <a-spin v-else :spinning="loading" />
</template>

<style lang="less" scoped>
.region-board {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.stat-cards {
  display: flex;
  gap: 12px;
}
.stat-card {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--gray-200, #e2e8f0);
  border-radius: 8px;
}
.stat-title {
  font-size: 12px;
  color: var(--gray-400, #94a3b8);
}
.stat-body {
  margin-top: 4px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.stat-item {
  font-size: 13px;
}
.section-title {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--gray-500, #64748b);
}
.region-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.region-card {
  padding: 8px 14px;
  border: 1px dashed var(--gray-300, #cbd5e1);
  border-radius: 8px;
  cursor: pointer;
  &.active {
    border-color: var(--main-color, #2563eb);
    border-style: solid;
  }
}
.region-name {
  font-size: 13px;
  font-weight: 600;
}
.region-badges {
  margin-top: 4px;
  font-size: 12px;
  color: var(--gray-400, #94a3b8);
}
.region-detail {
  padding: 10px 14px;
  border: 1px solid var(--gray-200, #e2e8f0);
  border-radius: 8px;
  font-size: 13px;
  p {
    margin: 2px 0;
  }
}
.detail-hint {
  color: var(--gray-400, #94a3b8);
}
</style>
