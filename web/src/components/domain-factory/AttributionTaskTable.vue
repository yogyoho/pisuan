<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import AttributionEditModal from './AttributionEditModal.vue'
import { dotStyle, statusMap } from './taskStatus'

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
  { value: 'regional', label: '区域级' },
  { value: 'project', label: '项目级' },
  { value: 'universal', label: '通用级' },
  { value: 'unassigned', label: '未归属' }
]

// scope 的英文枚举 → 中文展示（底层过滤值保持英文，作为 API 契约）；状态文案/颜色共用 taskStatus.js
const SCOPE_LABELS = { regional: '区域级', project: '项目级', universal: '通用级' }

const columns = [
  { title: '任务', dataIndex: 'file_name', ellipsis: true },
  { title: '归属层级', key: 'scope', width: 110 },
  { title: '区域名称', dataIndex: 'region_label', width: 140, ellipsis: true },
  { title: '区域标识', dataIndex: 'region_key', width: 130 },
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

const usedRegionKeys = computed(() => [
  ...new Set(items.value.map((t) => t.region_key).filter(Boolean))
])

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
    <div class="card">
      <div class="toolbar">
        <div class="seg">
          <button
            v-for="c in SCOPE_CHIPS"
            :key="c.value"
            :class="{ on: scopeFilter === c.value }"
            @click="
              () => {
                scopeFilter = c.value
                onFilterChange()
              }
            "
          >
            {{ c.label }}
          </button>
        </div>
        <a-input-search
          v-model:value="keyword"
          placeholder="搜索任务名"
          class="search-input"
          size="small"
          allow-clear
          @search="onFilterChange"
          @change="onKeywordChange"
        />
        <span v-if="regionKeyFilter" class="pill pill-sm pill-main">
          区域：{{ regionKeyFilter }}
          <button class="pill-x" title="清除区域过滤" @click="clearRegionFilter">×</button>
        </span>
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
            <span class="pill pill-sm" :class="record.scope ? 'pill-main' : 'pill-gray'">
              {{ SCOPE_LABELS[record.scope] || '未归属' }}
            </span>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <span class="status-dot">
              <span class="dot" :style="dotStyle(record.status)"></span>
              {{ statusMap[record.status]?.text || record.status }}
            </span>
          </template>
          <template v-else-if="column.key === 'action'">
            <button class="btn btn-sm btn-txt" @click="editingTask = record">
              {{ record.region_key ? '改判' : '归属确认' }}
            </button>
          </template>
        </template>
      </a-table>
    </div>
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
/* 公共配方（card/toolbar/seg/pill/btn/a-table 对齐）在 factory-core/factory-ui.less */

/* 正文列（任务/region_label/region_key/任务状态）13px；scope/操作列由 pill/btn 自带字号不受影响。
   :deep 前置 .attribution-task-table 使 [data-v] 落在根节点，才能命中 AntD 渲染的 td */
.attribution-task-table :deep(.ant-table-tbody > tr > td) {
  font-size: 13px;
}

/* 状态点：与数据源管理页待处理列表同款（taskStatus.js 提供颜色/光环） */
.status-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex: none;
  }
}

.search-input {
  width: 220px;

  :deep(.ant-input-affix-wrapper) {
    height: 30px;
    border-radius: 6px;
  }
}

.pill-x {
  appearance: none;
  border: none;
  background: none;
  padding: 0 0 0 2px;
  font-size: 12px;
  line-height: 1;
  color: inherit;
  cursor: pointer;

  &:hover {
    color: var(--main-700);
  }
}
</style>

<style lang="less" src="../factory-core/factory-ui.less"></style>
