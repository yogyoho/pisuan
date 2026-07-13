<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { message, Modal, Upload, Select, Form } from 'ant-design-vue'
import {
  InboxOutlined,
  FileTextOutlined,
  DeleteOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  MoreOutlined,
  ReloadOutlined,
  PlusOutlined,
  AuditOutlined,
  EyeOutlined,
  RedoOutlined
} from '@ant-design/icons-vue'
import { Search } from 'lucide-vue-next'
import dayjs from 'dayjs'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useTaskerStore } from '@/stores/tasker'

const props = defineProps({
  domains: { type: Array, default: () => [] },
  selectedDomain: { type: String, default: '' },
  loadingDomains: { type: Boolean, default: false }
})

const emit = defineEmits(['update:domain', 'task-open', 'domains-refreshed'])

const taskerStore = useTaskerStore()

// 状态
const taskList = ref([])
const taskLoading = ref(false)
const historyList = ref([])
const historyLoading = ref(false)
const searchKeyword = ref('')
const uploadModalVisible = ref(false)
const uploadFiles = ref([])
const uploadFileList = ref([])
const uploading = ref(false)
const selectedReportType = ref('')
const reportTypeOptions = ref([])
const activeTab = ref('pending')

// 批量操作
const selectedRowKeys = ref([])
const batchOperating = ref(false)

// 自动刷新
let refreshTimer = null

const hasActiveTasks = computed(() =>
  taskList.value.some(t =>
    ['UPLOADED', 'PARSING', 'EXTRACTING', 'GENERALIZING'].includes(t.status)
  )
)

