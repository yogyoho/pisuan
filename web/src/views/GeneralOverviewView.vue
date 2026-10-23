<!-- [pisuan-custom] 通用域「总览」屏：知识工厂 Landing 的一比一独立复刻（2026-10-23 自 DomainFactoryView
     整文件拷贝，非组件复用）——后续两侧各自演化：改知识工厂 hero 页不影响本屏，反之亦然。
     拷贝时含当时的状态修正（无数据统计 chip、数据源管理指向 data-sources）。样式 scoped 与原页互不泄漏；
     reveal 观察器按 .dfp 全局查询，两屏不同路由不并存，无串扰 -->
<template>
  <div class="dfp">
    <main>
      <!-- 1) 顶部工作台横带：紧凑左文右 CTA，不做居中营销 hero -->
      <section class="dfp-top">
        <div class="dfp-container">
          <div class="dfp-top-inner">
            <div class="dfp-top-copy reveal">
              <span class="dfp-badge">
                <Sparkles :size="12" />
                <span>DOMAIN KNOWLEDGE FACTORY</span>
              </span>
              <h1>领域知识工厂</h1>
              <p class="dfp-sub">
                语料从进料口上流水线：AI
                负责解析、提取与泛化，专家双屏复核把关，入库即精品——整条管线在本页一览，工位即入口。
              </p>
              <div class="dfp-run">
                <span class="dfp-run-state">
                  <i class="run-dot" aria-hidden="true"></i>
                  <span>管线运转中</span>
                </span>
                <i class="run-sep" aria-hidden="true"></i>
                <span>5 步加工 · 双屏校验 · 3 层入库</span>
              </div>
            </div>
            <div class="dfp-top-cta reveal" :style="{ '--stagger': 1 }">
              <button
                class="dfp-btn dfp-btn-primary"
                @click="router.push('/domain-factory/general')"
              >
                <span>进入通用域</span>
                <ArrowRight :size="16" />
              </button>
              <button
                class="dfp-btn dfp-btn-outline"
                @click="router.push('/domain-factory/eia-data')"
              >
                <span>环评域入口</span>
                <ArrowRight :size="16" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 2) 装配线主轴：实体传送带 + 流动加工件 + 四工位卡上下交错 -->
      <section class="dfp-floor">
        <div class="dfp-container dfp-floor-inner">
          <div class="dfp-rail" aria-hidden="true"></div>
          <span
            v-for="i in 3"
            :key="i"
            class="dfp-flow"
            :class="`dfp-flow-f${i}`"
            aria-hidden="true"
          ></span>
          <div class="dfp-stations">
            <div
              v-for="(s, i) in stations"
              :key="s.no"
              class="dfp-station reveal"
              :style="{ '--stagger': i }"
            >
              <div class="s-card">
                <span class="s-wm" aria-hidden="true">{{ s.wm }}</span>
                <span class="s-ico" aria-hidden="true">
                  <component :is="s.icon" :size="18" />
                </span>
                <span class="s-no">{{ s.no }}</span>
                <h3>{{ s.title }}</h3>
                <p>{{ s.desc }}</p>
                <div class="s-meter">
                  <span v-for="m in s.meters" :key="m">{{ m }}</span>
                </div>
                <button type="button" class="s-go" @click="router.push(s.to)">
                  直达 {{ s.screen }}
                  <ArrowRight :size="12" class="s-go-arr" />
                </button>
              </div>
              <div class="s-stem" aria-hidden="true"></div>
              <div class="s-dot" aria-hidden="true"></div>
            </div>
          </div>
        </div>
      </section>

      <!-- 3) 工位铭牌带（机制口径，仿设备铭牌） -->
      <section class="dfp-plates">
        <div class="dfp-container dfp-plates-grid">
          <div
            v-for="(p, i) in plates"
            :key="p.label"
            class="dfp-plate reveal"
            :style="{ '--stagger': i }"
          >
            <i class="p-screw p-screw-l" aria-hidden="true"></i>
            <i class="p-screw p-screw-r" aria-hidden="true"></i>
            <b>{{ p.label }}</b>
            <span class="p-value">{{ p.value }}</span>
            <p class="p-desc">{{ p.desc }}</p>
          </div>
        </div>
      </section>

      <!-- 4) 工位名录：模块横带 + 屏级 chip 直达 -->
      <section class="dfp-mods">
        <div class="dfp-container">
          <div class="dfp-mods-cap reveal">
            <b>工位名录 · 领域模块</b>
            <span>从横带进入模块，或点 chip 直达工作屏</span>
          </div>
          <div class="dfp-mods-list">
            <div
              v-for="(mod, i) in modules"
              :key="mod.name"
              class="dfp-mod-row reveal"
              :class="{ 'is-ph': mod.placeholder }"
              :style="{ '--stagger': i }"
              :role="mod.to ? 'link' : undefined"
              :tabindex="mod.to ? 0 : -1"
              @click="mod.to && router.push(mod.to)"
              @keydown.enter.prevent="mod.to && router.push(mod.to)"
            >
              <span class="m-bar" :class="mod.tone" aria-hidden="true"></span>
              <span class="m-glyph" :class="mod.tone" aria-hidden="true">
                <component :is="mod.icon" :size="15" />
              </span>
              <span class="m-name"
                >{{ mod.name }}<span class="m-en">{{ mod.en }}</span></span
              >
              <span class="m-desc">{{ mod.desc }}</span>
              <span v-if="mod.chips?.length" class="m-chips">
                <button
                  v-for="chip in mod.chips"
                  :key="chip.label"
                  v-show="!chip.admin || userStore.isAdmin"
                  class="dfp-chip"
                  :class="{ 'is-admin': chip.admin }"
                  @click.stop="router.push(chip.to)"
                >
                  {{ chip.label }}
                </button>
              </span>
              <ArrowRight v-if="mod.to" :size="16" class="m-arrow" />
            </div>
          </div>
        </div>
      </section>

      <!-- 5) 收工带 -->
      <section class="dfp-closing">
        <span class="c-wm" aria-hidden="true">PIPELINE READY</span>
        <div class="dfp-container dfp-closing-inner reveal">
          <div class="c-copy">
            <b>流水线已就绪</b>
            <span>领一张工单即可开工——语料上传、ETL 清洗、归属沉淀、写手消费。</span>
          </div>
          <span class="c-stamp" aria-hidden="true">入库即精品</span>
          <div class="c-cta">
            <button class="dfp-btn dfp-btn-primary" @click="router.push('/domain-factory/general')">
              <span>进入通用域</span>
              <ArrowRight :size="16" />
            </button>
            <button
              class="dfp-btn dfp-btn-outline"
              @click="router.push('/domain-factory/eia-data')"
            >
              浏览环评域
            </button>
          </div>
        </div>
      </section>
    </main>

    <footer class="dfp-footer">
      <div class="dfp-container">
        <p>领域知识工厂 · 数据从语料到资产的单一通道{{ footerCopyright }}</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import {
  Sparkles,
  ArrowRight,
  Inbox,
  Workflow,
  Database,
  PenLine,
  Factory,
  Sprout,
  Mountain
} from '@lucide/vue'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()

