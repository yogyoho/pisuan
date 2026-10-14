<!-- [pisuan-custom] 通用域「数据源管理」屏：原首页 data tab 迁入；领域选择状态由本容器持有 -->
<template>
  <DataSourceDashboard
    :domains="domains"
    :selected-domain="selectedDomain"
    :loading-domains="loadingDomains"
    @update:domain="handleDomainChange"
    @task-open="handleTaskOpen"
    @domains-refreshed="fetchDomains"
  />
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import DataSourceDashboard from '@/components/domain-factory/DataSourceDashboard.vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

const router = useRouter()

const domains = ref([])
const selectedDomain = ref('')
const loadingDomains = ref(false)

const fetchDomains = async () => {
  loadingDomains.value = true
  try {
    const res = await domainFactoryApi.getDomains()
    let domainsList = []
    if (Array.isArray(res)) {
      domainsList = res
    } else if (res?.items && Array.isArray(res.items)) {
      domainsList = res.items
    }
    domains.value = domainsList
    if (!selectedDomain.value && domains.value.length) {
      selectedDomain.value = domains.value[0].code || domains.value[0].id || domains.value[0].name
    }
  } catch (error) {
    console.warn(error)
    message.error('加载领域列表失败，使用默认配置')
    domains.value = []
    selectedDomain.value = ''
  } finally {
    loadingDomains.value = false
  }
}

const handleDomainChange = (domain) => {
  selectedDomain.value = domain
}

// 任务下钻改为跨路由：query.task 传 id，GeneralWorkbenchView 据此构造 task 交给 EtlWorkbench
const handleTaskOpen = (task) => {
  router.push({ path: '/domain-factory/general/workbench', query: { task: task.id } })
}

onMounted(fetchDomains)
</script>
