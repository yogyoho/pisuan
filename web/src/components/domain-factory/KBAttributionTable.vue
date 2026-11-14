<script setup>
import { onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { Info } from '@lucide/vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

// [pisuan-custom] W4 子页：知识库绑定诊断。页面只读；绑定只能由入库事务产生或保留。
const loading = ref(false)
const items = ref([])
const status = ref('')
const keyword = ref('')
const pagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  showTotal: (total) => `共 ${total} 条`,
  pageSizeOptions: ['10', '20', '50', '100']
})

const STATUS_CHIPS = [
  { value: '', label: '全部' },
  { value: 'bound', label: 'bound' },
  { value: 'mixed', label: 'mixed' },
  { value: 'retained', label: 'retained' },
  { value: 'legacy', label: 'legacy' }
]
const STATUS_PILL = { bound: 'pill-ok', mixed: 'pill-err', retained: 'pill-main', legacy: 'pill-orange' }
const STATUS_LABELS = { bound: '已绑定', mixed: '冲突', retained: '保留绑定', legacy: '待绑定' }

const columns = [
  { title: '目标知识库', dataIndex: 'kb_id', ellipsis: true },
  { title: '归属身份', key: 'attribution', width: 110 },
  { title: 'region', dataIndex: 'binding_region_key', width: 130 },
  { title: 'scope', dataIndex: 'binding_scope', width: 100 },
  { title: 'project', dataIndex: 'binding_project_name', width: 140, ellipsis: true },
  { title: '任务数', dataIndex: 'task_count', width: 80 },
  { title: '状态', key: 'status', width: 160 },
  { title: '绑定时间', dataIndex: 'created_at', width: 150 }
]

const shortAttribution = (value) => (value ? value.slice(0, 8) : '—')

const fetchList = async () => {
  loading.value = true
  try {
    const params = { page: pagination.current, page_size: pagination.pageSize }
    if (status.value) params.status = status.value
    if (keyword.value) params.keyword = keyword.value
    const res = await domainFactoryApi.fetchKbAttributions(params)
    items.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {
    message.error('加载知识库绑定诊断失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const onFilterChange = () => {
  pagination.current = 1
  fetchList()
}

const onKeywordChange = (e) => {
  if (!e.target.value) onFilterChange()
}

const handleTableChange = (pag) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  fetchList()
}

const formatTime = (value) => {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

onMounted(fetchList)
defineExpose({ refresh: fetchList })
</script>

<template>
  <div class="kb-attribution-table">
    <div class="card">
      <div class="note-bar note-bar-flush">
        <Info :size="16" />
        <span>绑定由入库事务产生；retained 表示任务已删除但绑定仍阻止知识库复用。</span>
      </div>
      <div class="toolbar">
        <div class="seg">
          <button
            v-for="item in STATUS_CHIPS"
            :key="item.value"
            :class="{ on: status === item.value }"
            @click="
              () => {
                status = item.value
                onFilterChange()
              }
            "
          >
            {{ item.label }}
          </button>
        </div>
        <a-input-search
          v-model:value="keyword"
          placeholder="搜索 KB / 归属 / 区域 / 项目"
          class="search-input"
          size="small"
          allow-clear
          @search="onFilterChange"
          @change="onKeywordChange"
        />
      </div>
      <a-table
        :data-source="items"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        row-key="kb_id"
        size="small"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'attribution'">
            <span class="mono">{{ shortAttribution(record.attribution) }}</span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tooltip :title="record.status_reason || STATUS_LABELS[record.status]">
              <span class="pill pill-sm" :class="STATUS_PILL[record.status] || 'pill-gray'">
                {{ STATUS_LABELS[record.status] || record.status }}
              </span>
            </a-tooltip>
          </template>
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ formatTime(record.created_at) }}
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<style lang="less" scoped>
/* 公共配方（card/note-bar/toolbar/seg/pill/a-table 对齐）在 factory-core/factory-ui.less */
.kb-attribution-table .note-bar-flush {
  margin: 10px 16px 0;
}

.search-input {
  width: 280px;

  :deep(.ant-input-affix-wrapper) {
    height: 30px;
    border-radius: 6px;
  }
}

.mono {
  font-family: ui-monospace, 'Cascadia Code', Consolas, 'Courier New', monospace;
  font-size: 12px;
}
</style>

<style lang="less" src="../factory-core/factory-ui.less"></style>