const footerCopyright = computed(() => {
  const c = infoStore.footer?.copyright
  return c ? ` · ${c}` : ''
})

// 装配线工位：即四大工作屏入口
const stations = [
  {
    no: 'STATION 01',
    wm: '01',
    icon: Inbox,
    title: '语料进料',
    desc: '领域文档批量上传，选择领域与报告类型，自动建任务入队解析。',
    meters: ['批量上传', '自动入队'],
    screen: '数据源管理',
    to: '/domain-factory/general/data-sources'
  },
  {
    no: 'STATION 02',
    wm: '02',
    icon: Workflow,
    title: 'ETL 清洗',
    desc: '解析、提取、泛化流水线，双屏人机校验把守质量关。',
    meters: ['5 步加工', '双屏校验'],
    screen: 'ETL 工作台',
    to: '/domain-factory/general/workbench'
  },
  {
    no: 'STATION 03',
    wm: '03',
    icon: Database,
    title: '归属入库',
    desc: '归属改判与退役聚合，结构化入库 Milvus / SQL / 图谱。',
    meters: ['3 层入库', '改判 · 退役'],
    screen: '归属管理',
    to: '/domain-factory/general/attribution'
  },
  {
    no: 'STATION 04',
    wm: '04',
    icon: PenLine,
    title: '写手消费',
    desc: '报告写手按章节模板与护栏取用资产，成稿即成品。',
    meters: ['模板复用', '入库即精品'],
    screen: '环评域总览',
    to: '/domain-factory/eia-data'
  }
]

