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
  PlusOutlined
} from '@ant-design/icons-vue'
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
const selectedDocumentType = ref('通用')
const activeTab = ref('pending')

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

// 文档类型选项
const documentTypeOptions = [
  { label: '通用', value: '通用' },
  { label: '环境影响评价报告', value: '环境影响评价报告' },
  { label: '可行性研究报告', value: '可行性研究报告' },
  { label: '初步设计', value: '初步设计' }
]

// 状态映射
const statusMap = {
  UPLOADED: { color: 'var(--gray-400)', text: '已上传' },
  PARSING: { color: '#1677ff', text: '解析中' },
  EXTRACTING: { color: '#722ed1', text: '提取中' },
  GENERALIZING: { color: '#722ed1', text: '泛化中' },
  WAITING_REVIEW: { color: '#faad14', text: '待校验' },
  COMMITTED: { color: '#52c41a', text: '已入库' },
  FAILED: { color: '#ff4d4f', text: '失败' }
}

// 计算属性
const pendingCount = computed(() => taskList.value.length)

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

const filteredTasks = computed(() => {
  if (!searchKeyword.value) return taskList.value
  const kw = searchKeyword.value.toLowerCase()
  return taskList.value.filter(t =>
    t.file_name?.toLowerCase().includes(kw) ||
    t.domain?.toLowerCase().includes(kw)
  )
})

const filteredHistory = computed(() => {
  if (!searchKeyword.value) return historyList.value
  const kw = searchKeyword.value.toLowerCase()
  return historyList.value.filter(t =>
    t.file_name?.toLowerCase().includes(kw)
  )
})

