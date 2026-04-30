<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import DataSourceDashboard from '@/components/domain-factory/DataSourceDashboard.vue'
import EtlWorkbench from '@/components/domain-factory/EtlWorkbench.vue'
import SchemaConfigurator from '@/components/domain-factory/SchemaConfigurator.vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useTaskerStore } from '@/stores/tasker'

const route = useRoute()
const router = useRouter()
const taskerStore = useTaskerStore()

const activeTab = ref(route.query.tab || 'data')
const domains = ref([])
const selectedDomain = ref('')
const loadingDomains = ref(false)
const currentTask = ref(null)
const dashboardRef = ref(null)

const tabMenu = [
  { key: 'data', title: '数据源管理', subtitle: '上传入口与任务队列' },
  { key: 'workbench', title: 'ETL 清洗工作台', subtitle: '双屏校验 · 阶段入库' },
  { key: 'schema', title: '领域 Schema 配置', subtitle: '变量字典 · 章节树' }
]

// 高级配置菜单
const advancedMenu = [
  { key: 'section-routing', title: '章节路由配置', subtitle: '章节目录 · Skill 路由', path: '/domain-factory/section-routing' },
  { key: 'prompt-config', title: 'Prompt 模板管理', subtitle: '文档解析 · 模板泛化提示词', path: '/domain-factory/prompt-config' },
  { key: 'standard-code', title: 'StandardCode 管理', subtitle: '标准代码 · 映射表管理', path: '/domain-factory/standard-code' }
]

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
    domains.value = [
      { id: 'coal', name: '煤炭采掘', code: 'coal' },
      { id: 'chem', name: '石油化工', code: 'chem' }
    ]
    if (!selectedDomain.value) {
      selectedDomain.value = domains.value[0].code
    }
  } finally {
    loadingDomains.value = false
  }
}

const handleDomainChange = (domain) => {
  selectedDomain.value = domain
}

const handleTaskOpen = (task) => {
  currentTask.value = task
  activeTab.value = 'workbench'
}

const handleTaskCompleted = () => {
  message.success('任务处理完成')
  currentTask.value = null
  activeTab.value = 'data'
  refreshDashboard()
  // 同步任务中心
  taskerStore.loadTasks()
}

const handleTaskUpdated = () => {
  refreshDashboard()
  // 任务状态更新后同步到任务中心
  if (currentTask.value?.id) {
    domainFactoryApi.syncTaskToTaskCenter(currentTask.value.id).catch(err => {
      console.error('同步任务中心失败:', err)
    })
  }
}

const handleTabChange = (key) => {
  activeTab.value = key
}