// 设备铭牌：机制口径而非运营统计
const plates = [
  { label: 'PIPELINE', value: '5 步加工', desc: '解析、提取、泛化、校验、入库，全程可复核' },
  { label: 'REVIEW', value: '双屏校验', desc: '机器粗加工，专家双屏逐段终审' },
  { label: 'STORAGE', value: '3 层入库', desc: 'Milvus 向量 · SQL 结构 · 图谱关联' },
  { label: 'REUSE', value: '模板复用', desc: '章节模板与实体资产，跨报告沉淀复用' }
]

const modules = [
  {
    name: '通用域',
    en: 'GENERAL',
    icon: Factory,
    tone: '',
    desc: '语料加工通用管线，领域无关动作与平台工具汇集于此',
    to: '/domain-factory/general',
    placeholder: false,
    chips: [
      { label: '数据源管理', to: '/domain-factory/general/data-sources' },
      { label: 'ETL 工作台', to: '/domain-factory/general/workbench' },
      { label: '归属管理', to: '/domain-factory/general/attribution' },
      { label: '平台工具', to: '/domain-factory/general/prompt-config', admin: true }
    ]
  },
  {
    name: '环评域',
    en: 'EIA',
    icon: Sprout,
    tone: 'is-eia',
    desc: '环评数据资产工厂，coal-eia-writer 技能资产加工与维护',
    to: '/domain-factory/eia-data',
    placeholder: false,
    chips: [
      { label: '总览', to: '/domain-factory/eia-data' },
      { label: '护栏词表', to: '/domain-factory/eia-data/lexicon' },
      { label: '元数据', to: '/domain-factory/eia-data/meta' },
      { label: '标准限值', to: '/domain-factory/eia-data/standards' },
      { label: '章节口径', to: '/domain-factory/eia-data/sections' },
      { label: '备料清单', to: '/domain-factory/eia-data/expectations' },
      { label: '公式参数', to: '/domain-factory/eia-data/formulas' },
      { label: '实体注册', to: '/domain-factory/eia-data/entities' }
    ]
  },
  {
    name: '矿井域',
    en: 'MINING',
    icon: Mountain,
    tone: 'is-gray',
    desc: '规划建设中，敬请期待',
    to: '',
    placeholder: true,
    chips: []
  }
]

// Only show sections when scrolled into view; skip animation entirely for reduced motion
let revealObserver = null

const initReveal = () => {
  const els = document.querySelectorAll('.dfp .reveal')
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    els.forEach((el) => el.classList.add('is-visible'))
    return
  }
  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          revealObserver.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.15 }
  )
  els.forEach((el) => revealObserver.observe(el))
}

onMounted(() => {
  initReveal()
})

onUnmounted(() => {
  if (revealObserver) {
    revealObserver.disconnect()
    revealObserver = null
  }
})
</script>

<style lang="less" scoped>
.dfp {
  color: var(--gray-1000);
  background: var(--gray-0);
  min-height: 100vh;
}

.dfp-container {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0 28px;
}

/* ============ Buttons ============ */
.dfp-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 22px;
  border: 1px solid transparent;
  border-radius: 8px;
  font-size: 14.5px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;

  &:focus-visible {
    outline: 2px solid var(--main-600);
    outline-offset: 2px;
  }
}

.dfp-btn-primary {
  position: relative;
  overflow: hidden;
  background: var(--main-600);
  color: var(--gray-0);

  /* hover 流光扫过 */
  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: -45%;
    width: 36%;
    height: 100%;
    background: linear-gradient(100deg, transparent, rgba(255, 255, 255, 0.3), transparent);
    transform: skewX(-18deg) translateX(0);
    pointer-events: none;
  }

  &:hover {
    background: var(--main-500);
    box-shadow: 0 6px 16px var(--shadow-3);

    &::after {
      transform: skewX(-18deg) translateX(420%);
      transition: transform 0.55s ease;
    }
  }

  &:active {
    background: var(--main-700);
  }
}

