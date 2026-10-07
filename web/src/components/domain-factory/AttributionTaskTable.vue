<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import AttributionEditModal from './AttributionEditModal.vue'

// [pisuan-custom] W4 子页1：任务归属列表（scope chips + 关键词 + 逐行改判入口）
const loading = ref(false)
const items = ref([])
const scopeFilter = ref('all')
const keyword = ref('')
const regionKeyFilter = ref('')
const pagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  showTotal: (t) => `共 ${t} 条`,
  pageSizeOptions: ['10', '20', '50', '100']
})

const SCOPE_CHIPS = [
  { value: 'all', label: '全部' },
  { value: 'regional', label: 'regional' },
  { value: 'project', label: 'project' },
  { value: 'universal', label: 'universal' },
  { value: 'unassigned', label: '未归属' }
]

const columns = [
  { title: '任务', dataIndex: 'file_name', ellipsis: true },
  { title: '领域', dataIndex: 'domain_label', width: 110 },
  { title: 'scope', key: 'scope', width: 110 },
  { title: 'region_label', dataIndex: 'region_label', width: 140, ellipsis: true },
  { title: 'region_key', dataIndex: 'region_key', width: 130 },
  { title: '任务状态', dataIndex: 'status', width: 140 },
  { title: '操作', key: 'action', width: 100 }
]

const fetchList = async () => {
  loading.value = true
  try {
    const params = { page: pagination.current, page_size: pagination.pageSize }
    if (scopeFilter.value !== 'all') params.scope = scopeFilter.value
    if (regionKeyFilter.value) params.region_key = regionKeyFilter.value
    if (keyword.value) params.keyword = keyword.value
    const res = await domainFactoryApi.fetchAttributionTasks(params)
    items.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {
    message.error('加载任务归属列表失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const onFilterChange = () => {
  pagination.current = 1
  fetchList()
}

// allow-clear 清空（或手动删空）时立即解除关键词过滤；输入中不触发
const onKeywordChange = (e) => {
  if (!e.target.value) onFilterChange()
}

const handleTableChange = (pag) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchList()
}

// 看板下钻跳转入口：真实 region key → region 过滤；'' → 清过滤
const applyRegionFilter = (regionKey) => {
  regionKeyFilter.value = regionKey || ''
  scopeFilter.value = 'all'
  pagination.current = 1
  fetchList()
}
const clearRegionFilter = () => applyRegionFilter('')

const usedRegionKeys = computed(
  () => [...new Set(items.value.map((t) => t.region_key).filter(Boolean))]
)

const editingTask = ref(null)
const handleEdited = (result) => {
  message.success(
    `已归属 ${result.region_key}：级联确认事实 ${result.facts_confirmed} 条，重算模板 ${result.templates_recalculated} 个`
  )
  editingTask.value = null
  fetchList()
}

onMounted(fetchList)
defineExpose({ applyRegionFilter, refresh: fetchList })
</script>

<template>
  <div class="attribution-task-table">
    <div class="filter-bar">
      <a-radio-group v-model:value="scopeFilter" button-style="solid" size="small" @change="onFilterChange">
        <a-radio-button v-for="c in SCOPE_CHIPS" :key="c.value" :value="c.value">{{ c.label }}</a-radio-button>
      </a-radio-group>
      <a-input-search
        v-model:value="keyword"
        placeholder="搜索任务名"
        style="width: 220px"
        size="small"
        allow-clear
        @search="onFilterChange"
        @change="onKeywordChange"
      />
      <a-tag v-if="regionKeyFilter" closable color="blue" @close="clearRegionFilter">
        region: {{ regionKeyFilter }}
      </a-tag>
    </div>
    <a-table
      :data-source="items"
      :columns="columns"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="small"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'scope'">
          <a-tag v-if="record.scope" color="blue">{{ record.scope }}</a-tag>
          <a-tag v-else>未归属</a-tag>
        </template>
        <template v-else-if="column.key === 'action'">
          <a @click="editingTask = record">{{ record.region_key ? '改判' : '归属确认' }}</a>
        </template>
      </template>
    </a-table>
    <AttributionEditModal
      :open="!!editingTask"
      :task="editingTask"
      :used-keys="usedRegionKeys"
      @close="editingTask = null"
      @edited="handleEdited"
    />
  </div>
</template>

<style lang="less" scoped>
.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
