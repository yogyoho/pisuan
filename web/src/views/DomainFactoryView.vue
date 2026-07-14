<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownOutlined, UpOutlined, ExperimentOutlined, ThunderboltOutlined, CloudUploadOutlined, RobotOutlined, AuditOutlined, DatabaseOutlined, RightOutlined } from '@ant-design/icons-vue'
import { Database, Layers, Zap } from 'lucide-vue-next'
import DataSourceDashboard from '@/components/domain-factory/DataSourceDashboard.vue'
import EtlWorkbench from '@/components/domain-factory/EtlWorkbench.vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useTaskerStore } from '@/stores/tasker'

const route = useRoute()
const router = useRouter()
const taskerStore = useTaskerStore()

const activeTab = ref('data')
const domains = ref([])
const selectedDomain = ref('')
const loadingDomains = ref(false)
const currentTask = ref(null)
const dashboardRef = ref(null)

const heroCollapsed = ref(localStorage.getItem('df_hero_collapsed') === 'true')
const globalStats = ref({ committed_tasks: 0, entity_count: 0, learned_templates: 0 })

const toggleHero = () => {
  heroCollapsed.value = !heroCollapsed.value
  localStorage.setItem('df_hero_collapsed', String(heroCollapsed.value))
}

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

const handleTaskOpen = (task) => {
  currentTask.value = task
  activeTab.value = 'workbench'
}

const handleTaskCompleted = () => {
  message.success('任务处理完成')
  currentTask.value = null
  activeTab.value = 'data'
  refreshDashboard()
  taskerStore.loadTasks()
}

const handleTaskUpdated = () => {
  refreshDashboard()
  if (currentTask.value?.id) {
    domainFactoryApi.syncTaskToTaskCenter(currentTask.value.id).catch(err => {
      console.error('同步任务中心失败:', err)
    })
  }
}

const handleTabChange = (key) => {
  activeTab.value = key
}

const refreshDomains = () => {
  fetchDomains()
}

const refreshDashboard = () => {
  dashboardRef.value?.refresh?.()
}

const fetchStats = async () => {
  try {
    const res = await domainFactoryApi.getContexts()
    if (res?.stats) globalStats.value = res.stats
  } catch (e) {
    // 静默失败，不影响主页面
  }
}

onMounted(() => {
  fetchDomains()
  fetchStats()
})

watch(() => route.query.tab, (tab) => {
  if (tab && ['data', 'workbench'].includes(tab)) {
    activeTab.value = tab
    router.replace({ query: { ...route.query, tab: undefined } })
  }
})
</script>

