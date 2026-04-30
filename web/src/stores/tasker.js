import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { taskerApi } from '@/apis/tasker'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useUserStore } from '@/stores/user'
import { parseToShanghai } from '@/utils/time'

const ACTIVE_STATUSES = new Set(['pending', 'running', 'queued'])
const FAILED_STATUSES = new Set(['failed', 'cancelled'])

const createDefaultSummary = () => ({
  total: 0,
  filtered_total: 0,
  status_counts: {},
  type_counts: {}
})

const toTask = (raw = {}) => ({
  id: raw.id,
  name: raw.name || '后台任务',
  type: raw.type || 'general',
  status: raw.status || 'pending',
  progress: raw.progress ?? 0,
  message: raw.message || '',
  created_at: raw.created_at,
  updated_at: raw.updated_at,
  started_at: raw.started_at,
  completed_at: raw.completed_at,
  payload: raw.payload || {},
  result: raw.result,
  error: raw.error,
  cancel_requested: raw.cancel_requested || false
})

// 任务类型标签映射
const TASK_TYPE_LABELS = {
  general: '后台任务',
  manual: '手动任务',
  knowledge_ingest: '知识库导入',
  knowledge_rechunks: '文档重新分块',
  graph_task: '图谱处理',
  agent_job: '智能体任务',
  domain_factory: '知识工厂报告解析',
}

// 知识工厂状态到任务中心状态的映射
const DOMAIN_FACTORY_STATUS_MAP = {
  'UPLOADED': { status: 'running', progress: 5, message: '文件已上传，等待处理...' },
  'PARSING': { status: 'running', progress: 25, message: '正在解析文档...' },
  'EXTRACTING': { status: 'running', progress: 55, message: '正在提取信息...' },
  'GENERALIZING': { status: 'running', progress: 80, message: '正在生成槽位模板...' },
  'WAITING_REVIEW': { status: 'running', progress: 95, message: '信息提取完成，等待人工审核...' },
  'COMMITTED': { status: 'success', progress: 100, message: '报告已入库完成' },
  'FAILED': { status: 'failed', progress: 100, message: '执行失败' },
}

