<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ChevronDown, ChevronUp, Database, FlaskConical, Layers, Leaf, LayoutGrid, Mountain, Zap } from '@lucide/vue'
import DataSourceDashboard from '@/components/domain-factory/DataSourceDashboard.vue'
import EtlWorkbench from '@/components/domain-factory/EtlWorkbench.vue'
import RegionAttributionPanel from '@/components/domain-factory/RegionAttributionPanel.vue'
import RegulationEnrichPanel from '@/extensions/regulation-library/RegulationEnrichPanel.vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'
import { useTaskerStore } from '@/stores/tasker'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const taskerStore = useTaskerStore()
const userStore = useUserStore()

const activeTab = ref('data')
const regulationPanelOpen = ref(false)
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

// [pisuan-custom] 应用入口磁贴：写死示例占位，应用中心立项后再接 getDomains() 真数据
const APP_ENTRIES = [
  { key: 'eia', name: '环评域', desc: '报告智能加工', icon: Leaf, tone: 'eia' },
  { key: 'mining', name: '矿井域', desc: '规划建设中', icon: Mountain, tone: 'mining' }
]

const handleAppStub = (name) => {
  if (name === '环评域') {
    router.push('/domain-factory/eia-data')
    return
  }
  message.info(`「${name}」建设中`)
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
  if (userStore.isAdmin && currentTask.value?.id) {
    domainFactoryApi.syncTaskToTaskCenter(currentTask.value.id).catch((err) => {
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
  } catch {
    // 静默失败，不影响主页面
  }
}

onMounted(() => {
  fetchDomains()
  fetchStats()
})

watch(
  () => route.query.tab,
  (tab) => {
    if (tab && ['data', 'workbench'].includes(tab)) {
      activeTab.value = tab
      router.replace({ query: { ...route.query, tab: undefined } })
    }
  }
)
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
                <FlaskConical :size="12" style="margin-right: 4px" />Domain Knowledge Factory
              </div>
              <h1>人机协同的领域知识工厂</h1>
              <p class="desc">
                AI 负责粗加工，专家完成精加工，最终将高质量数据入库 Milvus / SQL /
                图谱，确保「入库即精品」。
              </p>
            </div>
            <div class="app-launcher">
              <button
                v-for="entry in APP_ENTRIES"
                :key="entry.key"
                class="app-tile"
                :class="`tone-${entry.tone}`"
                @click="handleAppStub(entry.name)"
              >
                <span class="app-icon-chip">
                  <component :is="entry.icon" :size="20" />
                </span>
                <span class="app-name">{{ entry.name }}</span>
                <span class="app-desc">{{ entry.desc }}</span>
              </button>
              <button class="app-tile more" @click="handleAppStub('应用中心')">
                <span class="app-icon-chip">
                  <LayoutGrid :size="20" />
                </span>
                <span class="app-name">更多</span>
                <span class="app-desc">应用中心</span>
              </button>
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
            <component :is="heroCollapsed ? ChevronDown : ChevronUp" :size="12" />
            {{ heroCollapsed ? '展开简介' : '收起' }}
          </span>
          <div class="hero-actions">
            <a-button
              v-if="userStore.isAdmin"
              size="small"
              class="hero-nav-btn"
              @click="router.push('/domain-factory/prompt-config')"
            >
              <Zap :size="13" /> Prompt 管理
            </a-button>
            <a-button
              v-if="userStore.isAdmin"
              size="small"
              class="hero-nav-btn"
              @click="router.push('/domain-factory/outline-template')"
            >
              大纲模板
            </a-button>
            <a-button
              v-if="userStore.isAdmin"
              size="small"
              class="hero-nav-btn"
              @click="router.push('/domain-factory/entity-builder')"
            >
              实体构建器
            </a-button>
            <a-button size="small" class="hero-nav-btn" @click="regulationPanelOpen = true">
              规范库加工
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
          <a-tab-pane key="region" tab="归属管理">
            <template #tab>
              <span class="tab-label">
                <span class="tab-dot region"></span>归属管理
                <span class="tab-hint">改判 · 退役 · 聚合</span>
              </span>
            </template>
            <RegionAttributionPanel />
          </a-tab-pane>
        </a-tabs>
      </div>
    </div>
    <RegulationEnrichPanel v-model:open="regulationPanelOpen" />
  </div>
</template>

<style lang="less" scoped>
.domain-factory-view {
  padding: 24px 28px 32px;
  min-height: 100%;
  background: var(--gray-50, #f5f7fb);

  .factory-main {
    max-width: 100%;
    margin: 0 auto;
  }

  .hero {
    border-radius: 16px;
    background: var(--gray-0);
    border: 1px solid var(--gray-150);
    margin-bottom: 20px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);

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
      flex-wrap: wrap;
      padding: 28px 32px 12px;
      gap: 40px;
      background:
        radial-gradient(ellipse at top right, rgba(var(--main-color-rgb), 0.06), transparent 50%),
        linear-gradient(135deg, var(--main-10) 0%, var(--gray-0) 100%);
    }

    .hero-text {
      flex: 1;

      .badge {
        display: inline-flex;
        align-items: center;
        font-size: 12px;
        font-weight: 600;
        color: var(--main-color);
        background: rgba(var(--main-color-rgb), 0.08);
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

    .app-launcher {
      flex-shrink: 0;
      display: flex;
      align-items: stretch;
      gap: 12px;

      .app-tile {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 7px;
        width: 116px;
        padding: 14px 10px 12px;
        border-radius: 12px;
        background: var(--gray-0);
        border: 1px solid var(--gray-100);
        cursor: pointer;
        transition: all 0.2s;
        font-family: inherit;

        &:hover {
          box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
          transform: translateY(-1px);
        }

        &:focus-visible {
          outline: 2px solid var(--main-color);
          outline-offset: 2px;
        }

        .app-icon-chip {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 40px;
          height: 40px;
          border-radius: 10px;
          background: rgba(var(--main-color-rgb), 0.08);
          color: var(--main-color);
        }

        .app-name {
          font-size: 13px;
          font-weight: 600;
          color: var(--gray-800, #1e293b);
        }

        .app-desc {
          font-size: 11px;
          color: var(--gray-400, #94a3b8);
        }

        &.tone-mining .app-icon-chip {
          /* [pisuan-custom] 青云素雅：一次性装饰色（矿井域琥珀点缀），不随主题 */
          background: rgba(250, 173, 20, 0.12);
          color: var(--color-warning-700);
        }

        &.more {
          background: transparent;
          border-style: dashed;

          .app-icon-chip {
            background: var(--gray-100);
            color: var(--gray-400, #94a3b8);
          }
        }
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

        &:hover {
          color: var(--main-color);
        }
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
            color: var(--main-color);
            border-color: var(--main-color);
          }
        }
      }
    }
  }

  .factory-tabs-wrapper {
    background: var(--gray-0);
    border-radius: 0;
    border: none;
    box-shadow: none;
    overflow: hidden;
  }

  .factory-tabs {
    :deep(.ant-tabs-nav) {
      margin: 0;
      padding: 0 8px;
      background: var(--gray-0);

      &::before {
        border-bottom: 1px solid var(--gray-100);
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

        &.data {
          background: var(--main-color);
        }
        &.workbench {
          background: #722ed1; /* [pisuan-custom] 青云素雅：一次性装饰色（领域工厂状态点缀），不随主题 */
        }
        &.region {
          background: #0891b2; /* [pisuan-custom] W4 归属管理点缀（科技青系），不随主题 */
        }
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