.dfp-btn-outline {
  border-color: var(--gray-200);
  color: var(--gray-600);
  background: var(--gray-0);

  &:hover {
    border-color: var(--main-400);
    color: var(--main-700);
    box-shadow: 0 4px 12px var(--shadow-2);
  }
}

/* ============ 1) 顶部工作台横带 ============ */
.dfp-top {
  border-bottom: 1px solid var(--gray-150);

  /* 背景配方与系统首页 hero 同款：双光晕 + 32px 方格网（token 翻转自动适配暗色） */
  background-image:
    radial-gradient(620px 320px at 88% 0%, var(--main-100), transparent 65%),
    radial-gradient(520px 280px at 4% 100%, var(--second-50), transparent 60%),
    repeating-linear-gradient(
      0deg,
      transparent,
      transparent 31px,
      rgba(var(--main-color-rgb), 0.05) 31px,
      rgba(var(--main-color-rgb), 0.05) 32px
    ),
    repeating-linear-gradient(
      90deg,
      transparent,
      transparent 31px,
      rgba(var(--main-color-rgb), 0.05) 31px,
      rgba(var(--main-color-rgb), 0.05) 32px
    );
}

.dfp-top-inner {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 24px;
  padding: 56px 0 32px;
}

.dfp-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--second-200);
  border-radius: 999px;
  background: var(--second-50);
  color: var(--second-700);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
}

.dfp-top-copy h1 {
  margin: 14px 0 10px;
  font-size: clamp(28px, 3vw, 34px);
  font-weight: 800;
  letter-spacing: 0.5px;
  color: var(--gray-1000);
}

.dfp-sub {
  max-width: 580px;
  font-size: 14.5px;
  line-height: 1.75;
  color: var(--gray-500);
}

/* 运转指示灯 + 机制速览 */
.dfp-run {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  font-size: 12.5px;
  color: var(--gray-500);
}

.dfp-run-state {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-weight: 600;
  color: var(--gray-700);
}

.run-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--main-500);
  animation: dfp-ping-run 2s ease-out infinite;
}

.run-sep {
  width: 1px;
  height: 12px;
  background: var(--gray-200);
}

@keyframes dfp-ping-run {
  0% {
    box-shadow: 0 0 0 0 rgba(var(--main-color-rgb), 0.4);
  }

  70%,
  100% {
    box-shadow: 0 0 0 7px rgba(var(--main-color-rgb), 0);
  }
}

.dfp-top-cta {
  display: flex;
  gap: 10px;
  flex: none;
  padding-bottom: 4px;
}

/* ============ 2) 装配线主轴 ============ */
.dfp-floor-inner {
  position: relative;
  padding-top: 14px;
  padding-bottom: 6px;
}

/* 传送带：实体带体 + 滚动刻度 + 进料箭头 */
.dfp-rail {
  position: absolute;
  left: -40px;
  right: -40px;
  top: 227px;
  height: 6px;
  border: 1px solid var(--gray-200);
  border-radius: 999px;
  background: var(--gray-100);
  box-shadow: 0 5px 16px rgba(var(--main-color-rgb), 0.08);

  /* 带面滚动的加工刻度 */
  &::before {
    content: '';
    position: absolute;
    inset: 1px;
    border-radius: inherit;
    background: repeating-linear-gradient(90deg, var(--gray-300) 0 7px, transparent 7px 13px);
    animation: dfp-belt 0.9s linear infinite;
  }

  /* 进料口箭头 */
  &::after {
    content: '';
    position: absolute;
    left: -12px;
    top: 50%;
    transform: translateY(-50%);
    border: 6px solid transparent;
    border-left: 10px solid var(--main-500);
  }
}

@keyframes dfp-belt {
  to {
    background-position-x: 13px;
  }
}

