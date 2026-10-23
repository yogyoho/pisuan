<!-- [pisuan-custom] 通用域「ETL 清洗工作台」屏：原首页 workbench tab 迁入；支持 ?task=<id> 跨路由下钻 -->
<template>
  <EtlWorkbench
    :task="task"
    @task-completed="handleTaskCompleted"
    @task-updated="handleTaskUpdated"
    @navigate-to-data-sources="router.push('/domain-factory/general/data-sources')"
  />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import EtlWorkbench from '@/components/domain-factory/EtlWorkbench.vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useTaskerStore } from '@/stores/tasker'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const taskerStore = useTaskerStore()
const userStore = useUserStore()

// 只传 id：EtlWorkbench 内部按 task.id 调 fetchTaskDetail 补全详情
const task = computed(() => (route.query.task ? { id: route.query.task } : null))

const handleTaskCompleted = () => {
  message.success('任务处理完成')
  taskerStore.loadTasks()
  router.push('/domain-factory/general/data-sources')
}

const handleTaskUpdated = () => {
  if (userStore.isAdmin && task.value?.id) {
    domainFactoryApi.syncTaskToTaskCenter(task.value.id).catch((err) => {
      console.error('同步任务中心失败:', err)
    })
  }
}
</script>
