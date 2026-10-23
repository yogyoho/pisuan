<!-- [pisuan-custom] 知识工厂 Landing 首页 · 立式流水线方案（2026-10-14 用户选定；与系统首页 HomeViewV2 拉开布局差异：
     无营销 hero/拟真窗/三列卡组/深色 CTA，以装配线主轴作页面骨架。原工作台三 tab 迁往 /domain-factory/general 通用域。
     同日二轮精修（用户反馈「太单调」）：传送带实体化（带体+滚动刻度+进料箭头）、工位卡图标块+序号水印+顶部流光条、
     铭牌金属质感+铆钉、顶部运转指示灯、收工带斜纹+印章、主按钮流光扫过；全部动效受 reduced-motion 约束。
     背景配方对齐系统首页 hero（HomeViewV2 .lp-hero）：右上靛蓝光晕 + 左下橙光晕 + 32px 方格网） -->
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

      <!-- 2) 管线全景：语料加工管线 × 写手技能流程（archify 图整页嵌入，含流动动效与代码锚点） -->
      <section class="dfp-flowmap">
        <div class="dfp-container">
          <div class="dfp-flowmap-cap reveal">
            <b>管线全景 · 生产与消费</b>
            <span>语料提取加工管线与 coal-eia-writer 技能流程，节点锚定真实代码</span>
          </div>
          <div class="dfp-flowmap-frame reveal">
            <iframe
              src="/diagrams/corpus-writer-flow.html"
              title="语料提取加工管线与 coal-eia-writer 技能流程图"
              loading="lazy"
              @load="fitFlowmap"
            ></iframe>
          </div>
        </div>
      </section>

      <!-- 3) 工位名录：模块横带 + 屏级 chip 直达 -->
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

      <!-- 4) 收工带 -->
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

// 图页为同源整页 viewer：仅藏其滚动条（工具栏等操作全保留），iframe 高度按内容实高校准；
// 另把导出按钮对齐宿主主按钮配色（变量取宿主实值注入，随宿主明暗主题走）
const fitFlowmap = (evt) => {
  const frame = evt.target
  const doc = frame.contentDocument
  const root = doc?.documentElement
  if (!root) return
  root.style.overflow = 'hidden'
  if (doc.body) doc.body.style.overflow = 'hidden'
  const cs = getComputedStyle(document.documentElement)
  const v = (name) => cs.getPropertyValue(name).trim()
  const style = doc.createElement('style')
  style.textContent = `
    .toolbar #btn-export::before { display: none; }
    .toolbar #btn-export {
      background: ${v('--main-600')};
      color: ${v('--gray-0')};
      border-radius: 8px;
      font-weight: 600;
      /* 与左侧控件药丸视觉同高（36px），在 44px 行内居中 */
      min-height: 2.25rem;
    }
    .toolbar #btn-export:hover,
    .toolbar #btn-export[aria-expanded='true'] {
      background: ${v('--main-500')};
      color: ${v('--gray-0')};
      box-shadow: 0 6px 16px ${v('--shadow-3')};
    }
    .toolbar #btn-export:active {
      background: ${v('--main-700')};
    }
  `
  doc.head.appendChild(style)
  const sync = () => {
    const h = Math.max(root.scrollHeight, doc.body?.scrollHeight || 0)
    if (h > 0) frame.style.height = `${h}px`
  }
  sync()
  new ResizeObserver(sync).observe(root)
}


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

/* ============ 2) 管线全景（archify 图 iframe 整页嵌入） ============ */
.dfp-flowmap-cap {
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

.dfp-flowmap-frame {
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  overflow: hidden;
  background: var(--gray-0);

  iframe {
    display: block;
    width: 100%;
    /* 初始估值，onLoad 后按图页内容实高校准 */
    height: 1200px;
    border: 0;
  }
}

/* ============ 3) 工位名录 ============ */
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

/* ============ 4) 收工带 ============ */
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
  .dfp-btn-primary::after {
    display: none;
  }

  .run-dot {
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

  .c-wm {
    display: none;
  }

  .m-chips {
    max-width: none;
    justify-content: flex-start;
  }
}

@media (max-width: 767px) {
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