const startAutoRefresh = () => {
  stopAutoRefresh()
  refreshTimer = setInterval(() => {
    if (hasActiveTasks.value) {
      fetchTasks()
    } else {
      stopAutoRefresh()
    }
  }, 15000)
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// 新增：领域创建
const showDomainModal = ref(false)
const newDomain = ref({
  name: '',
  code: '',
  description: ''
})

// 新增：Markdown查看
const markdownModalVisible = ref(false)
const markdownContent = ref('')
const markdownLoading = ref(false)
const currentTaskId = ref(null)

// 状态映射
const statusMap = {
  UPLOADED: { color: 'var(--gray-400)', text: '已上传' },
  PARSING: { color: '#1677ff', text: '解析中' },
  EXTRACTING: { color: '#722ed1', text: '提取中' },
  GENERALIZING: { color: '#722ed1', text: '泛化中' },
  WAITING_REVIEW: { color: '#faad14', text: '待校验' },
  COMMITTED: { color: '#52c41a', text: '已入库' },
  COMMIT_FAILED: { color: '#ff4d4f', text: '入库失败' },
  COMMIT_PARTIAL: { color: '#faad14', text: '部分入库' },
  FAILED: { color: '#ff4d4f', text: '失败' }
}

// 计算属性
const pendingCount = computed(() => taskList.value.length)

// 领域选择
const localDomain = ref('__all__')

watch(() => props.selectedDomain, (val) => {
  if (val && val !== localDomain.value) {
    localDomain.value = val
  }
})

watch(localDomain, (val) => {
  fetchTasks(val)
  fetchHistory(val)
})

const handleDomainChange = (eventOrValue) => {
  const value = eventOrValue?.target?.value ?? eventOrValue
  if (!value || value === localDomain.value) return
  localDomain.value = value
  emit('update:domain', value)
}

const getDomainLabel = (value) => {
  if (!Array.isArray(props.domains)) return value
  const found = props.domains.find(d => (d.code || d.id || d.name) === value)
  return found?.name || value
}

const domainOptions = computed(() => {
  if (!Array.isArray(props.domains)) return []
  const allOption = { label: '全部', value: '__all__' }
  const domainList = props.domains.map(d => ({
    label: d.name,
    value: d.code || d.id || d.name
  }))
  return [allOption, ...domainList]
})

const filteredTasks = computed(() => taskList.value)

const filteredHistory = computed(() => {
  if (!searchKeyword.value) return historyList.value
  const kw = searchKeyword.value.toLowerCase()
  return historyList.value.filter(t =>
    t.file_name?.toLowerCase().includes(kw)
  )
})

const pendingAllSelected = computed(() =>
  filteredTasks.value.length > 0 && filteredTasks.value.every(t => selectedRowKeys.value.includes(t.id))
)
const pendingPartiallySelected = computed(() =>
  !pendingAllSelected.value && filteredTasks.value.some(t => selectedRowKeys.value.includes(t.id))
)
const handlePendingSelectAll = (e) => {
  selectedRowKeys.value = e.target.checked ? filteredTasks.value.map(t => t.id) : []
}
const togglePendingSelect = (id, checked) => {
  if (checked) {
    if (!selectedRowKeys.value.includes(id)) selectedRowKeys.value = [...selectedRowKeys.value, id]
  } else {
    selectedRowKeys.value = selectedRowKeys.value.filter(k => k !== id)
  }
}

// 获取任务列表
const fetchTasks = async (domain) => {
  const d = domain !== undefined ? domain : localDomain.value
  taskLoading.value = true
  try {
    const params = d && d !== '__all__' ? { domain: d } : {}
    const res = await domainFactoryApi.fetchDataSources(params)
    taskList.value = res?.pending || res?.items || []
  } catch (e) {
    console.error('fetchTasks failed:', e)
    message.error('加载待处理任务失败')
  } finally {
    taskLoading.value = false
  }
}

// 获取历史记录
const fetchHistory = async (domain) => {
  const d = domain !== undefined ? domain : localDomain.value
  historyLoading.value = true
  try {
    const params = {
      keyword: searchKeyword.value || undefined
    }
    if (d && d !== '__all__') {
      params.domain = d
    }
    const res = await domainFactoryApi.fetchHistory(params)
    historyList.value = res?.items || []
  } catch (e) {
    console.error('fetchHistory failed:', e)
  } finally {
    historyLoading.value = false
  }
}

// 刷新
const refresh = () => {
  fetchTasks()
  fetchHistory()
  if (hasActiveTasks.value) startAutoRefresh()
}

// 批量操作
const handleBatchDelete = async () => {
  if (!selectedRowKeys.value.length) return
  try {
    await Modal.confirm({
      title: `确认删除选中的 ${selectedRowKeys.value.length} 个任务？`,
      content: '删除后将无法恢复。'
    })
    batchOperating.value = true
    let ok = 0
    for (const id of selectedRowKeys.value) {
      try {
        await domainFactoryApi.deleteDataSource(id)
        ok++
      } catch (e) { /* skip */ }
    }
    message.success(`已删除 ${ok} 个任务`)
    selectedRowKeys.value = []
    refresh()
    emit('domains-refreshed')
  } catch (e) { /* cancelled */ }
  finally {
    batchOperating.value = false
  }
}

// 打开任务
const handleOpenTask = (task) => {
  emit('task-open', task)
}

// 删除任务
const handleDeleteTask = async (task) => {
  try {
    await Modal.confirm({
      title: '确认删除该任务？',
      content: '删除后将无法恢复，且不会再出现在队列中。'
    })
    await domainFactoryApi.deleteDataSource(task.id || task.task_id)
    message.success('删除成功')
    refresh()
    emit('domains-refreshed')
  } catch (e) {
    message.error('删除失败')
  }
}

// 重试任务（FAILED → 重新提取，重置为 UPLOADED 重跑整个 ETL）
const handleRetryTask = async (task) => {
  try {
    await domainFactoryApi.retryTask(task.id || task.task_id)
    message.success('已重新提交')
    refresh()
  } catch (e) {
    message.error('重试失败')
  }
}

// 重新入库（COMMIT_FAILED/COMMIT_PARTIAL → 复用已审核数据重跑 commit pipeline）
const handleReingestTask = async (task) => {
  try {
    await domainFactoryApi.reingestTask(task.id || task.task_id)
    message.success('已重新提交入库')
    refresh()
  } catch {
    message.error('重新入库失败')
  }
}

// 查看 Markdown
const handleViewMarkdown = async (task) => {
  const taskId = task.id || task.task_id
  if (!taskId) {
    message.warning('任务ID不存在')
    return
  }
  currentTaskId.value = taskId
  markdownModalVisible.value = true
  markdownLoading.value = true
  markdownContent.value = ''

  try {
    const detail = await domainFactoryApi.getTaskMarkdown(taskId)
    markdownContent.value = detail?.markdown || '暂无 markdown 数据'
  } catch (e) {
    console.error(e)
    message.error('获取 markdown 数据失败')
    markdownContent.value = '获取数据失败'
  } finally {
    markdownLoading.value = false
  }
}

// 新建领域
const showCreateDomainModal = () => {
  newDomain.value = { name: '', code: '', description: '' }
  showDomainModal.value = true
}

const handleCreateDomain = async () => {
  if (!newDomain.value.name) {
    message.warning('请输入领域名称')
    return
  }
  try {
    await domainFactoryApi.createDomain(newDomain.value)
    message.success('领域创建成功')
    showDomainModal.value = false
    emit('domains-refreshed')
  } catch (e) {
    console.error(e)
    message.error('创建领域失败')
  }
}

// 上传相关
const uploadDomain = ref('')
const uploadDomainOptions = computed(() => {
  if (!Array.isArray(props.domains)) return []
  return props.domains.map(d => ({
    label: d.name,
    value: d.code || d.id || d.name
  }))
})

const openUploadModal = async () => {
  uploadFiles.value = []
  uploadFileList.value = []
  uploadDomain.value = props.selectedDomain || (props.domains?.[0]?.code || props.domains?.[0]?.id || '')
  selectedReportType.value = ''
  await loadReportTypes()
  uploadModalVisible.value = true
}

const loadReportTypes = async () => {
  try {
    const res = await domainFactoryApi.getContexts()
    const domain = uploadDomain.value || props.selectedDomain || props.domains?.[0]?.code || ''
    const typesByDomain = res?.report_types || {}
    const types = typesByDomain[domain] || []
    reportTypeOptions.value = types.map(t => ({ label: t.name, value: t.code }))
  } catch {
    reportTypeOptions.value = []
  }
}

const handleUploadDomainChange = async () => {
  selectedReportType.value = ''
  await loadReportTypes()
}

const beforeUpload = (file) => {
  // 文件类型验证
  const isValidType = file.type === 'application/pdf' ||
    file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    file.type === 'application/msword' ||
    file.name.endsWith('.pdf') ||
    file.name.endsWith('.docx') ||
    file.name.endsWith('.doc')

  if (!isValidType) {
    message.error('只支持 .docx / .pdf 格式的文件')
    return Upload.LIST_IGNORE
  }

  // 文件大小验证 (100MB)
  const isLt100M = file.size / 1024 / 1024 < 100
  if (!isLt100M) {
    message.error('文件大小不能超过 100MB')
    return Upload.LIST_IGNORE
  }

  // 检查是否已存在
  const exists = uploadFiles.value.find(f => f.name === file.name && f.size === file.size)
  if (exists) {
    message.warning(`文件 "${file.name}" 已存在`)
    return Upload.LIST_IGNORE
  }

  uploadFiles.value.push(file)
  return false
}

const handleFileRemove = (file) => {
  const index = uploadFiles.value.findIndex(f => f.name === file.name && f.size === file.size)
  if (index > -1) {
    uploadFiles.value.splice(index, 1)
  }
  const listIndex = uploadFileList.value.findIndex(f => f.name === file.name && f.size === file.size)
  if (listIndex > -1) {
    uploadFileList.value.splice(listIndex, 1)
  }
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
}

const getFileIcon = (fileName) => {
  if (fileName?.endsWith('.pdf')) return 'pdf'
  if (fileName?.endsWith('.docx') || fileName?.endsWith('.doc')) return 'doc'
  return 'file'
}

const handleUpload = async () => {
  if (!uploadFiles.value.length) {
    message.warning('请选择文件')
    return
  }
  if (!uploadDomain.value) {
    message.warning('请选择行业领域')
    return
  }

  uploading.value = true
  try {
    for (const file of uploadFiles.value) {
      const formData = new FormData()
      formData.append('file', file.originFileObj || file)
      formData.append('domain', uploadDomain.value)
      const rtOption = reportTypeOptions.value.find(o => o.value === selectedReportType.value)
      formData.append('document_type', rtOption?.label || selectedReportType.value)
      formData.append('report_type_code', selectedReportType.value)
      const result = await domainFactoryApi.uploadSources(formData)
      console.log('上传成功，任务ID:', result?.task_id)
    }
    message.success('上传成功，任务已提交处理')
    uploadModalVisible.value = false
    uploadFiles.value = []
    uploadFileList.value = []
    selectedReportType.value = ''

    setTimeout(() => {
      refresh()
      taskerStore.loadTasks()
    }, 500)
    emit('domains-refreshed')
  } catch (e) {
    message.error('上传失败: ' + (e.message || '未知错误'))
  } finally {
    uploading.value = false
  }
}

// 格式化日期
const formatDate = (isoString) => {
  if (!isoString) return '-'
  try {
    return dayjs(isoString).format('YYYY-MM-DD HH:mm')
  } catch {
    return isoString
  }
}

const formatTime = (isoString) => {
  if (!isoString) return '-'
  try {
    return dayjs(isoString).format('YYYY-MM-DD HH:mm')
  } catch {
    return isoString
  }
}

// 置信度颜色
const getConfidenceColor = (val) => {
  if (val === null || val === undefined) return 'var(--gray-400)'
  if (val >= 80) return '#52c41a'
  if (val >= 60) return '#faad14'
  return '#ff4d4f'
}

onMounted(() => {
  refresh()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})

defineExpose({ refresh })
</script>

<template>
  <div class="data-source-dashboard">
    <!-- Header -->
    <div class="page-header">
      <div class="title">
        <h2>领域知识工厂 · 数据源管理</h2>
        <p>上传报告、跟踪解析状态、为行业工序创建高质量样本。</p>
      </div>
      <div class="actions">
        <a-button class="refresh-btn" @click="refresh" :loading="taskLoading || historyLoading">
          <ReloadOutlined /> 刷新
        </a-button>
        <a-button type="primary" @click="openUploadModal">
          <PlusOutlined /> 上传新报告
        </a-button>
      </div>
    </div>

    <!-- 领域筛选 -->
    <div class="domain-card">
      <div class="domain-toolbar">
        <div class="label">领域筛选</div>
        <div class="domains">
          <a-radio-group
            :value="localDomain"
            button-style="solid"
            @change="handleDomainChange"
          >
            <a-radio-button
              v-for="domain in domainOptions"
              :key="domain.value"
              :value="domain.value"
            >
              {{ domain.label }}
            </a-radio-button>
          </a-radio-group>
          <a-button type="link" size="small" @click="showCreateDomainModal">
            <PlusOutlined /> 新建领域
          </a-button>
        </div>
      </div>
    </div>

    <!-- 待处理任务 -->
    <div class="task-section">
      <div class="section-header">
        <div class="section-header__left">
          <span class="section-title">待处理任务</span>
          <span class="entry-count">{{ pendingCount }} 项</span>
          <a-tag v-if="hasActiveTasks" color="blue" class="processing-tag">
            <span class="pulse-dot"></span> 处理中
          </a-tag>
        </div>
        <div class="section-header__right">
          <transition name="batch-bar">
            <div v-if="selectedRowKeys.length > 0" class="batch-bar">
              <span class="batch-bar__label">
                已选 <strong>{{ selectedRowKeys.length }}</strong> 项
              </span>
              <a-button
                size="small"
                danger
                type="primary"
                :loading="batchOperating"
                @click="handleBatchDelete"
              >
                <DeleteOutlined /> 批量删除
              </a-button>
            </div>
          </transition>
        </div>
      </div>
      <div class="file-table" role="table">
        <div class="file-row table-head has-checkbox">
          <span class="checkbox-cell">
            <a-checkbox
              :checked="pendingAllSelected"
              :indeterminate="pendingPartiallySelected"
              :disabled="!filteredTasks.length"
              @change="handlePendingSelectAll"
            />
          </span>
          <span>文件名</span>
          <span class="col-center">所属领域</span>
          <span>文档类型</span>
          <span class="col-center">上传时间</span>
          <span class="col-center">状态</span>
          <span class="col-center">AI 置信度</span>
          <span class="col-action">操作</span>
        </div>
        <a-spin v-if="taskLoading" class="list-state" tip="加载中..." />
        <a-empty v-else-if="!filteredTasks.length" description="暂无待处理任务" class="list-empty" />
        <template v-for="record in filteredTasks" :key="record.id">
          <div
            class="file-row"
            @click="selectedRowKeys = [record.id]"
          >
            <span class="checkbox-cell" @click.stop>
              <a-checkbox
                :checked="selectedRowKeys.includes(record.id)"
                @change="(e) => togglePendingSelect(record.id, e.target.checked)"
              />
            </span>
            <span class="name-cell" :title="record.file_name">
              <FileTextOutlined style="color: var(--main-500); font-size: 16px; flex-shrink: 0;" />
              <span class="entry-name">{{ record.file_name }}</span>
            </span>
            <span class="col-center">{{ record.domain_label }}</span>
            <span>{{ record.document_type || record.report_type_name || record.report_type_code || '-' }}</span>
            <span class="col-center col-time">{{ formatTime(record.uploaded_at) }}</span>
            <span class="col-center">
              <span class="status-dot">
                <span class="dot" :style="{ backgroundColor: statusMap[record.status]?.color || '#999' }"></span>
                {{ statusMap[record.status]?.text || record.status }}
              </span>
            </span>
            <span class="col-center">
              <span v-if="record.ai_confidence">{{ record.ai_confidence }}%</span>
              <span v-else class="col-dash">-</span>
            </span>
            <span class="col-action" @click.stop>
              <div class="action-btns">
                <a-tooltip v-if="record.status === 'WAITING_REVIEW'" title="进入清洗工作台校验">
                  <a-button type="primary" size="small" @click="handleOpenTask(record)">
                    校验
                  </a-button>
                </a-tooltip>
                <a-tooltip v-else :title="statusMap[record.status]?.text || '处理中'">
                  <a-button size="small" disabled>
                    {{ statusMap[record.status]?.text || '处理中' }}
                  </a-button>
                </a-tooltip>
                <a-tooltip title="查看原文">
                  <a-button size="small" type="text" class="btn-view" @click="handleViewMarkdown(record)">
                    <EyeOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip v-if="record.status === 'FAILED'" title="重新提取">
                  <a-button size="small" type="text" @click="handleRetryTask(record)">
                    <RedoOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip v-else-if="record.status === 'COMMIT_FAILED' || record.status === 'COMMIT_PARTIAL'" title="重新入库">
                  <a-button size="small" type="text" @click="handleReingestTask(record)">
                    <RedoOutlined />
                  </a-button>
                </a-tooltip>
                <a-popconfirm
                  title="确定删除此任务吗？"
                  @confirm="handleDeleteTask(record)"
                >
                  <a-tooltip title="删除">
                    <a-button size="small" danger type="text" class="btn-delete">
                      <DeleteOutlined />
                    </a-button>
                  </a-tooltip>
                </a-popconfirm>
              </div>
            </span>
          </div>
        </template>
      </div>
    </div>

    <!-- 历史记录 -->
    <div class="task-section task-section--history">
      <div class="section-header">
        <div class="section-header__left">
          <span class="section-title">已入库历史文档</span>
          <span class="entry-count">{{ filteredHistory.length }} 项</span>
        </div>
        <div class="section-header__right">
          <a-input
            v-model:value="searchKeyword"
            placeholder="搜索文件名..."
            class="history-search"
            allow-clear
            @change="fetchHistory"
          >
            <template #prefix><Search :size="14" class="search-icon" /></template>
          </a-input>
        </div>
      </div>
      <div class="file-table" role="table">
        <div class="file-row table-head no-checkbox">
          <span>文件名</span>
          <span class="col-center">所属领域</span>
          <span>文档类型</span>
          <span class="col-center">操作人</span>
          <span class="col-center">入库时间</span>
          <span class="col-center">置信度</span>
          <span class="col-action">操作</span>
        </div>
        <a-spin v-if="historyLoading" class="list-state" tip="加载中..." />
        <a-empty v-else-if="!filteredHistory.length" description="暂无历史数据" class="list-empty" />
        <template v-for="record in filteredHistory" :key="record.id">
          <div class="file-row no-checkbox" @click="handleViewMarkdown(record)">
            <span class="name-cell" :title="record.file_name">
              <FileTextOutlined style="color: var(--main-500); font-size: 16px; flex-shrink: 0;" />
              <span class="entry-name">{{ record.file_name }}</span>
            </span>
            <span class="col-center">{{ record.domain_label }}</span>
            <span>{{ record.document_type }}</span>
            <span class="col-center">{{ record.reviewer || '-' }}</span>
            <span class="col-center col-time">{{ formatDate(record.committed_at) }}</span>
            <span class="col-center">
              <span v-if="record.ai_confidence">{{ record.ai_confidence }}%</span>
              <span v-else class="col-dash">-</span>
            </span>
            <span class="col-action" @click.stop>
              <div class="action-btns">
                <a-tooltip title="查看原文">
                  <a-button size="small" type="text" class="btn-view" @click="handleViewMarkdown(record)">
                    <EyeOutlined />
                  </a-button>
                </a-tooltip>
                <a-popconfirm
                  title="确定删除此记录吗？"
                  @confirm="handleDeleteTask(record)"
                >
                  <a-tooltip title="删除">
                    <a-button size="small" danger type="text" class="btn-delete">
                      <DeleteOutlined />
                    </a-button>
                  </a-tooltip>
                </a-popconfirm>
              </div>
            </span>
          </div>
        </template>
      </div>
    </div>

    <!-- 上传弹窗 -->
    <a-modal
      v-model:open="uploadModalVisible"
      title="上传新报告"
      :confirm-loading="uploading"
      ok-text="开始解析"
      width="640px"
      @ok="handleUpload"
      @cancel="uploadFiles = []"
    >
      <div class="upload-modal-content">
        <div class="upload-instruction">
          <p class="instruction-text">选择本地文件，上传后将自动解析文档内容。</p>
        </div>

        <div class="form-selectors">
          <a-form-item label="行业领域" required>
            <a-select
              v-model:value="uploadDomain"
              :options="uploadDomainOptions"
              placeholder="选择行业领域"
              style="width: 100%"
              @change="handleUploadDomainChange"
            />
          </a-form-item>
          <a-form-item label="报告类型" required>
            <a-select
              v-model:value="selectedReportType"
              :options="reportTypeOptions"
              placeholder="选择报告类型"
              style="width: 100%"
            />
          </a-form-item>
        </div>

        <a-upload-dragger
          v-model:file-list="uploadFileList"
          :before-upload="beforeUpload"
          :multiple="true"
          :accept="'.doc,.docx,.pdf'"
          :show-upload-list="false"
          class="custom-upload-dragger"
        >
          <div class="upload-icon-wrapper">
            <InboxOutlined class="upload-icon" />
          </div>
          <p class="ant-upload-text">点击或拖拽文件至此</p>
          <p class="ant-upload-hint">支持 Word/PDF 格式，单个文件不超过 100MB</p>
        </a-upload-dragger>

        <!-- 已选文件列表 -->
        <div class="file-list" v-if="uploadFiles.length > 0">
          <div class="file-items">
            <div
              v-for="(file, index) in uploadFiles"
              :key="`${file.name}-${file.size}-${index}`"
              class="file-item"
            >
              <div class="file-status-dot"></div>
              <div class="file-icon-wrapper">
                <FilePdfOutlined v-if="getFileIcon(file.name) === 'pdf'" class="file-icon pdf-icon" />
                <FileWordOutlined v-else-if="getFileIcon(file.name) === 'doc'" class="file-icon doc-icon" />
                <FileTextOutlined v-else class="file-icon file-icon-default" />
              </div>
              <div class="file-name" :title="file.name">{{ file.name }}</div>
              <div class="file-size">{{ formatFileSize(file.size) }}</div>
              <a-button
                type="text"
                danger
                size="small"
                class="file-remove-btn"
                @click="handleFileRemove(file)"
                :disabled="uploading"
              >
                <DeleteOutlined />
              </a-button>
            </div>
          </div>
          <div class="file-confirm-message">
            已选择 {{ uploadFiles.length }} 个文件，点击"开始解析"上传
          </div>
        </div>
      </div>
    </a-modal>

    <!-- 新建领域弹窗 -->
    <a-modal
      v-model:open="showDomainModal"
      title="新建领域"
      @ok="handleCreateDomain"
      ok-text="创建"
    >
      <a-form layout="vertical">
        <a-form-item label="领域名称" required>
          <a-input v-model:value="newDomain.name" placeholder="如：煤炭采掘" />
        </a-form-item>
        <a-form-item label="领域标识">
          <a-input v-model:value="newDomain.code" placeholder="仅用于接口标识，可留空自动生成" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea
            v-model:value="newDomain.description"
            rows="3"
            placeholder="补充该领域适用范围"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Markdown 查看弹窗 -->
    <a-modal
      v-model:open="markdownModalVisible"
      title="Markdown 数据查看"
      width="900px"
      :footer="null"
      :bodyStyle="{ maxHeight: '70vh', overflow: 'auto' }"
    >
      <a-spin :spinning="markdownLoading">
        <div class="markdown-viewer">
          <pre v-if="markdownContent" class="markdown-content">{{ markdownContent }}</pre>
          <a-empty v-else description="暂无 markdown 数据" />
        </div>
      </a-spin>
    </a-modal>
  </div>
</template>

<style lang="less" scoped>
.data-source-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: #fff;
  border-radius: 0;
  border-bottom: 1px solid var(--gray-150);

  .title {
    h2 {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
    }
    p {
      margin: 4px 0 0;
      color: var(--gray-500);
      font-size: 13px;
    }
  }

  .actions {
    display: flex;
    gap: 12px;

    .refresh-btn {
      border-radius: 999px;
      border: 1px solid var(--gray-300);
      background: #ffffff;
      color: var(--gray-700);
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);

      &:hover {
        border-color: var(--main-color);
        color: var(--main-color);
        background: rgba(22, 119, 255, 0.04);
      }
    }
  }
}