/* 流动加工件：沿带移动的胶囊 */
.dfp-flow {
  position: absolute;
  top: 225px;
  z-index: 1;
  width: 16px;
  height: 9px;
  border-radius: 5px;
  background: linear-gradient(90deg, var(--main-400), var(--main-600));
  box-shadow: 0 0 10px rgba(var(--main-color-rgb), 0.45);
  opacity: 0.9;
  animation: dfp-travel 8s linear infinite;
}

.dfp-flow-f2 {
  animation-delay: 2.6s;
}

.dfp-flow-f3 {
  animation-delay: 5.2s;
}

@keyframes dfp-travel {
  from {
    left: -40px;
  }

  to {
    left: 100%;
  }
}

.dfp-stations {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;
}

.dfp-station {
  position: relative;
  height: 430px;
}

.s-card {
  position: absolute;
  left: 0;
  right: 0;
  height: 196px;
  padding: 17px 18px 13px;
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  background: var(--gray-0);
  box-shadow: 0 1px 2px var(--shadow-2);
  overflow: hidden;
  transition:
    box-shadow 0.25s ease,
    transform 0.25s ease,
    border-color 0.25s ease;

  /* 顶部流光条：hover 时从左展开 */
  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 2;
    height: 3px;
    background: linear-gradient(90deg, var(--main-500), var(--second-400));
    transform: scaleX(0);
    transform-origin: left;
    transition: transform 0.3s ease;
  }

  /* 文字内容抬到水印之上 */
  > * {
    position: relative;
    z-index: 1;
  }
}

.dfp-station:nth-child(odd) .s-card {
  top: 0;
}

.dfp-station:nth-child(even) .s-card {
  bottom: 0;
}

.dfp-station:hover .s-card {
  transform: translateY(-3px);
  border-color: var(--main-400);
  box-shadow: 0 14px 30px var(--shadow-3);

  &::after {
    transform: scaleX(1);
  }
}

.s-go {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-top: 10px;
  padding: 0;
  border: none;
  background: none;
  font-size: 12.5px;
  font-weight: 600;
  font-family: inherit;
  color: var(--main-600);
  cursor: pointer;
  transition: color 0.2s ease;

  &:hover {
    color: var(--main-700);
  }

  &:focus-visible {
    outline: 2px solid var(--main-600);
    outline-offset: 2px;
    border-radius: 2px;
  }
}

.s-go-arr {
  transition: transform 0.2s ease;

  .s-go:hover & {
    transform: translateX(2px);
  }
}

.s-stem {
  position: absolute;
  left: 50%;
  width: 2px;
  background: var(--gray-300);
}

.dfp-station:nth-child(odd) .s-stem {
  top: 196px;
  height: 14px;
}

.dfp-station:nth-child(even) .s-stem {
  top: 222px;
  height: 14px;
}

/* 工位节点：呼吸灯 */
.s-dot {
  position: absolute;
  left: 50%;
  top: 217px;
  z-index: 2;
  width: 12px;
  height: 12px;
  transform: translate(-50%, -50%);
  border: 3px solid var(--main-100);
  border-radius: 50%;
  background: var(--main-600);
  box-shadow: 0 0 0 4px var(--gray-0);
  animation: dfp-ping-dot 2.8s ease-out infinite;
}

.dfp-station:nth-child(2) .s-dot {
  animation-delay: 0.7s;
}

.dfp-station:nth-child(3) .s-dot {
  animation-delay: 1.4s;
}

.dfp-station:nth-child(4) .s-dot {
  animation-delay: 2.1s;
}

@keyframes dfp-ping-dot {
  0% {
    box-shadow:
      0 0 0 4px var(--gray-0),
      0 0 0 5px rgba(var(--main-color-rgb), 0.4);
  }

  70%,
  100% {
    box-shadow:
      0 0 0 4px var(--gray-0),
      0 0 0 13px rgba(var(--main-color-rgb), 0);
  }
}

.s-ico {
  position: absolute;
  top: 15px;
  right: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: var(--main-50);
  color: var(--main-600);
  transition:
    background 0.25s ease,
    color 0.25s ease;

  .dfp-station:hover & {
    background: var(--main-100);
    color: var(--main-700);
  }
}

