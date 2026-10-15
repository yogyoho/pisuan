<template>
  <div class="factory-chrome">
    <!-- 左侧子页导航（原型 chrome 配方；分组为产品语义，原型的 P1/P2/P3 批次标签不入产品菜单） -->
    <aside class="chrome-side">
      <div class="chrome-brand">
        <h1>环评数据工厂</h1>
        <p>coal-eia-writer 技能数据资产</p>
      </div>
      <div v-for="g in groups" :key="g.label" class="chrome-group">
        <div class="g-label">
          {{ g.label }} <span class="g-tag">{{ g.items.length }} 页</span>
        </div>
        <button
          v-for="it in g.items"
          :key="it.to"
          class="nav-item"
          :class="{ on: route.path === it.to }"
          @click="router.push(it.to)"
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
    <!-- 内容列：max-width 对齐原型 .screen 画布（各面板自带 20/24/40 内边距） -->
    <main class="chrome-main">
      <div class="chrome-canvas">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import {
  BookOpen,
  Box,
  ChartColumn,
  ChartLine,
  ClipboardList,
  CornerDownLeft,
  LayoutGrid,
  MessageSquareQuote,
  NotebookPen,
  Rows3,
  ShieldCheck
} from '@lucide/vue'

const route = useRoute()
const router = useRouter()

const groups = [
  {
    label: '数据分层',
    items: [{ to: '/domain-factory/eia-data', label: '分层统计总览', icon: ChartColumn }]
  },
  {
    label: '语料与护栏',
    items: [
      { to: '/domain-factory/eia-data/lexicon', label: '数值护栏词表', icon: BookOpen },
      { to: '/domain-factory/eia-data/meta', label: '语料元数据标注', icon: LayoutGrid },
      { to: '/domain-factory/eia-data/standards', label: '标准与限值库', icon: ShieldCheck }
    ]
  },
  {
    label: '章节与备料',
    items: [
      { to: '/domain-factory/eia-data/sections', label: '章节口径', icon: Rows3 },
      { to: '/domain-factory/eia-data/expectations', label: '备料清单浏览', icon: ClipboardList }
    ]
  },
  {
    label: '参数与实体',
    items: [
      { to: '/domain-factory/eia-data/formulas', label: '公式参数核对', icon: ChartLine },
      { to: '/domain-factory/eia-data/entities', label: '实体注册补充', icon: Box }
    ]
  },
  {
    label: '写作范式',
    items: [
      { to: '/domain-factory/eia-data/paradigms', label: '写作范式（md）', icon: NotebookPen },
      {
        to: '/domain-factory/eia-data/forms',
        label: '句式范式（catalog）',
        icon: MessageSquareQuote
      }
    ]
  }
]
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

/* 原型 .screen 画布宽（.ewp 自带 20/24/40 内边距，画布只管宽） */
.chrome-canvas {
  max-width: 1180px;
}

/* 暗色：选中底/组标签底提亮一档（原型 .proto-dark 同款） */
:root.dark .factory-chrome {
  .nav-item.on {
    background: var(--main-100);
  }

  .g-label .g-tag {
    background: var(--main-100);
  }
}
</style>