<template>
  <div class="domain-factory-view">
    <div class="factory-main">
      <!-- 可折叠 Hero 区 -->
      <div :class="['hero', { collapsed: heroCollapsed }]">
        <transition name="hero-expand">
          <div v-if="!heroCollapsed" class="hero-content">
            <div class="hero-text">
              <div class="badge">
                <ExperimentOutlined style="margin-right: 4px;" />Domain Knowledge Factory
              </div>
              <h1>人机协同的领域知识工厂</h1>
              <p class="desc">
                AI 负责粗加工，专家完成精加工，最终将高质量数据入库 LightRAG / SQL /
                图谱，确保「入库即精品」。
              </p>
            </div>
            <div class="hero-illustration">
              <div class="pipeline-visual">
                <div class="pipeline-node">
                  <div class="node-icon-wrap upload"><CloudUploadOutlined /></div>
                  <div class="node-body">
                    <span class="node-title">上传</span>
                    <span class="node-desc">报告文档</span>
                  </div>
                </div>
                <div class="pipeline-arrow"><RightOutlined /></div>
                <div class="pipeline-node accent">
                  <div class="node-icon-wrap ai"><RobotOutlined /></div>
                  <div class="node-body">
                    <span class="node-title">AI 提取</span>
                    <span class="node-desc">智能泛化</span>
                  </div>
                </div>
                <div class="pipeline-arrow"><RightOutlined /></div>
                <div class="pipeline-node">
                  <div class="node-icon-wrap review"><AuditOutlined /></div>
                  <div class="node-body">
                    <span class="node-title">专家审核</span>
                    <span class="node-desc">精校数据</span>
                  </div>
                </div>
                <div class="pipeline-arrow"><RightOutlined /></div>
                <div class="pipeline-node success">
                  <div class="node-icon-wrap store"><DatabaseOutlined /></div>
                  <div class="node-body">
                    <span class="node-title">入库</span>
                    <span class="node-desc">知识精品</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </transition>
        <div class="hero-bar">
          <div class="hero-stats">
            <div class="hero-stat-card">
              <Database :size="16" />
              <div class="hero-stat-inline">
                <strong>{{ globalStats.committed_tasks }}</strong>
                <span>已入库</span>
              </div>
            </div>
            <div class="hero-stat-card">
              <Layers :size="16" />
              <div class="hero-stat-inline">
                <strong>{{ globalStats.entity_count }}</strong>
                <span>实体</span>
              </div>
            </div>
            <div class="hero-stat-card">
              <Zap :size="16" />
              <div class="hero-stat-inline">
                <strong>{{ globalStats.learned_templates }}</strong>
                <span>学习模板</span>
              </div>
            </div>
          </div>
          <span class="hero-toggle" @click="toggleHero">
            <component :is="heroCollapsed ? DownOutlined : UpOutlined" />
            {{ heroCollapsed ? '展开简介' : '收起' }}
          </span>
          <div class="hero-actions">
            <a-button size="small" class="hero-nav-btn" @click="router.push('/domain-factory/prompt-config')">
              <ThunderboltOutlined /> Prompt 管理
            </a-button>
            <a-button size="small" class="hero-nav-btn" @click="router.push('/domain-factory/entity-builder')">
              实体构建器
            </a-button>
          </div>
        </div>
      </div>

      <div class="factory-tabs-wrapper">
        <a-tabs
          v-model:activeKey="activeTab"
          size="large"
          @change="handleTabChange"
          class="factory-tabs"
        >
          <a-tab-pane key="data" tab="数据源管理">
            <template #tab>
              <span class="tab-label">
                <span class="tab-dot data"></span>数据源管理
                <span class="tab-hint">上传与任务队列</span>
              </span>
            </template>
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
          <a-tab-pane key="workbench" tab="ETL 清洗工作台">
            <template #tab>
              <span class="tab-label">
                <span class="tab-dot workbench"></span>ETL 清洗工作台
                <span class="tab-hint">双屏校验</span>
              </span>
            </template>
            <EtlWorkbench
              :task="currentTask"
              @task-completed="handleTaskCompleted"
              @task-updated="handleTaskUpdated"
              @navigate-to-data-sources="activeTab = 'data'"
            />
          </a-tab-pane>
        </a-tabs>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.domain-factory-view {
  padding: 24px 28px 80px;
  min-height: 100%;
  background: var(--gray-50, #f5f7fb);

  .factory-main {
    max-width: 100%;
    margin: 0 auto;
  }

  .hero {
    border-radius: 16px;
    background: #fff;
    border: 1px solid var(--gray-150, #e8ecf1);
    margin-bottom: 20px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);

    &.collapsed {
      border-radius: 12px;

      .hero-bar {
        padding: 8px 24px;
      }
    }

    .hero-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 28px 32px 12px;
      gap: 40px;
      background:
        radial-gradient(ellipse at top right, rgba(22, 119, 255, 0.06), transparent 50%),
        linear-gradient(135deg, #fafcff 0%, #fff 100%);
    }

    .hero-text {
      flex: 1;

      .badge {
        display: inline-flex;
        align-items: center;
        font-size: 12px;
        font-weight: 600;
        color: var(--main-color, #1677ff);
        background: rgba(22, 119, 255, 0.08);
        padding: 2px 10px;
        border-radius: 999px;
        margin-bottom: 12px;
        letter-spacing: 0.3px;
      }

      h1 {
        margin: 0;
        font-size: 26px;
        font-weight: 700;
        color: var(--gray-900, #0f172a);
        letter-spacing: -0.3px;
      }

      .desc {
        margin-top: 8px;
        color: var(--gray-500, #64748b);
        font-size: 13px;
        max-width: 520px;
        line-height: 1.6;
      }
    }

    .hero-illustration {
      flex-shrink: 0;

      .pipeline-visual {
        display: flex;
        align-items: center;
        gap: 0;
        padding: 16px 24px;
        background: linear-gradient(135deg, rgba(22, 119, 255, 0.03), rgba(82, 196, 26, 0.03));
        border-radius: 14px;
        border: 1px solid var(--gray-100, #f1f5f9);
      }

      .pipeline-node {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 14px;
        border-radius: 10px;
        background: #fff;
        border: 1px solid var(--gray-100, #f1f5f9);
        transition: all 0.2s;
        min-width: 100px;

        &:hover {
          box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
          transform: translateY(-1px);
        }

        &.accent {
          border-color: rgba(22, 119, 255, 0.15);
          background: rgba(22, 119, 255, 0.02);
        }

        &.success {
          border-color: rgba(82, 196, 26, 0.15);
          background: rgba(82, 196, 26, 0.02);
        }

        .node-icon-wrap {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 10px;
          font-size: 18px;
          flex-shrink: 0;

          &.upload {
            background: rgba(22, 119, 255, 0.08);
            color: #1677ff;
          }

          &.ai {
            background: rgba(114, 46, 209, 0.08);
            color: #722ed1;
          }

          &.review {
            background: rgba(250, 173, 20, 0.08);
            color: #d48806;
          }

          &.store {
            background: rgba(82, 196, 26, 0.08);
            color: #389e0d;
          }
        }

        .node-body {
          display: flex;
          flex-direction: column;
          gap: 2px;

          .node-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--gray-800, #1e293b);
          }

          .node-desc {
            font-size: 11px;
            color: var(--gray-400, #94a3b8);
          }
        }
      }

      .pipeline-arrow {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        flex-shrink: 0;
        color: var(--gray-300, #cbd5e1);
        font-size: 10px;
      }
    }

    .hero-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 32px 10px;
      border-top: 1px solid var(--gray-100, #f1f5f9);

      .hero-stats {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .hero-stat-card {
        min-width: 60px;
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 8px 10px;
        border-radius: 8px;
        background: var(--main-0);
        border: 1px solid var(--gray-100);
        color: var(--main-color);

        .hero-stat-inline {
          display: flex;
          flex-direction: row;
          align-items: baseline;
          gap: 4px;
        }

        strong {
          font-size: 14px;
          line-height: 1.2;
          color: var(--gray-900);
          white-space: nowrap;
          font-weight: 600;
        }

        span {
          font-size: 11px;
          color: var(--gray-500);
          white-space: nowrap;
        }
      }

      .hero-toggle {
        font-size: 12px;
        color: var(--gray-400, #94a3b8);
        cursor: pointer;
        user-select: none;
        transition: color 0.2s;

        &:hover { color: var(--main-color, #1677ff); }
      }

      .hero-actions {
        display: flex;
        gap: 8px;

        .hero-nav-btn {
          border-radius: 6px;
          font-size: 13px;
          color: var(--gray-600, #475569);
          border-color: var(--gray-200, #e2e8f0);

          &:hover {
            color: var(--main-color, #1677ff);
            border-color: var(--main-color, #1677ff);
          }
        }
      }
    }
  }

  .factory-tabs-wrapper {
    background: #fff;
    border-radius: 0;
    border: none;
    box-shadow: none;
    overflow: hidden;
  }

  .factory-tabs {
    :deep(.ant-tabs-nav) {
      margin: 0;
      padding: 0 8px;
      background: #fff;

      &::before {
        border-bottom: 1px solid var(--gray-100, #f1f5f9);
      }
    }

    :deep(.ant-tabs-tab) {
      padding: 14px 16px;
      font-size: 14px;

      .tab-label {
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }

      .tab-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;

        &.data { background: #1677ff; }
        &.workbench { background: #722ed1; }
      }

      .tab-hint {
        font-size: 12px;
        color: var(--gray-400, #94a3b8);
        margin-left: 2px;
      }
    }

    :deep(.ant-tabs-content-holder) {
      padding: 0;
    }

    :deep(.ant-tabs-content) {
      background: transparent;
    }

    :deep(.ant-tabs-tabpane) {
      padding: 0;
    }
  }
}

.hero-expand-enter-active,
.hero-expand-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}

.hero-expand-enter-from,
.hero-expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
</style>