// 获取任务列表
const fetchTasks = async () => {
  taskLoading.value = true
  try {
    const params = props.selectedDomain && props.selectedDomain !== '__all__'
      ? { domain: props.selectedDomain } : {}
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
const fetchHistory = async () => {
  historyLoading.value = true
  try {
    const params = {
      keyword: searchKeyword.value || undefined
    }
    if (props.selectedDomain && props.selectedDomain !== '__all__') {
      params.domain = props.selectedDomain
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

// 重试任务
const handleRetryTask = async (task) => {
  try {
    await domainFactoryApi.retryTask(task.id || task.task_id)
    message.success('已重新提交')
    refresh()
  } catch (e) {
    message.error('重试失败')
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
const openUploadModal = () => {
  uploadFiles.value = []
  uploadFileList.value = []
  selectedDocumentType.value = '通用'
  uploadModalVisible.value = true
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
  if (!props.selectedDomain || props.selectedDomain === '__all__') {
    message.warning('请先选择一个领域')
    return
  }

  uploading.value = true
  try {
    for (const file of uploadFiles.value) {
      const formData = new FormData()
      formData.append('file', file.originFileObj || file)
      formData.append('domain', props.selectedDomain)
      formData.append('document_type', selectedDocumentType.value)
      const result = await domainFactoryApi.uploadSources(formData)
      console.log('上传成功，任务ID:', result?.task_id)
    }
    message.success('上传成功，任务已提交处理')
    uploadModalVisible.value = false
    uploadFiles.value = []
    uploadFileList.value = []
    selectedDocumentType.value = '通用'

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
    return dayjs(isoString).format('HH:mm:ss')
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

// 监听领域变化
watch(() => props.selectedDomain, () => {
  if (props.selectedDomain) {
    refresh()
  }
}, { immediate: true })

onMounted(() => {
  refresh()
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
            :value="props.selectedDomain"
            button-style="solid"
            @change="e => emit('update:domain', e.target.value)"
          >
            <a-radio-button
              v-for="domain in domainOptions"
              :key="domain.value"
              :value="domain.value"
            >
              {{ domain.label }}
            </a-radio-button>
          </a-radio-group>
          <a-button type="link" @click="showCreateDomainModal">
            <PlusOutlined /> 新建领域
          </a-button>
        </div>
      </div>
    </div>

    <!-- 待处理任务 -->
    <div class="task-section">
      <a-card :title="`待处理任务 (${pendingCount})`" :loading="taskLoading">
        <template #extra>
          <a-tag color="blue">实时更新</a-tag>
        </template>
        <a-table
          :data-source="filteredTasks"
          :columns="[
            { title: '文件名', dataIndex: 'file_name', key: 'file_name' },
            { title: '所属领域', dataIndex: 'domain_label', key: 'domain_label', width: 140 },
            { title: '文档类型', dataIndex: 'document_type', key: 'document_type', width: 140 },
            { title: '上传时间', dataIndex: 'uploaded_at', key: 'uploaded_at', width: 160 },
            { title: '状态', dataIndex: 'status', key: 'status', width: 120 },
            { title: 'AI 置信度', dataIndex: 'ai_confidence', key: 'ai_confidence', width: 120 },
            { title: '操作', key: 'action', width: 180 }
          ]"
          row-key="id"
          :pagination="false"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'uploaded_at'">
              {{ formatTime(record.uploaded_at) }}
            </template>
            <template v-else-if="column.dataIndex === 'status'">
              <div class="status-dot">
                <span class="dot" :style="{ backgroundColor: statusMap[record.status]?.color || '#999' }"></span>
                {{ statusMap[record.status]?.text || record.status }}
              </div>
            </template>
            <template v-else-if="column.dataIndex === 'ai_confidence'">
              <span v-if="record.ai_confidence">{{ record.ai_confidence }}%</span>
              <a-tag v-else color="default">-</a-tag>
            </template>
            <template v-else-if="column.key === 'action'">
              <a-space>
                <a-button
                  v-if="record.status === 'WAITING_REVIEW'"
                  type="primary"
                  size="small"
                  @click="handleOpenTask(record)"
                >
                  校验
                </a-button>
                <a-button v-else size="small" disabled>
                  {{ statusMap[record.status]?.text || '处理中' }}
                </a-button>
                <a-button size="small" @click="handleViewMarkdown(record)">
                  查看
                </a-button>
                <a-button
                  v-if="record.status === 'FAILED'"
                  size="small"
                  @click="handleRetryTask(record)"
                >
                  重试
                </a-button>
                <a-popconfirm
                  title="确定删除此任务吗？"
                  @confirm="handleDeleteTask(record)"
                >
                  <a-button size="small" danger type="text">
                    <DeleteOutlined />
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-card>
    </div>

    <!-- 历史记录 -->
    <a-card class="history-card" title="已入库历史数据" :loading="historyLoading">
      <template #extra>
        <a-input-search
          v-model:value="searchKeyword"
          placeholder="搜索文件名..."
          style="width: 220px"
          allow-clear
          @search="fetchHistory"
        />
      </template>
      <a-table
        :data-source="filteredHistory"
        :columns="[
          { title: '文件名', dataIndex: 'file_name', key: 'file_name' },
          { title: '所属领域', dataIndex: 'domain_label', key: 'domain_label', width: 140 },
          { title: '文档类型', dataIndex: 'document_type', key: 'document_type', width: 140 },
          { title: '操作人', dataIndex: 'reviewer', key: 'reviewer', width: 120 },
          { title: '入库时间', dataIndex: 'committed_at', key: 'committed_at', width: 160 },
          { title: '置信度', dataIndex: 'ai_confidence', key: 'ai_confidence', width: 120 },
          { title: '操作', key: 'action', width: 80 }
        ]"
        row-key="id"
        :pagination="{ pageSize: 10 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'committed_at'">
            {{ formatDate(record.committed_at) }}
          </template>
          <template v-else-if="column.dataIndex === 'ai_confidence'">
            <a-progress
              v-if="record.ai_confidence"
              :percent="record.ai_confidence"
              size="small"
              :stroke-color="record.ai_confidence > 80 ? '#52c41a' : '#faad14'"
            />
            <a-tag v-else color="default">-</a-tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button size="small" @click="handleViewMarkdown(record)">查看</a-button>
              <a-popconfirm
                title="确定删除此记录吗？"
                @confirm="handleDeleteTask(record)"
              >
                <a-button size="small" danger type="text">
                  <DeleteOutlined />
                </a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

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
          <a-form-item label="文档类型" required>
            <a-select
              v-model:value="selectedDocumentType"
              :options="documentTypeOptions"
              placeholder="选择文档类型"
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
  border-radius: 12px 12px 0 0;
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
    }
  }
}

.task-section {
  background: #fff;

  :deep(.ant-card-body) {
    padding: 0;
  }
}

.status-dot {
  display: flex;
  align-items: center;
  gap: 8px;

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
}

.history-card {
  background: #fff;
  margin-bottom: 24px;
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
</style>
