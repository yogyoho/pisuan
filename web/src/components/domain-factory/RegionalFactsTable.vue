<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useUserStore } from '@/stores/user'

// [pisuan-custom] W4 子页2：区域事实浏览 + admin 批量退役。
// API 层 get_admin_user 兜底，前端 isAdmin 仅展示层收敛（不重复鉴权假设）。
const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const regionKey = ref('')
const factType = ref('')
const status = ref('')
const selectedIds = ref([])
const regionOptions = ref([{ value: '', label: '全部 region' }])
const pagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  showTotal: (t) => `共 ${t} 条`,
  pageSizeOptions: ['10', '20', '50', '100']
})

const FACT_TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  { value: 'monitoring', label: '监测' },
  { value: 'sensitive_target', label: '敏感目标' },
  { value: 'measure', label: '措施' },
  { value: 'constraint', label: '约束' }
]
const STATUS_CHIPS = [
  { value: '', label: '全部' },
  { value: 'draft', label: 'draft' },
  { value: 'confirmed', label: 'confirmed' },
  { value: 'retired', label: 'retired' }
]
const STATUS_COLORS = { draft: 'orange', confirmed: 'green', retired: 'default' }
const TYPE_LABELS = { monitoring: '监测', sensitive_target: '敏感目标', measure: '措施', constraint: '约束' }

const columns = [
  { title: '类型', key: 'fact_type', width: 90 },
  { title: 'region', dataIndex: 'region_key', width: 120 },
  { title: '内容', dataIndex: 'content', ellipsis: true },
  { title: '状态', key: 'status', width: 100 },
  { title: '年份', dataIndex: 'year', width: 70 },
  { title: '来源任务', dataIndex: 'source_task_file_name', ellipsis: true, width: 220 }
]

const fetchList = async () => {
  loading.value = true
  try {
    const params = { page: pagination.current, page_size: pagination.pageSize }
    if (regionKey.value) params.region_key = regionKey.value
    if (factType.value) params.fact_type = factType.value
    if (status.value) params.status = status.value
    const res = await domainFactoryApi.fetchRegionalFacts(params)
    items.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {
    message.error('加载区域事实失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// region 下拉候选来自看板树（真实存在的 region 才可筛）
const fetchRegionOptions = async () => {
  try {
    const board = await domainFactoryApi.fetchRegionBoard()
    const opts = (board.region_tree || [])
      .filter((n) => n.region_key)
      .map((n) => ({
        value: n.region_key,
        label: `${n.region_label || n.region_key}（${n.region_key}）`
      }))
    regionOptions.value = [{ value: '', label: '全部 region' }, ...opts]
  } catch (e) {
    console.warn('[RegionalFactsTable] region 候选加载失败（不影响浏览）', e)
  }
}

const onFilterChange = () => {
  pagination.current = 1
  fetchList()
}
const handleTableChange = (pag) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchList()
}

const rowSelection = computed(() => {
  if (!userStore.isAdmin) return undefined
  return {
    selectedRowKeys: selectedIds.value,
    onChange: (keys) => {
      selectedIds.value = keys
    }
  }
})

const rowClassName = (record) => (record.status === 'retired' ? 'fact-retired' : '')

const confirmRetire = () => {
  Modal.confirm({
    title: `批量退役 ${selectedIds.value.length} 条区域事实？`,
    content: '退役 = status→retired 留审计行，不删数据；操作不可恢复，请确认。',
    okText: '批量退役',
    okType: 'danger',
    onOk: async () => {
      try {
        const res = await domainFactoryApi.retireRegionalFacts(selectedIds.value)
        message.success(`已退役 ${res.retired} 条`)
        selectedIds.value = []
        fetchList()
      } catch (e) {
        message.error('退役失败: ' + (e.message || '未知错误'))
      }
    }
  })
}

onMounted(() => {
  fetchList()
  fetchRegionOptions()
})
defineExpose({
  applyRegionFilter: (rk) => {
    regionKey.value = rk || ''
    pagination.current = 1
    fetchList()
  },
  refresh: fetchList
})
</script>

<template>
  <div class="regional-facts-table">
    <div class="filter-bar">
      <a-select v-model:value="regionKey" :options="regionOptions" style="width: 200px" size="small" @change="onFilterChange" />
      <a-select
        :options="FACT_TYPE_OPTIONS"
        style="width: 120px"
        size="small"
        :value="factType"
        @change="(v) => { factType = v; onFilterChange() }"
      />
      <a-radio-group :value="status" button-style="solid" size="small" @change="(e) => { status = e.target.value; onFilterChange() }">
        <a-radio-button v-for="c in STATUS_CHIPS" :key="c.value" :value="c.value">{{ c.label }}</a-radio-button>
      </a-radio-group>
    </div>
    <a-table
      :data-source="items"
      :columns="columns"
      :loading="loading"
      :pagination="pagination"
      :row-selection="rowSelection"
      :row-class-name="rowClassName"
      row-key="id"
      size="small"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'fact_type'">
          {{ TYPE_LABELS[record.fact_type] || record.fact_type }}
        </template>
        <template v-else-if="column.key === 'status'">
          <a-tag :color="STATUS_COLORS[record.status]">{{ record.status }}</a-tag>
        </template>
      </template>
    </a-table>
    <div v-if="userStore.isAdmin && selectedIds.length" class="batch-bar">
      <span>已选 {{ selectedIds.length }} 条</span>
      <a-button danger size="small" @click="confirmRetire">批量退役</a-button>
    </div>
  </div>
</template>

<style lang="less" scoped>
.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding: 6px 12px;
  background: var(--warning-bg, #fff7e6);
  border-radius: 6px;
  width: fit-content;
}
:deep(.fact-retired) {
  opacity: 0.5;
}
</style>
