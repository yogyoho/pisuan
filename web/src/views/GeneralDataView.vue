<!-- [pisuan-custom] 通用域「数据源管理」屏：原首页 data tab 迁入；去领域化后无领域维度 -->
<template>
  <DataSourceDashboard @task-open="handleTaskOpen" />
</template>

<script setup>
import { useRouter } from 'vue-router'
import DataSourceDashboard from '@/components/domain-factory/DataSourceDashboard.vue'

const router = useRouter()

// 任务下钻改为跨路由：query.task 传 id，GeneralWorkbenchView 据此构造 task 交给 EtlWorkbench
const handleTaskOpen = (task) => {
  router.push({ path: '/domain-factory/general/workbench', query: { task: task.id } })
}
</script>