/* 卡角大序号水印 */
.s-wm {
  position: absolute;
  right: 10px;
  bottom: -12px;
  z-index: 0;
  font-size: 58px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: 2px;
  color: var(--gray-100);
  user-select: none;
  pointer-events: none;
}

.s-no {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--main-600);
}

.s-card h3 {
  margin: 7px 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--gray-1000);
}

.s-card p {
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--gray-500);
}

.s-meter {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 10px;
}

.s-meter span {
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--gray-100);
  color: var(--gray-600);
  font-size: 11px;
}

/* ============ 3) 工位铭牌带 ============ */
.dfp-plates-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  padding-top: 30px;
  padding-bottom: 8px;
}

.dfp-plate {
  position: relative;
  padding: 16px 18px 14px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  background: linear-gradient(180deg, var(--gray-0) 0%, var(--gray-25) 100%);
  box-shadow:
    inset 0 1px 0 var(--gray-0),
    0 1px 2px var(--shadow-2);

  /* 铭牌顶部双刻线 */
  &::before {
    content: '';
    position: absolute;
    top: 6px;
    left: 18px;
    right: 18px;
    height: 1px;
    background: var(--gray-150);
    box-shadow: 0 3px 0 var(--gray-150);
  }
}

/* 铆钉 */
.p-screw {
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--gray-300);
  box-shadow:
    inset 0 1px 1px var(--gray-0),
    0 1px 0 var(--gray-0);
}

.p-screw-l {
  top: 9px;
  left: 9px;
}

.p-screw-r {
  top: 9px;
  right: 9px;
}

.dfp-plate b {
  display: block;
  margin: 8px 0 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--gray-400);
}

.p-value {
  font-size: 19px;
  font-weight: 800;
  color: var(--main-700);
  font-variant-numeric: tabular-nums;
}

.p-desc {
  margin-top: 4px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--gray-500);
}

/* ============ 4) 工位名录 ============ */
.dfp-mods-cap {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 30px 0 12px;

  b {
    font-size: 17px;
    font-weight: 800;
    color: var(--gray-1000);
  }

  span {
    font-size: 12px;
    color: var(--gray-400);
  }
}

.dfp-mods-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 8px;
}

.dfp-mod-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 15px 20px;
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  background: var(--gray-0);
  cursor: pointer;
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    border-color: var(--main-400);
    background: rgba(var(--main-color-rgb), 0.03);
    box-shadow: 0 8px 22px var(--shadow-3);
  }

  &:focus-visible {
    outline: none;
    border-color: var(--main-500);
    box-shadow: 0 0 0 2px var(--main-100);
  }

  &.is-ph {
    border-style: dashed;
    opacity: 0.55;
    cursor: default;

    &:hover {
      transform: none;
      border-color: var(--gray-200);
      background: var(--gray-0);
      box-shadow: none;
    }
  }
}

.m-bar {
  flex: none;
  width: 4px;
  height: 28px;
  border-radius: 2px;
  background: var(--main-500);

  &.is-eia {
    background: var(--second-500);
  }

  &.is-gray {
    background: var(--gray-300);
  }
}

/* 模块图标块 */
.m-glyph {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--main-50);
  color: var(--main-600);

  &.is-eia {
    background: var(--second-50);
    color: var(--second-700);
  }

  &.is-gray {
    background: var(--gray-100);
    color: var(--gray-400);
  }
}

.m-name {
  font-size: 15.5px;
  font-weight: 700;
  white-space: nowrap;
  color: var(--gray-1000);
}

.m-en {
  margin-left: 6px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--gray-400);
}

.m-desc {
  flex: 1;
  font-size: 12.5px;
  color: var(--gray-500);
}

.m-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  justify-content: flex-end;
  max-width: 420px;
}

.dfp-chip {
  padding: 3px 10px;
  border: 1px solid var(--gray-200);
  border-radius: 999px;
  background: var(--gray-0);
  color: var(--gray-600);
  font-size: 11.5px;
  font-family: inherit;
  cursor: pointer;
  transition:
    color 0.15s ease,
    border-color 0.15s ease,
    background 0.15s ease,
    transform 0.15s ease;

  &:hover {
    border-color: var(--main-400);
    color: var(--main-700);
    background: var(--main-50);
    transform: translateY(-1px);
  }

  &.is-admin {
    border-style: dashed;
    border-color: var(--second-200);
    color: var(--second-700);
    background: var(--second-50);

    &:hover {
      border-color: var(--second-400);
      color: var(--second-700);
      background: var(--second-100);
    }
  }
}