export const useTaskerStore = defineStore('tasker', () => {
  const userStore = useUserStore()
  const tasks = ref([])
  const loading = ref(false)
  const lastError = ref(null)
  const isDrawerOpen = ref(false)
  const summary = ref(createDefaultSummary())
  let pollingTimer = null

  const sortedTasks = computed(() => {
    return [...tasks.value].sort((a, b) => {
      const timeA = parseToShanghai(a.created_at)
      const timeB = parseToShanghai(b.created_at)
      if (!timeA && !timeB) return 0
      if (!timeA) return 1
      if (!timeB) return -1
      return timeB.valueOf() - timeA.valueOf()
    })
  })

  const statusCounts = computed(() => summary.value?.status_counts || {})

  const activeCount = computed(() =>
    Array.from(ACTIVE_STATUSES).reduce(
      (count, status) => count + (statusCounts.value?.[status] || 0),
      0
    )
  )
  const failedCount = computed(() =>
    Array.from(FAILED_STATUSES).reduce(
      (count, status) => count + (statusCounts.value?.[status] || 0),
      0
    )
  )
  const successCount = computed(() => statusCounts.value?.success || 0)
  const totalCount = computed(() => summary.value?.total || 0)

  // 是否存在需要持续轮询的任务：summary 统计或本地乐观登记的活跃任务
  const hasActiveTasks = computed(
    () => activeCount.value > 0 || tasks.value.some((task) => ACTIVE_STATUSES.has(task.status))
  )

  function upsertTask(rawTask) {
    if (!rawTask || !rawTask.id) return
    const task = toTask(rawTask)
    const index = tasks.value.findIndex((item) => item.id === task.id)
    if (index >= 0) {
      tasks.value.splice(index, 1, { ...tasks.value[index], ...task })
    } else {
      tasks.value.unshift(task)
    }
  }

  async function loadTasks(params = {}) {
    if (!userStore.isAdmin) {
      tasks.value = []
      summary.value = createDefaultSummary()
      lastError.value = null
      syncPolling()
      return
    }

    loading.value = true
    lastError.value = null
    try {
      // 获取通用任务
      const [response, dfResponse] = await Promise.all([
        taskerApi.fetchTasks(params),
        domainFactoryApi.getTasksForTaskCenter(params).catch(err => {
          console.warn('获取知识工厂任务失败:', err)
          return { tasks: [] }
        })
      ])

      const taskList = response?.tasks || []
      const dfTasks = dfResponse?.tasks || []

      // 合并知识工厂任务（使用 domain_factory 类型标记）
      const mergedTasks = [...taskList, ...dfTasks]

      // 更新 summary
      const statusCounter = {}
      const typeCounter = {}
      for (const task of mergedTasks) {
        statusCounter[task.status] = (statusCounter[task.status] || 0) + 1
        typeCounter[task.type] = (typeCounter[task.type] || 0) + 1
      }

      summary.value = {
        total: mergedTasks.length,
        filtered_total: mergedTasks.length,
        status_counts: statusCounter,
        type_counts: typeCounter,
      }

      // 合并去重：通用任务和知识工厂任务合并，如果有相同 ID（通过 payload.task_id 判断）则更新
      const taskMap = new Map()
      for (const t of taskList) {
        taskMap.set(t.id, toTask(t))
      }
      // 知识工厂任务使用 df_ 前缀的 ID，但关联到原始 task_id
      for (const t of dfTasks) {
        const existingTask = taskMap.get(t.id)
        if (existingTask) {
          // 更新现有任务的状态
          const mapped = DOMAIN_FACTORY_STATUS_MAP[t.status] || {}
          taskMap.set(t.id, { ...existingTask, ...t, ...mapped })
        } else {
          taskMap.set(t.id, toTask(t))
        }
      }

      tasks.value = Array.from(taskMap.values())
    } catch (error) {
      console.error('加载任务列表失败', error)
      lastError.value = error
      summary.value = createDefaultSummary()
    } finally {
      loading.value = false
      syncPolling()
    }
  }

  async function refreshTask(taskId) {
    if (!taskId) return
    try {
      const response = await taskerApi.fetchTaskDetail(taskId)
      if (response?.task) {
        upsertTask(response.task)
      }
    } catch (error) {
      console.error(`刷新任务 ${taskId} 详情失败`, error)
      lastError.value = error
    }
  }

  async function cancelTask(taskId) {
    if (!taskId) return
    try {
      await taskerApi.cancelTask(taskId)
      message.success('取消请求已提交')
      await refreshTask(taskId)
    } catch (error) {
      console.error(`取消任务 ${taskId} 失败`, error)
      message.error(error?.message || '取消任务失败')
    }
  }

  async function deleteTask(taskId) {
    if (!taskId) return
    try {
      await taskerApi.deleteTask(taskId)
      message.success('删除任务成功')
      // 从本地列表中移除
      const index = tasks.value.findIndex((item) => item.id === taskId)
      if (index >= 0) {
        tasks.value.splice(index, 1)
      }
    } catch (error) {
      console.error(`删除任务 ${taskId} 失败`, error)
      message.error(error?.message || '删除任务失败')
    }
  }

  function registerQueuedTask({ task_id, name, task_type, message: msg, payload } = {}) {
    if (!task_id) return
    const now = new Date().toISOString()
    upsertTask({
      id: task_id,
      name: name || '后台任务',
      type: task_type || 'manual',
      status: 'queued',
      progress: 0,
      message: msg || '任务已排队',
      created_at: now,
      updated_at: now,
      payload: payload || {}
    })
    syncPolling()
  }

  function openDrawer() {
    isDrawerOpen.value = true
    syncPolling()
  }

  function closeDrawer() {
    isDrawerOpen.value = false
    syncPolling()
  }

  function startPolling(interval = 5000) {
    if (pollingTimer) return
    pollingTimer = setInterval(() => {
      loadTasks()
    }, interval)
  }

  function stopPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
  }

  // 轮询所有权收敛到 store：抽屉打开或存在活跃任务时持续轮询，否则停止，
  // 修复抽屉关闭后任务角标（activeCount）不再更新的问题。
  function syncPolling() {
    if (userStore.isAdmin && (isDrawerOpen.value || hasActiveTasks.value)) {
      startPolling()
    } else {
      stopPolling()
    }
  }

  function reset() {
    stopPolling()
    tasks.value = []
    lastError.value = null
    isDrawerOpen.value = false
    summary.value = createDefaultSummary()
  }

  return {
    isDrawerOpen,
    tasks,
    sortedTasks,
    totalCount,
    successCount,
    failedCount,
    loading,
    lastError,
    activeCount,
    loadTasks,
    refreshTask,
    cancelTask,
    deleteTask,
    registerQueuedTask,
    reset,
    openDrawer,
    closeDrawer
  }
})