.domain-card {
  background: #fff;
  border-radius: 0;
  border-left: none;
  border-right: none;
  padding: 10px 20px;

  :deep(.ant-card-body) {
    padding: 16px 24px;
  }

  .domain-toolbar {
    .label {
      font-size: 14px;
      font-weight: 600;
      color: var(--gray-600);
      margin-bottom: 12px;
    }

    .domains {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;

      :deep(.ant-radio-button-wrapper) {
        font-size: 12px;
        height: 28px;
        line-height: 26px;
        padding: 0 12px;
      }

      :deep(.ant-btn-link) {
        font-size: 12px;
        height: 28px;
        line-height: 28px;
        padding: 0 8px;
      }
    }
  }
}

.task-section {
  background: var(--gray-0, #fff);
  margin-bottom: 16px;

  &--history {
    margin-top: 24px;
  }
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
  padding: 0 14px;
  border-bottom: 1px solid var(--gray-100, #f1f5f9);

  &__left,
  &__right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__right {
    flex: 0 0 auto;
  }

  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--gray-900, #0f172a);
  }

  .entry-count {
    color: var(--gray-500, #64748b);
    font-size: 12px;
  }

  .processing-tag {
    font-size: 11px;
  }

  .history-search {
    width: 240px;
    display: flex;
    align-items: center;

    :deep(.ant-input-affix-wrapper) {
      height: 32px;
      padding: 0 10px;
      border: 1px solid var(--gray-150);
      border-radius: 8px;
      background-color: var(--gray-0);

      &:hover,
      &:focus,
      &.ant-input-affix-wrapper-focused {
        border-color: var(--gray-200);
        box-shadow: none;
      }
    }

    :deep(.ant-input-prefix) {
      margin-right: 8px;
      color: var(--gray-400);
    }

    :deep(.ant-input) {
      height: 100%;
      background-color: transparent;
      font-size: 13px;
    }
  }

  .search-icon {
    color: var(--gray-400);
  }
}

.file-table {
  min-height: 0;
  overflow-y: auto;
}

.file-row {
  display: grid;
  grid-template-columns: 34px minmax(150px, 1fr) 88px 120px 140px 110px 88px 180px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 38px;
  padding: 0 14px;
  border: 0;
  border-bottom: 1px solid var(--gray-50, #f8fafc);
  background: transparent;
  color: var(--gray-700, #334155);
  font-size: 13px;
  text-align: left;

  &:not(.table-head) {
    cursor: pointer;
  }

  &:hover:not(.table-head) {
    background: var(--main-20, #fafcff);
    color: var(--gray-1000, #0c0d0d);
  }

  &.no-checkbox {
    grid-template-columns: minmax(150px, 1fr) 88px 100px 100px 130px 88px 100px;
  }
}

.table-head {
  position: sticky;
  top: 0;
  z-index: 1;
  min-height: 34px;
  background: var(--gray-25, #fefeff);
  color: var(--gray-500, #64748b);
  font-size: 12px;
  font-weight: 600;
}

.checkbox-cell {
  display: inline-flex;
  align-items: center;
}

.name-cell {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.entry-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-center {
  text-align: center;
  justify-self: center;
}

.col-time {
  font-variant-numeric: tabular-nums;
}

.col-dash {
  color: var(--gray-400, #94a3b8);
}

.col-action {
  justify-self: start;
}

.status-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
}

.list-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 180px;
  color: var(--gray-500);
  width: 100%;
}

.list-empty {
  margin-top: 48px;
}

// 上传弹窗样式
.upload-modal-content {
  .upload-instruction {
    margin-bottom: 20px;

    .instruction-text {
      margin: 0;
      font-size: 14px;
      color: var(--gray-600);
    }
  }

  .form-selectors {
    margin-bottom: 20px;
  }

  .custom-upload-dragger {
    :deep(.ant-upload-drag) {
      background: #fafafa;
      border: 2px dashed #d9d9d9;
      border-radius: 8px;
      padding: 40px 20px;
      transition: all 0.3s ease;

      &:hover {
        border-color: var(--main-color);
        background: rgba(22, 119, 255, 0.02);
      }
    }

    .upload-icon-wrapper {
      display: flex;
      justify-content: center;
      align-items: center;
      margin-bottom: 16px;

      .upload-icon {
        font-size: 48px;
        color: var(--main-color);
      }
    }

    :deep(.ant-upload-text) {
      font-size: 15px;
      font-weight: 500;
      color: var(--gray-800);
    }

    :deep(.ant-upload-hint) {
      font-size: 13px;
      color: var(--gray-500);
    }
  }

  .file-list {
    margin-top: 16px;

    .file-items {
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: 200px;
      overflow-y: auto;
      padding: 12px;
      background: var(--gray-50);
      border-radius: 8px;
    }

    .file-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 12px;
      background: #fff;
      border-radius: 6px;
      border: 1px solid var(--gray-100);

      .file-status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #52c41a;
        flex-shrink: 0;
      }

      .file-icon-wrapper {
        .file-icon {
          font-size: 20px;

          &.pdf-icon { color: #dc2626; }
          &.doc-icon { color: #2563eb; }
          &.file-icon-default { color: var(--gray-500); }
        }
      }

      .file-name {
        flex: 1;
        min-width: 0;
        font-size: 14px;
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .file-size {
        font-size: 12px;
        color: var(--gray-500);
        flex-shrink: 0;
      }

      .file-remove-btn {
        opacity: 0.6;
        &:hover { opacity: 1; }
      }
    }

    .file-confirm-message {
      margin-top: 12px;
      font-size: 13px;
      color: var(--gray-600);
      text-align: center;
    }
  }
}

.markdown-viewer {
  .markdown-content {
    padding: 16px;
    background: var(--gray-50);
    border-radius: 8px;
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 60vh;
    overflow-y: auto;
  }
}

.action-btns {
  display: inline-flex;
  align-items: center;
  gap: 6px;

  :deep(.ant-btn) {
    font-size: 12px;
  }

  .btn-delete {
    border-radius: 4px;
    color: var(--gray-400, #94a3b8);

    &:hover {
      color: #ff4d4f;
      background: rgba(255, 77, 79, 0.06);
    }
  }

  .btn-view,
  .btn-delete {
    width: 28px;
    height: 28px;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    color: var(--gray-400, #94a3b8);
  }

  .btn-view:hover {
    color: #1677ff;
    background: rgba(22, 119, 255, 0.06);
  }

  .btn-delete:hover {
    color: #ff4d4f;
    background: rgba(255, 77, 79, 0.06);
  }
}

.batch-bar {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 4px 12px;
  background: rgba(255, 77, 79, 0.06);
  border: 1px solid rgba(255, 77, 79, 0.15);
  border-radius: 6px;
  font-size: 13px;
  color: var(--gray-600, #475569);

  .batch-bar__label strong {
    color: #ff4d4f;
    font-weight: 600;
  }
}

.batch-bar-enter-active,
.batch-bar-leave-active {
  transition: all 0.25s ease;
}

.batch-bar-enter-from,
.batch-bar-leave-to {
  opacity: 0;
  transform: translateX(8px);
}

.pulse-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #1677ff;
  animation: pulse 1.5s ease-in-out infinite;
  vertical-align: middle;
  margin-right: 4px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