.m-arrow {
  flex: none;
  color: var(--gray-400);
  transition:
    color 0.2s ease,
    transform 0.2s ease;

  .dfp-mod-row:hover & {
    color: var(--main-500);
    transform: translateX(2px);
  }
}

/* ============ 5) 收工带 ============ */
.dfp-closing {
  position: relative;
  margin-top: 34px;
  border-top: 1px solid var(--gray-150);
  overflow: hidden;

  /* 顶部斜纹加工带 */
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 5px;
    background: repeating-linear-gradient(135deg, var(--gray-200) 0 7px, transparent 7px 14px);
    opacity: 0.7;
    pointer-events: none;
  }

  /* 右侧橙色氛围 */
  &::after {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(
      420px 220px at 94% 30%,
      color-mix(in srgb, var(--second-500) 7%, transparent),
      transparent 70%
    );
    pointer-events: none;
  }
}

.c-wm {
  position: absolute;
  right: -8px;
  bottom: -20px;
  z-index: 0;
  font-size: 84px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: 4px;
  color: var(--gray-100);
  user-select: none;
  pointer-events: none;
}

.dfp-closing-inner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 20px;
  padding-top: 32px;
  padding-bottom: 36px;
}

.c-copy {
  b {
    display: block;
    font-size: 18px;
    font-weight: 800;
    color: var(--gray-1000);
  }

  span {
    font-size: 13px;
    color: var(--gray-500);
  }
}

/* 质检印章 */
.c-stamp {
  flex: none;
  margin-left: auto;
  padding: 5px 14px;
  border: 2px solid color-mix(in srgb, var(--second-500) 65%, transparent);
  border-radius: 8px;
  color: var(--second-700);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 4px;
  transform: rotate(-5deg);
  background: color-mix(in srgb, var(--second-50) 80%, transparent);
}

.c-cta {
  display: flex;
  gap: 10px;
}

/* ============ Footer ============ */
.dfp-footer {
  border-top: 1px solid var(--gray-150);

  p {
    margin: 0;
    padding: 22px 0 30px;
    text-align: center;
    font-size: 12.5px;
    color: var(--gray-400);
  }
}

/* ============ Reveal animation ============ */
.reveal {
  opacity: 0;
  transform: translateY(22px);
  transition:
    opacity 0.55s ease-out,
    transform 0.55s ease-out;
  transition-delay: calc(var(--stagger, 0) * 60ms);

  &.is-visible {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .dfp-flow,
  .dfp-rail::before,
  .dfp-btn-primary::after {
    display: none;
  }

  .run-dot,
  .s-dot {
    animation: none;
  }

  .reveal {
    opacity: 1;
    transform: none;
    transition: none;
  }
}

/* ============ Responsive ============ */
@media (max-width: 1024px) {
  .dfp-top-inner {
    flex-direction: column;
    align-items: flex-start;
  }

  /* 窄屏收起交错轨道，工位卡改常规网格 */
  .dfp-rail,
  .dfp-flow,
  .s-stem,
  .s-dot {
    display: none;
  }

  .dfp-stations {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .dfp-station {
    height: auto;
  }

  .s-card {
    position: static;
    height: auto;
  }

  .dfp-plates-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .c-wm {
    display: none;
  }

  .m-chips {
    max-width: none;
    justify-content: flex-start;
  }
}

@media (max-width: 767px) {
  .dfp-stations,
  .dfp-plates-grid {
    grid-template-columns: 1fr;
  }

  .dfp-mod-row {
    flex-wrap: wrap;
  }

  .m-desc {
    flex-basis: 100%;
    order: 3;
  }

  .m-chips {
    order: 4;
  }

  .dfp-top-cta .dfp-btn {
    flex: 1 1 auto;
  }

  .c-stamp {
    margin-left: 0;
  }
}
</style>