const handleSideNavClick = (key) => {
  activeTab.value = key
  document.querySelector('.factory-main')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// 跳转到高级配置页面
const goToAdvancedConfig = (item) => {
  router.push(item.path)
}

const refreshDomains = () => {
  fetchDomains()
}

const refreshDashboard = () => {
  dashboardRef.value?.refresh?.()
}

onMounted(() => {
  fetchDomains()
})

watch(() => route.query.tab, (tab) => {
  if (tab && ['data', 'workbench', 'schema'].includes(tab)) {
    activeTab.value = tab
  }
})

watch(activeTab, (tab) => {
  router.replace({ query: { ...route.query, tab } })
})
</script>

<template>
  <div class="domain-factory-view">
    <div class="factory-layout">
      <!-- Left Sidebar -->
      <div class="left-sidebar">
        <!-- 主导航 -->
        <aside class="side-nav">
          <h4>知识工厂</h4>
          <p class="side-desc">从上传到入库的全链路控制台</p>
          <div class="side-menu">
            <button
              v-for="item in tabMenu"
              :key="item.key"
              class="side-btn"
              :class="{ active: activeTab === item.key }"
              @click="handleSideNavClick(item.key)"
            >
              <span class="side-title">{{ item.title }}</span>
              <span class="side-subtitle">{{ item.subtitle }}</span>
            </button>
          </div>
        </aside>

        <!-- 高级配置导航 -->
        <aside class="schema-config-nav">
          <h4>高级配置</h4>
          <button
            v-for="item in advancedMenu"
            :key="item.key"
            class="side-btn secondary"
            @click="goToAdvancedConfig(item)"
          >
            <span class="side-title">{{ item.title }}</span>
            <span class="side-subtitle">{{ item.subtitle }}</span>
          </button>
        </aside>
      </div>

      <!-- Main Content -->
      <div class="factory-main">
        <div class="hero">
          <div>
            <p class="badge">Domain Knowledge Factory</p>
            <h1>人机协同的领域知识工厂</h1>
            <p class="desc">
              AI 负责粗加工，专家完成精加工，最终将高质量数据入库 LightRAG / SQL /
              图谱，确保「入库即精品」。
            </p>
          </div>
          <div class="hero-actions">
            <a-button type="primary" size="large" @click="activeTab = 'data'">上传新报告</a-button>
            <a-button size="large" @click="activeTab = 'schema'">配置领域 Schema</a-button>
          </div>
        </div>

        <a-tabs
          v-model:activeKey="activeTab"
          size="large"
          @change="handleTabChange"
          class="factory-tabs"
        >
          <a-tab-pane key="data" tab="数据源管理 · 上传与任务队列">
            <DataSourceDashboard
              ref="dashboardRef"
              :domains="domains"
              :selected-domain="selectedDomain"
              :loading-domains="loadingDomains"
              @update:domain="handleDomainChange"
              @task-open="handleTaskOpen"
              @domains-refreshed="refreshDomains"
            />
          </a-tab-pane>
          <a-tab-pane key="workbench" tab="ETL 清洗工作台 · 双屏校验">
            <EtlWorkbench
              :task="currentTask"
              @task-completed="handleTaskCompleted"
              @task-updated="handleTaskUpdated"
            />
          </a-tab-pane>
          <a-tab-pane key="schema" tab="领域 Schema 配置 · 数据字典">
            <SchemaConfigurator
              :domains="domains"
              :selected-domain="selectedDomain"
              @update:domain="handleDomainChange"
            />
          </a-tab-pane>
        </a-tabs>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.domain-factory-view {
  padding: 32px 32px 80px;
  min-height: 100%;
  background: linear-gradient(180deg, #f5f7fb 0%, #ffffff 120%);

  .factory-layout {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 24px;
  }

  .left-sidebar {
    display: flex;
    flex-direction: column;
    gap: 16px;
    position: sticky;
    height: fit-content;
  }

  .side-nav,
  .schema-config-nav {
    background: #fff;
    border: 1px solid var(--gray-150);
    border-radius: 12px;
    padding: 24px;
    height: fit-content;

    h4 {
      margin: 0;
      font-size: 18px;
    }
  }

  .side-nav {
    .side-desc {
      margin: 4px 0 16px;
      color: var(--gray-500);
      font-size: 13px;
    }

    .side-menu {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
  }

  .schema-config-nav {
    h4 {
      margin: 0 0 12px 0;
    }

    .side-btn + .side-btn {
      margin-top: 8px;
    }
  }

  .side-btn {
    border: 1px solid var(--gray-150);
    background: #fff;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: left;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    transition: all 0.2s ease;
    width: 100%;

    &.active {
      border-color: var(--main-color);
      background: rgba(22, 119, 255, 0.08);
    }

    &:hover {
      border-color: var(--main-200);
    }

    &.secondary {
      border-style: dashed;
      border-color: var(--gray-200);
      background: #fafafa;

      &:hover {
        border-color: var(--main-color);
        background: #f5f7ff;
      }
    }

    .side-title {
      font-weight: 600;
      font-size: 13px;
    }

    .side-subtitle {
      font-size: 11px;
      color: var(--gray-500);
      margin-top: 2px;
    }
  }

  .factory-main {
    min-height: 100%;
  }

  .hero {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    padding: 32px;
    border-radius: 20px;
    background:
      radial-gradient(circle at top right, rgba(22, 119, 255, 0.12), transparent 40%),
      #fff;
    border: 1px solid var(--gray-150);
    margin-bottom: 24px;

    .badge {
      font-size: 13px;
      font-weight: 600;
      color: var(--main-color);
      margin-bottom: 8px;
    }

    h1 {
      margin: 0;
      font-size: 32px;
      font-weight: 700;
    }

    .desc {
      margin-top: 8px;
      color: var(--gray-600);
      max-width: 640px;
    }

    .hero-actions {
      display: flex;
      gap: 12px;
    }
  }

  .factory-tabs {
    background: transparent;

    :deep(.ant-tabs-nav) {
      margin: 0 0 16px;
      padding: 0 12px;
    }

    :deep(.ant-tabs-content) {
      background: transparent;
    }
  }

  @media (max-width: 1080px) {
    .factory-layout {
      grid-template-columns: 1fr;
    }

    .left-sidebar {
      position: static;
    }
  }
}
</style>
