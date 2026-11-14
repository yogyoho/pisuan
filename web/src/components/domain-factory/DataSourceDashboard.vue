<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { message, Modal, Upload } from 'ant-design-vue'
import { FileText, FileType2, Inbox, Plus, RotateCw, Search, Trash2 } from '@lucide/vue'
import dayjs from 'dayjs'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useTaskerStore } from '@/stores/tasker'
import { dotStyle, statusMap } from './taskStatus'

const emit = defineEmits(['task-open'])

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

// 批量操作
const selectedRowKeys = ref([])
const batchOperating = ref(false)

// 自动刷新
let refreshTimer = null

const hasActiveTasks = computed(() =>
  taskList.value.some((t) =>
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

// 新增：Markdown查看
const markdownModalVisible = ref(false)
const markdownContent = ref('')
const markdownLoading = ref(false)
const currentTaskId = ref(null)

// 计算属性
const pendingCount = computed(() => taskList.value.length)

const filteredTasks = computed(() => taskList.value)

const filteredHistory = computed(() => {
  if (!searchKeyword.value) return historyList.value
  const kw = searchKeyword.value.toLowerCase()
  return historyList.value.filter((t) => t.file_name?.toLowerCase().includes(kw))
})

const pendingAllSelected = computed(
  () =>
    filteredTasks.value.length > 0 &&
    filteredTasks.value.every((t) => selectedRowKeys.value.includes(t.id))
)
const pendingPartiallySelected = computed(
  () =>
    !pendingAllSelected.value &&
    filteredTasks.value.some((t) => selectedRowKeys.value.includes(t.id))
)
const handlePendingSelectAll = (e) => {
  selectedRowKeys.value = e.target.checked ? filteredTasks.value.map((t) => t.id) : []
}
const togglePendingSelect = (id, checked) => {
  if (checked) {
    if (!selectedRowKeys.value.includes(id)) selectedRowKeys.value = [...selectedRowKeys.value, id]
  } else {
    selectedRowKeys.value = selectedRowKeys.value.filter((k) => k !== id)
  }
}

// 获取任务列表
const fetchTasks = async () => {
  taskLoading.value = true
  try {
    const res = await domainFactoryApi.fetchDataSources()
    taskList.value = res?.pending || res?.items || []
  } catch (e) {
    console.error('fetchTasks failed:', e)
    message.error('加载待处理任务失败')
  } finally {
    taskLoading.value = false
  }
}

// 获取历史记录
const fetchHistory = async () => {
  historyLoading.value = true
  try {
    const params = {
      keyword: searchKeyword.value || undefined
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
      } catch {
        /* skip */
      }
    }
    message.success(`已删除 ${ok} 个任务`)
    selectedRowKeys.value = []
    refresh()
  } catch {
    /* cancelled */
  } finally {
    batchOperating.value = false
  }
}

// 打开任务
const handleOpenTask = (task) => {
  emit('task-open', task)
}

// 删除任务
const handleDeleteTask = async (task) => {
  // 行内 popconfirm 已是唯一确认点，确认后直接删除
  try {
    await domainFactoryApi.deleteDataSource(task.id || task.task_id)
    message.success('删除成功')
    refresh()
  } catch (e) {
    console.error('删除任务失败:', e)
    message.error('删除失败')
  }
}

// 重试任务：FAILED 且熔断时已存段落 → 后端断点续跑（仅补失败段）；无段落 → 重置 UPLOADED 全卷重跑
const handleRetryTask = async (task) => {
  try {
    await domainFactoryApi.retryTask(task.id || task.task_id)
    message.success('已重新提交')
    refresh()
  } catch {
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

// 上传相关
const openUploadModal = async () => {
  uploadFiles.value = []
  uploadFileList.value = []
  selectedReportType.value = ''
  await loadReportTypes()
  uploadModalVisible.value = true
}

const loadReportTypes = async () => {
  try {
    const res = await domainFactoryApi.getContexts()
    const typesByDomain = res?.report_types || {}
    const types = typesByDomain.general || []
    reportTypeOptions.value = types.map((t) => ({ label: t.name, value: t.code }))
  } catch {
    reportTypeOptions.value = []
  }
}

const beforeUpload = (file) => {
  // 文件类型验证
  const isValidType =
    file.type === 'application/pdf' ||
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
  const exists = uploadFiles.value.find((f) => f.name === file.name && f.size === file.size)
  if (exists) {
    message.warning(`文件 "${file.name}" 已存在`)
    return Upload.LIST_IGNORE
  }

  uploadFiles.value.push(file)
  return false
}

const handleFileRemove = (file) => {
  const index = uploadFiles.value.findIndex((f) => f.name === file.name && f.size === file.size)
  if (index > -1) {
    uploadFiles.value.splice(index, 1)
  }
  const listIndex = uploadFileList.value.findIndex(
    (f) => f.name === file.name && f.size === file.size
  )
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

  uploading.value = true
  try {
    for (const file of uploadFiles.value) {
      const formData = new FormData()
      formData.append('file', file.originFileObj || file)
      const rtOption = reportTypeOptions.value.find((o) => o.value === selectedReportType.value)
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
      fetchTasks()
      taskerStore.loadTasks()
      if (hasActiveTasks.value) startAutoRefresh()
    }, 500)
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

onMounted(() => {
  refresh()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})

defineExpose({ refresh })
</script>

<template>
  <div class="ewp data-source-dashboard">
    <!-- 页头（EIA page-head 配方：点阵底纹 + 34px 图标位 + 右侧操作区） -->
    <div class="page-head">
      <div class="ph-icon">
        <Inbox :size="18" />
      </div>
      <div>
        <h2>数据加工</h2>
        <div class="ph-sub">上传报告、跟踪解析状态、为工程报告智能写作创建高质量数据集。</div>
      </div>
      <div class="ph-actions">
        <button class="btn btn-sec" :disabled="taskLoading || historyLoading" @click="refresh">
          <RotateCw :size="14" /> 刷新
        </button>
        <button class="btn btn-pri" @click="openUploadModal">
          <Plus :size="14" /> 上传新报告
        </button>
      </div>
    </div>

    <!-- 待处理任务 -->
    <div class="card task-section">
      <div class="card-hd">
        <h3>待处理任务</h3>
        <span class="pill pill-sm pill-gray">{{ pendingCount }} 项</span>
        <span v-if="hasActiveTasks" class="pill pill-sm pill-main processing-tag">
          <span class="pulse-dot"></span> 处理中
        </span>
        <div class="hd-right">
          <transition name="batch-bar">
            <div v-if="selectedRowKeys.length > 0" class="batch-bar">
              <span class="batch-bar__label">
                已选 <strong>{{ selectedRowKeys.length }}</strong> 项
              </span>
              <button class="btn btn-sm btn-danger" :disabled="batchOperating" @click="handleBatchDelete">
                <Trash2 :size="12" /> 批量删除
              </button>
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
          <span>文档类型</span>
          <span class="col-center">上传时间</span>
          <span class="col-center">状态</span>
          <span class="col-center">AI 置信度</span>
          <span class="col-action">操作</span>
        </div>
        <a-spin v-if="taskLoading" class="list-state" tip="加载中..." />
        <a-empty
          v-else-if="!filteredTasks.length"
          description="暂无待处理任务"
          class="list-empty"
        />
        <template v-for="record in filteredTasks" :key="record.id">
          <div class="file-row" @click="selectedRowKeys = [record.id]">
            <span class="checkbox-cell" @click.stop>
              <a-checkbox
                :checked="selectedRowKeys.includes(record.id)"
                @change="(e) => togglePendingSelect(record.id, e.target.checked)"
              />
            </span>
            <span class="name-cell" :title="record.file_name">
              <FileText :size="16" style="color: var(--main-500); flex-shrink: 0" />
              <span class="entry-name">{{ record.file_name }}</span>
            </span>
            <span>{{
              record.document_type || record.report_type_name || record.report_type_code || '-'
            }}</span>
            <span class="col-center col-time">{{ formatTime(record.uploaded_at) }}</span>
            <span class="col-center">
              <span class="status-dot">
                <span
                  class="dot"
                  :style="dotStyle(record.status)"
                ></span>
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
                  <button class="btn btn-sm btn-pri" @click="handleOpenTask(record)">校验</button>
                </a-tooltip>
                <a-tooltip v-else :title="statusMap[record.status]?.text || '处理中'">
                  <button class="btn btn-sm" disabled>
                    {{ statusMap[record.status]?.text || '处理中' }}
                  </button>
                </a-tooltip>
                <button class="btn btn-sm btn-txt" @click="handleViewMarkdown(record)">
                  查看原文
                </button>
                <button
                  v-if="record.status === 'FAILED'"
                  class="btn btn-sm btn-txt"
                  @click="handleRetryTask(record)"
                >
                  重新提取
                </button>
                <button
                  v-else-if="record.status === 'COMMIT_FAILED' || record.status === 'COMMIT_PARTIAL'"
                  class="btn btn-sm btn-txt"
                  @click="handleReingestTask(record)"
                >
                  重新入库
                </button>
                <a-popconfirm
                  title="确定删除此任务吗？"
                  ok-text="删除"
                  :ok-button-props="{ danger: true }"
                  @confirm="handleDeleteTask(record)"
                >
                  <button class="btn btn-sm btn-txt btn-delete">删除</button>
                </a-popconfirm>
              </div>
            </span>
          </div>
        </template>
      </div>
    </div>

    <!-- 历史记录 -->
    <div class="card task-section task-section--history">
      <div class="card-hd">
        <h3>已入库历史文档</h3>
        <span class="pill pill-sm pill-gray">{{ filteredHistory.length }} 项</span>
        <div class="hd-right">
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
          <span>文档类型</span>
          <span class="col-center">操作人</span>
          <span class="col-center">入库时间</span>
          <span class="col-center">置信度</span>
          <span class="col-action">操作</span>
        </div>
        <a-spin v-if="historyLoading" class="list-state" tip="加载中..." />
        <a-empty
          v-else-if="!filteredHistory.length"
          description="暂无历史数据"
          class="list-empty"
        />
        <template v-for="record in filteredHistory" :key="record.id">
          <div class="file-row no-checkbox" @click="handleViewMarkdown(record)">
            <span class="name-cell" :title="record.file_name">
              <FileText :size="16" style="color: var(--main-500); flex-shrink: 0" />
              <span class="entry-name">{{ record.file_name }}</span>
            </span>
            <span>{{ record.document_type }}</span>
            <span class="col-center">{{ record.reviewer || '-' }}</span>
            <span class="col-center col-time">{{ formatDate(record.committed_at) }}</span>
            <span class="col-center">
              <span v-if="record.ai_confidence">{{ record.ai_confidence }}%</span>
              <span v-else class="col-dash">-</span>
            </span>
            <span class="col-action" @click.stop>
              <div class="action-btns">
                <button class="btn btn-sm btn-txt" @click="handleViewMarkdown(record)">
                  查看原文
                </button>
                <a-popconfirm
                  title="确定删除此记录吗？"
                  ok-text="删除"
                  :ok-button-props="{ danger: true }"
                  @confirm="handleDeleteTask(record)"
                >
                  <button class="btn btn-sm btn-txt btn-delete">删除</button>
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
            <Inbox :size="48" class="upload-icon" />
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
                <!-- PDF 用 FileText（lucide 无官方 PDF 图标） -->
                <FileText
                  v-if="getFileIcon(file.name) === 'pdf'"
                  :size="20"
                  class="file-icon pdf-icon"
                />
                <FileType2
                  v-else-if="getFileIcon(file.name) === 'doc'"
                  :size="20"
                  class="file-icon doc-icon"
                />
                <FileText v-else :size="20" class="file-icon file-icon-default" />
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
                <Trash2 :size="12" />
              </a-button>
            </div>
          </div>
          <div class="file-confirm-message">
            已选择 {{ uploadFiles.length }} 个文件，点击"开始解析"上传
          </div>
        </div>
      </div>
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
          <pre v-if="markdownContent" class="markdown-content expr-block">{{ markdownContent }}</pre>
          <a-empty v-else description="暂无 markdown 数据" />
        </div>
      </a-spin>
    </a-modal>
  </div>
</template>

<style lang="less" scoped>
/* 数据源管理（通用域）：公共配方在 factory-core/factory-ui.less；此处只留本页形状 */
.task-section--history {
  margin-top: 16px;
}

/* 批量操作条（卡片头右侧浮出，EIA 错误色语义） */
.batch-bar {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 4px 12px;
  background: var(--color-error-50);
  border-radius: 6px;
  font-size: 12px;
  color: var(--color-error-700);
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

/* 自绘表格（简单只读列表走配方 CSS 自绘，规范 §6） */
.file-table {
  min-height: 0;
}

.file-row {
  display: grid;
  /* 232px：容纳「校验/失败 + 查看原文 + 重新提取 + 删除」四钮最坏组合（文字钮方案 A） */
  grid-template-columns: 34px minmax(150px, 1fr) 120px 140px 110px 88px 232px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 38px;
  padding: 0 16px;
  border-bottom: 1px solid var(--gray-100);
  font-size: 13px;
  color: var(--color-text);
  text-align: left;

  &:not(.table-head) {
    cursor: pointer;
    transition: background 0.12s;

    &:hover {
      background: var(--gray-50);
    }
  }

  &.no-checkbox {
    grid-template-columns: minmax(150px, 1fr) 140px 130px 150px 88px 140px;
  }
}

.table-head {
  min-height: 34px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-tertiary);
  border-bottom: 1px solid var(--gray-200);
  white-space: nowrap;
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
  color: var(--color-text-tertiary);
}

.col-action {
  justify-self: start;
}

/* 破坏性文字钮：红字 + 错误浅底 hover（方案 A 的删除语义） */
.btn-delete {
  color: var(--color-error-700);

  &:hover {
    background: var(--color-error-50);
  }
}

/* 状态点：EIA dot 配方（6px；光环由 dotStyle 内联注入） */
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

.pulse-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--main-500);
  animation: dsd-pulse 1.5s ease-in-out infinite;
}

@keyframes dsd-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.3;
  }
}

