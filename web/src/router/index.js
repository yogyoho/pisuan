import { createRouter, createWebHistory } from 'vue-router'
import BlankLayout from '@/layouts/BlankLayout.vue'
import { useUserStore } from '@/stores/user'
import { useAgentStore } from '@/stores/agent'
import { sanitizeRedirect } from '@/utils/oidcAutoStart'

const AppLayout = () => import('@/layouts/AppLayout.vue')

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'main',
      component: BlankLayout,
      children: [
        {
          path: '',
          name: 'Home',
          component: () => import('../views/HomeViewV2.vue'),
          meta: { keepAlive: false, requiresAuth: false }
        },
        {
          path: 'landing-v2',
          name: 'HomeV2',
          component: () => import('../views/HomeViewV2.vue'),
          meta: { keepAlive: false, requiresAuth: false }
        }
      ]
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/auth/oidc/callback', // oidc登录回调页面
      name: 'OIDCCallback',
      component: () => import('@/views/OIDCCallbackView.vue'),
      meta: { public: true }
    },
    {
      path: '/auth/cli/authorize',
      name: 'CLIAuthAuthorize',
      component: () => import('@/views/CLIAuthAuthorizeView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/agent',
      name: 'AgentMain',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'AgentComp',
          component: () => import('../views/AgentView.vue'),
          meta: { keepAlive: true, requiresAuth: true }
        },
        {
          path: ':thread_id',
          name: 'AgentCompWithThreadId',
          component: () => import('../views/AgentView.vue'),
          meta: { keepAlive: true, requiresAuth: true }
        }
      ]
    },
    {
      path: '/workspace',
      name: 'workspace',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'WorkspaceComp',
          component: () => import('../views/WorkspaceView.vue'),
          meta: { keepAlive: true, requiresAuth: true }
        }
      ]
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'DashboardComp',
          component: () => import('../views/DashboardView.vue'),
          meta: { keepAlive: false, requiresAuth: true, requiresSuperAdmin: true }
        }
      ]
    },
    {
      path: '/agent-manage',
      name: 'agent-manage',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'AgentManageComp',
          component: () => import('../views/AgentManageView.vue'),
          meta: { keepAlive: false, requiresAuth: true }
        }
      ]
    },
    {
      path: '/extensions',
      name: 'extensions',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'ExtensionsComp',
          component: () => import('../views/ExtensionsView.vue'),
          meta: {
            keepAlive: false,
            requiresAuth: true
          },
          children: [
            {
              path: 'knowledgebase/:kbId',
              name: 'ExtensionKnowledgeBaseDetail',
              component: () => import('../views/DataBaseInfoView.vue'),
              meta: {
                keepAlive: false,
                requiresAuth: true,
                requiresAdmin: true
              }
            },
            {
              path: 'knowledgebase/:kbId/evaluation/:datasetId',
              name: 'ExtensionEvaluationBenchmarkDetail',
              component: () => import('../views/EvaluationBenchmarkDetailView.vue'),
              meta: {
                keepAlive: false,
                requiresAuth: true,
                requiresAdmin: true
              }
            },
            {
              path: 'mcp/:slug',
              name: 'ExtensionMcpDetail',
              component: () => import('../components/extensions/McpDetailView.vue'),
              meta: {
                keepAlive: false,
                requiresAuth: true,
                requiresAdmin: true
              }
            },
            {
              path: 'skill/:slug',
              name: 'ExtensionSkillDetail',
              component: () => import('../components/extensions/SkillDetailView.vue'),
              meta: {
                keepAlive: false,
                requiresAuth: true
              }
            }
          ]
        }
      ]
    },
    {
      path: '/skills',
      name: 'skills',
      redirect: '/extensions'
    },
    {
      path: '/domain-factory',
      name: 'DomainFactory',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'DomainFactoryMain',
          component: () => import('../views/DomainFactoryView.vue'),
          meta: { keepAlive: false, requiresAuth: true }
        },
        {
          path: 'eia-data',
          component: () => import('../components/eia-data/EiaDataLayout.vue'),
          children: [
            {
              path: '',
              name: 'EiaDataFactory',
              component: () => import('../views/EiaDataView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'lexicon',
              name: 'EiaDataLexicon',
              component: () => import('../views/EiaLexiconView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'library',
              name: 'EiaDataLibrary',
              component: () => import('../views/EiaLibraryView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'meta',
              name: 'EiaDataMeta',
              component: () => import('../views/EiaMetaView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'standards',
              name: 'EiaDataStandards',
              component: () => import('../views/EiaStandardsView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'sections',
              name: 'EiaDataSections',
              component: () => import('../views/EiaSectionsView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'expectations',
              name: 'EiaDataExpectations',
              component: () => import('../views/EiaExpectationsView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'formulas',
              name: 'EiaDataFormulas',
              component: () => import('../views/EiaFormulasView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'entities',
              name: 'EiaDataEntities',
              component: () => import('../views/EiaEntitiesView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'paradigms',
              name: 'EiaDataParadigms',
              component: () => import('../views/EiaParadigmsView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'forms',
              name: 'EiaDataForms',
              component: () => import('../views/EiaFormsView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            }
          ]
        },
        {
          // [pisuan-custom] 通用域：与 eia-data 平级的语料加工通用管线（壳复用 eia chrome 配方），admin 工具页一并迁入
          path: 'general',
          component: () => import('../components/factory-core/GeneralLayout.vue'),
          children: [
            {
              // [pisuan-custom] 总览：知识工厂 Landing 的一比一独立复刻（后续两侧各自演化），作通用域侧栏首项
              path: 'overview',
              name: 'GeneralOverview',
              component: () => import('../views/GeneralOverviewView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              // 进通用域默认打开总览
              path: '',
              redirect: { name: 'GeneralOverview' }
            },
            {
              path: 'data-sources',
              name: 'GeneralData',
              component: () => import('../views/GeneralDataView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'workbench',
              name: 'GeneralWorkbench',
              component: () => import('../views/GeneralWorkbenchView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'attribution',
              name: 'GeneralAttribution',
              component: () => import('../views/GeneralAttributionView.vue'),
              meta: { keepAlive: false, requiresAuth: true }
            },
            {
              path: 'prompt-config',
              name: 'DomainFactoryPromptConfig',
              component: () => import('../views/PromptConfigView.vue'),
              meta: { keepAlive: false, requiresAuth: true, requiresAdmin: true }
            },
            {
              path: 'outline-template',
              name: 'DomainFactoryOutlineTemplate',
              component: () => import('../views/DomainOutlineTemplateView.vue'),
              meta: { keepAlive: false, requiresAuth: true, requiresAdmin: true }
            },
            {
              path: 'entity-builder',
              name: 'DomainEntityBuilder',
              component: () => import('../views/DomainEntityBuilderView.vue'),
              meta: { keepAlive: false, requiresAuth: true, requiresAdmin: true }
            }
          ]
        },
        {
          // [pisuan-custom] 旧路径兼容：原 /domain-factory 直挂的 admin 工具页重定向到通用域
          path: 'prompt-config',
          redirect: { name: 'DomainFactoryPromptConfig' }
        },
        {
          path: 'outline-template',
          redirect: { name: 'DomainFactoryOutlineTemplate' }
        },
        {
          path: 'entity-builder',
          redirect: { name: 'DomainEntityBuilder' }
        }
      ]
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('../views/EmptyView.vue'),
      meta: { requiresAuth: false }
    }
  ]
})

// 全局前置守卫
router.beforeEach(async (to) => {
  // 检查路由是否需要认证
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth === true)
  const requiresAdmin = to.matched.some((record) => record.meta.requiresAdmin)
  const requiresSuperAdmin = to.matched.some((record) => record.meta.requiresSuperAdmin)

  const userStore = useUserStore()

  // 如果有 token 但用户信息未加载，先获取用户信息
  if (userStore.token && !userStore.userId) {
    try {
      await userStore.getCurrentUser()
    } catch (error) {
      // 如果获取用户信息失败（如 token 过期），清除 token
      console.error('获取用户信息失败:', error)
      userStore.logout()
    }
  }

  const isLoggedIn = userStore.isLoggedIn
  const isAdmin = userStore.isAdmin
  const isSuperAdmin = userStore.isSuperAdmin

  // 如果路由需要认证但用户未登录
  if (requiresAuth && !isLoggedIn) {
    // 保存尝试访问的路径，登录后跳转
    sessionStorage.setItem('redirect', to.fullPath)
    return '/login'
  }

  // 如果路由需要管理员权限但用户不是管理员
  if (requiresAdmin && !isAdmin) {
    // 如果是普通用户，跳转到聊天页空态
    try {
      const agentStore = useAgentStore()
      // 等待 store 初始化完成
      if (!agentStore.isInitialized) {
        await agentStore.initialize()
      }
      return '/agent'
    } catch (error) {
      console.error('获取智能体信息失败:', error)
      return '/agent'
    }
  }

  // 如果路由需要超级管理员权限但用户不是超级管理员
  if (requiresSuperAdmin && !isSuperAdmin) {
    try {
      const agentStore = useAgentStore()
      if (!agentStore.isInitialized) {
        await agentStore.initialize()
      }
      return '/agent'
    } catch (error) {
      console.error('获取智能体信息失败:', error)
      return '/agent'
    }
  }

  // 如果用户已登录但访问登录页，按 redirect 参数跳转
  if (to.path === '/login' && isLoggedIn) {
    return sanitizeRedirect(to.query.redirect)
  }

  // 其他情况正常导航
  return true
})

export default router
