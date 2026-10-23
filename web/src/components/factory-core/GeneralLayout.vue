<template>
  <!-- [pisuan-custom] 通用域壳：与 EiaDataLayout 同款 chrome 配方（216px 侧栏 + 分组导航 + 返回知识工厂），
       承载与环评域平级的语料加工通用管线；规范库加工保持抽屉形态，入口挂侧栏不建屏 -->
  <div class="factory-chrome">
    <aside class="chrome-side">
      <div class="chrome-brand">
        <h1>通用域</h1>
        <p>语料加工通用管线</p>
      </div>
      <div class="chrome-overview">
        <button
          class="nav-item"
          :class="{ on: route.path === '/domain-factory/general/overview' }"
          @click="router.push('/domain-factory/general/overview')"
        >
          <LayoutDashboard :size="16" />
          <span>总览</span>
        </button>
      </div>
      <div v-for="g in visibleGroups" :key="g.label" class="chrome-group">
        <div class="g-label">
          {{ g.label }} <span v-if="g.tag" class="g-tag">{{ g.tag }}</span>
        </div>
        <button
          v-for="it in g.items"
          :key="it.label"
          class="nav-item"
          :class="{ on: it.to && route.path === it.to }"
          @click="onNav(it)"
        >
          <component :is="it.icon" :size="16" />
          <span>{{ it.label }}</span>
        </button>
      </div>
      <div class="chrome-foot">
        <button @click="router.push('/domain-factory')">
          <CornerDownLeft :size="16" />
          <span>返回知识工厂</span>
        </button>
      </div>
    </aside>
    <main class="chrome-main">
      <!-- 容器屏（数据源/工作台/归属/admin 工具页）不自带外边距（原首页父级提供 24/28），画布统一补上；
           总览屏直出 Landing 全幅背景，画布零内边距 -->
      <div class="chrome-canvas" :class="{ 'chrome-canvas-bleed': isOverview }">
        <router-view />
      </div>
    </main>
    <RegulationEnrichPanel v-model:open="regulationPanelOpen" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BookOpen,
  Box,
  ClipboardList,
  CornerDownLeft,
  Inbox,
  LayoutDashboard,
  Rows3,
  ShieldCheck,
  Zap
} from '@lucide/vue'
import RegulationEnrichPanel from '@/extensions/regulation-library/RegulationEnrichPanel.vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const regulationPanelOpen = ref(false)

const groups = [
  {
    label: '加工管线',
    tag: '3 页',
    items: [
      { to: '/domain-factory/general/data-sources', label: '数据源管理', icon: Inbox },
      { to: '/domain-factory/general/workbench', label: 'ETL 清洗工作台', icon: ClipboardList },
      { to: '/domain-factory/general/attribution', label: '归属管理', icon: Rows3 }
    ]
  },
  {
    label: '数据与工具',
    tag: '',
    items: [
      { label: '规范库加工', icon: ShieldCheck, drawer: true }
    ]
  }
]

const adminGroups = [
  {
    label: '平台配置',
    tag: '3 页',
    items: [
      { to: '/domain-factory/general/prompt-config', label: 'Prompt 管理', icon: Zap },
      { to: '/domain-factory/general/outline-template', label: '大纲模板', icon: BookOpen },
      { to: '/domain-factory/general/entity-builder', label: '实体构建器', icon: Box }
    ]
  }
]

const onNav = (it) => {
  if (it.drawer) {
    regulationPanelOpen.value = true
    return
  }
  router.push(it.to)
}

// 平台配置组仅管理员可见
const visibleGroups = computed(() => (userStore.isAdmin ? [...groups, ...adminGroups] : groups))

// 总览屏直出知识工厂 Landing：画布零内边距，保留其全幅背景配方
const isOverview = computed(() => route.name === 'GeneralOverview')
</script>

<style lang="less" scoped>
.factory-chrome {
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
}

.chrome-side {
  display: flex;
  flex-direction: column;
  flex: none;
  width: 216px;
  overflow-y: auto;
  background: var(--gray-0);
  border-right: 1px solid var(--gray-200);
}

.chrome-brand {
  padding: 18px 16px 12px;
  border-bottom: 1px solid var(--gray-200);

  h1 {
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: var(--gray-800);
  }

  p {
    margin-top: 2px;
    font-size: 11px;
    color: var(--color-text-tertiary);
  }
}

.chrome-overview {
  padding: 12px 8px 0;
}

.chrome-group {
  padding: 12px 8px 4px;
}

.g-label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary);

  .g-tag {
    padding: 0 5px;
    border-radius: 4px;
    background: var(--main-50);
    color: var(--main-600);
    font-size: 10px;
    font-weight: 600;
  }
}

.nav-item {
  appearance: none;
  background: none;
  border: none;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin-bottom: 2px;
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 13px;
  text-align: left;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s;

  &:hover {
    background: var(--gray-50);
    color: var(--color-text);
  }

  &.on {
    background: var(--main-50);
    color: var(--main-600);
    font-weight: 600;
  }
}

.chrome-foot {
  margin-top: auto;
  padding: 12px 16px;
  border-top: 1px solid var(--gray-200);

  button {
    appearance: none;
    background: none;
    border: none;
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 6px 8px;
    border-radius: 6px;
    font-size: 12px;
    color: var(--color-text-secondary);
    cursor: pointer;

    &:hover {
      background: var(--gray-50);
      color: var(--color-text);
    }
  }
}

.chrome-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

/* 通用域屏多为表格/双屏工作台，不锁 1180 画布宽（区别于 eia 表单屏） */
.chrome-canvas {
  padding: 20px 24px 32px;
}

/* 总览屏：Landing 自带全幅背景与节奏，画布让位直出 */
.chrome-canvas-bleed {
  padding: 0;
}

/* 暗色：选中底/组标签底提亮一档（EiaDataLayout 同款） */
:root.dark .factory-chrome {
  .nav-item.on {
    background: var(--main-100);
  }

  .g-label .g-tag {
    background: var(--main-100);
  }
}
</style>