.list-state {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 180px;
  color: var(--color-text-tertiary);
}

.list-empty {
  margin-top: 48px;
  font-size: 13px;
  color: var(--color-text-tertiary);
}

/* 卡片头搜索：AntD 输入罩到 .inp 配方（30px/6px/主色 focus ring） */
.history-search {
  width: 220px;

  :deep(.ant-input-affix-wrapper) {
    height: 30px;
    padding: 0 10px;
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    background: var(--gray-0);
    font-size: 13px;
    transition: border-color 0.15s;

    &:hover {
      border-color: var(--gray-200);
    }

    &:focus,
    &.ant-input-affix-wrapper-focused {
      border-color: var(--main-500);
      box-shadow: 0 0 0 2px var(--main-50);
    }
  }

  :deep(.ant-input-prefix) {
    margin-right: 6px;
    color: var(--color-text-tertiary);
  }

  :deep(.ant-input) {
    background: transparent;
    font-size: 13px;
  }
}

.search-icon {
  color: var(--color-text-tertiary);
}

/* ── 上传弹窗 ── */
.upload-modal-content {
  .upload-instruction {
    margin-bottom: 16px;

    .instruction-text {
      margin: 0;
      font-size: 12px;
      color: var(--color-text-tertiary);
    }
  }

  .form-selectors {
    margin-bottom: 16px;
  }

  .custom-upload-dragger {
    :deep(.ant-upload-drag) {
      background: var(--gray-50);
      border: 1px dashed var(--gray-200);
      border-radius: 8px;
      padding: 32px 20px;
      transition:
        border-color 0.15s,
        background 0.15s;

      &:hover {
        border-color: var(--main-400);
        background: var(--main-10, var(--main-50));
      }
    }

    .upload-icon-wrapper {
      display: flex;
      justify-content: center;
      margin-bottom: 12px;

      .upload-icon {
        color: var(--main-500);
      }
    }

    .file-icon {
      color: var(--color-text-tertiary);
    }

    :deep(.ant-upload-text) {
      font-size: 14px;
      font-weight: 500;
      color: var(--color-text);
    }

    :deep(.ant-upload-hint) {
      font-size: 12px;
      color: var(--color-text-tertiary);
    }
  }

  .file-list {
    margin-top: 12px;

    .file-items {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-height: 200px;
      overflow-y: auto;
      padding: 10px;
      background: var(--gray-50);
      border: 1px solid var(--gray-150);
      border-radius: 8px;
    }

    .file-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      background: var(--gray-0);
      border: 1px solid var(--gray-150);
      border-radius: 6px;

      .file-status-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--color-success-500);
        flex: none;
      }

      .file-name {
        flex: 1;
        min-width: 0;
        font-size: 13px;
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .file-size {
        font-size: 12px;
        color: var(--color-text-tertiary);
        font-variant-numeric: tabular-nums;
        flex: none;
      }
    }

    .file-confirm-message {
      margin-top: 10px;
      font-size: 12px;
      color: var(--color-text-tertiary);
      text-align: center;
    }
  }
}

/* ── Markdown 查看暗块（expr-block 同款钉死深底，双主题一致） ── */
.markdown-viewer {
  .markdown-content {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 60vh;
    overflow-y: auto;
  }
}
</style>

<style lang="less" src="../factory-core/factory-ui.less"></style>
