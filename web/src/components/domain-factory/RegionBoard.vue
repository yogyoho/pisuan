<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { domainFactoryApi } from '@/apis/domain_factory_api'

// [pisuan-custom] W4 子页3：模板隔离诊断（只读）。region>6 个时组件内重排 T2 形态（左树右详情）。
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
// 同一 region_key 历史标签可能漂移（用户自由文本），按 key 归并（先到 label 优先，与树侧一致）防卡片拆行
const tbr = computed(() => {
  const merged = new Map()
  for (const r of board.value?.stats?.tasks_by_region || []) {
    const k = r.region_key ?? '__none__'
    if (merged.has(k)) merged.get(k).count += r.count || 0
    else merged.set(k, { ...r, count: r.count || 0 })
  }
  return [...merged.values()]
})

const templateColumns = [
  { title: '模板（章族）', dataIndex: 'chapter', ellipsis: true },
  { title: 'scope', key: 'scope', width: 110 },
  { title: '归属身份', key: 'attribution', width: 110 },
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
const expandedNode = computed(() =>
  (board.value?.region_tree || []).find((n) => nodeKey(n) === expandedKey.value)
)
const toggleExpand = (node) => {
  expandedKey.value = expandedKey.value === nodeKey(node) ? null : nodeKey(node)
}
const regionText = (r) => (r === 'mixed' ? 'mixed（多区域）' : r || '未归属')
const attributionText = (value) => (value ? value.slice(0, 8) : 'legacy')
const legacyConfirmedFacts = computed(() => board.value?.stats?.facts_by_attribution?.['']?.confirmed || 0)
const fmt = (v) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—')

onMounted(fetchBoard)
defineExpose({ refresh: fetchBoard })
</script>

<template>
  <div v-if="board" class="region-board">
    <!-- 指标带（EIA metric-strip 配方：三 cell 分栏） -->
    <div class="metric-strip">
      <div class="metric-cell">
        <div class="metric-label">模板 × scope</div>
        <div class="metric-value metric-vals">
          <span v-for="c in SCOPE_CARDS" :key="c.key">
            <b>{{ tbs[c.key] ?? 0 }}</b> {{ c.label }}
          </span>
        </div>
      </div>
      <div class="metric-cell">
        <div class="metric-label">任务 × region</div>
        <div class="metric-value metric-vals">
          <span v-for="r in tbr" :key="r.region_key ?? '__none__'">
            <b>{{ r.count }}</b> {{ r.region_label || r.region_key || '未归属' }}
          </span>
        </div>
      </div>
      <div class="metric-cell" :class="{ warn: legacyConfirmedFacts > 0 }">
        <div class="metric-label">事实 × 状态</div>
        <div class="metric-value metric-vals">
          <span><b>{{ fbs.draft ?? 0 }}</b> draft</span>
          <span><b>{{ fbs.confirmed ?? 0 }}</b> confirmed</span>
          <span><b>{{ fbs.retired ?? 0 }}</b> retired</span>
          <span v-if="legacyConfirmedFacts">
            <b>{{ legacyConfirmedFacts }}</b> 未证明归属
          </span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-hd">
        <h3>模板隔离明细</h3>
      </div>
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
            <span class="pill pill-sm" :class="record.scope ? 'pill-main' : 'pill-gray'">
              {{ record.scope || '未判定' }}
            </span>
          </template>
          <template v-else-if="column.key === 'attribution'">
            <span class="pill pill-sm" :class="record.attribution ? 'pill-main' : 'pill-err'">
              {{ attributionText(record.attribution) }}
            </span>
          </template>
          <template v-else-if="column.key === 'region'">{{ regionText(record.region) }}</template>
          <template v-else-if="column.key === 'updated_at'">{{ fmt(record.updated_at) }}</template>
        </template>
      </a-table>
    </div>

    <h4 class="section-title">区域下钻</h4>
    <div class="region-cards">
      <div
        v-for="node in board.region_tree"
        :key="nodeKey(node)"
        class="region-card"
        :class="{ active: expandedKey === nodeKey(node) }"
        @click="toggleExpand(node)"
      >
        <div class="region-name">
          {{ expandedKey === nodeKey(node) ? '▾' : '▸' }} {{ regionLabel(node) }}
        </div>
        <div class="region-badges">
          任务 {{ node.task_count }} · 事实 {{ node.fact_count }} · 模板 {{ node.template_count }}
        </div>
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
        <button
          class="btn btn-sm btn-txt"
          @click="emit('jump-to-tasks', { regionKey: expandedNode.region_key })"
          >任务 {{ expandedNode.task_count }} →</button
        >
        <button
          class="btn btn-sm btn-txt"
          @click="emit('jump-to-facts', { regionKey: expandedNode.region_key })"
          >事实 {{ expandedNode.fact_count }} →</button
        >
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

/* metric-vals：指标带内的多值行（数值 tabular + 12px 说明字，EIA metric-cell 语义）；
   三级前缀提升优先级，稳定压过 factory-ui 全局 .metric-value 的 22px 大数配方 */
.region-board .metric-strip .metric-vals {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 13px;
  font-weight: 400;
  color: var(--color-text-secondary);

  b {
    font-weight: 700;
    color: var(--gray-800);
  }
}

.region-board .metric-strip .metric-warn {
  color: var(--second-600);
}

.region-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.region-card {
  padding: 8px 14px;
  border: 1px dashed var(--gray-200);
  border-radius: 8px;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;

  &:hover {
    background: var(--gray-50);
  }

  /* 选中态同 fam-item.on：主色浅底 + 内嵌左缘（原型 .proto 语汇） */
  &.active {
    background: var(--main-50);
    border: 1px solid var(--main-300);
    box-shadow: inset 2px 0 0 var(--main-500);
  }
}
.region-name {
  font-size: 13px;
  font-weight: 600;
}
.region-badges {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.region-detail {
  padding: 10px 16px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);
  font-size: 13px;
  p {
    margin: 2px 0;
  }
}
.detail-hint {
  color: var(--color-text-tertiary);
}
</style>

<style lang="less" src="../factory-core/factory-ui.less"></style>
