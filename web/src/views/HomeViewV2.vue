<template>
  <div class="lp">
    <header class="lp-header" :class="{ 'is-scrolled': isScrolled }">
      <div class="lp-container lp-header-inner">
        <a class="lp-brand" href="#top">
          <img
            :src="infoStore.organization.logo"
            :alt="infoStore.organization.name"
            class="lp-brand-logo"
          />
          <span class="lp-brand-name">{{ infoStore.organization.name }}</span>
        </a>
        <nav class="lp-nav" aria-label="页面导航">
          <a href="#features">核心能力</a>
          <a href="#workflow">工作流程</a>
          <a href="#scenarios">应用场景</a>
        </nav>
        <div class="lp-header-actions">
          <button v-if="!userStore.isLoggedIn" class="lp-btn lp-btn-ghost" @click="goLogin">
            登录
          </button>
          <button v-else class="lp-btn lp-btn-primary lp-btn-sm" @click="goFactory">
            <span>进入工作台</span>
            <ArrowRight :size="16" />
          </button>
        </div>
      </div>
    </header>

    <main id="top">
      <!-- Hero -->
      <section class="lp-hero">
        <div class="lp-container lp-hero-grid">
          <div class="lp-hero-copy">
            <span class="lp-badge">
              <Sparkles :size="14" />
              <span>AI 驱动 · 工程报告智能写作平台</span>
            </span>
            <h1 class="lp-hero-title">
              <template v-if="titleLines.length > 1">
                <span class="lp-title-line">{{ titleLines[0] }}</span>
                <span class="lp-title-line">{{ titleLines[1] }}</span>
              </template>
              <template v-else>{{ infoStore.branding.title }}</template>
            </h1>
            <p class="lp-hero-sub">
              以领域知识库与知识图谱为底座，覆盖资料加工、大纲生成、分章写作到装配交付的报告写作全流程。每一章有据可依，每一稿皆可溯源。
            </p>
            <div class="lp-hero-actions">
              <button class="lp-btn lp-btn-primary" @click="goWrite">
                <PenLine :size="18" />
                <span>开始写作</span>
              </button>
              <a class="lp-btn lp-btn-outline" href="#workflow">
                <span>了解工作流程</span>
                <ArrowDown :size="18" />
              </a>
            </div>
            <ul class="lp-hero-points">
              <li><Check :size="14" /><span>检索增强生成</span></li>
              <li><Check :size="14" /><span>知识图谱关联</span></li>
              <li><Check :size="14" /><span>标准规范校验</span></li>
            </ul>
          </div>

          <div class="lp-hero-visual" aria-hidden="true">
            <div class="lp-window">
              <div class="lp-window-bar">
                <span class="lp-dot"></span>
                <span class="lp-dot"></span>
                <span class="lp-dot"></span>
                <span class="lp-window-title">工程报告工作台</span>
              </div>
              <div class="lp-window-body">
                <aside class="lp-chapters">
                  <p class="lp-chapters-title">报告章节</p>
                  <div class="lp-chapter" v-for="ch in demoChapters" :key="ch.name">
                    <span class="lp-chapter-dot" :class="ch.state"></span>
                    <span>{{ ch.name }}</span>
                  </div>
                </aside>
                <div class="lp-doc">
                  <div class="lp-doc-heading"></div>
                  <div
                    class="lp-line"
                    v-for="(w, i) in demoLines"
                    :key="i"
                    :style="{ width: w + '%' }"
                  ></div>
                  <div class="lp-doc-cite">
                    <BookOpen :size="12" />
                    <span>引自领域知识库 · 章节级溯源</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="lp-float lp-float-tr">
              <ShieldCheck :size="14" />
              <span>规范校验通过</span>
            </div>
            <div class="lp-float lp-float-bl">
              <Layers :size="14" />
              <span>装配完成 · assembled</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Metrics -->
      <section class="lp-metrics">
        <div class="lp-container lp-metrics-grid">
          <div
            class="lp-metric reveal"
            v-for="(m, i) in metrics"
            :key="m.value"
            :style="{ '--stagger': i }"
          >
            <span class="lp-metric-ticks" aria-hidden="true"></span>
            <span class="lp-metric-icon">
              <component :is="m.icon" :size="19" />
            </span>
            <p class="lp-metric-value">{{ m.value }}</p>
            <p class="lp-metric-desc">{{ m.desc }}</p>
          </div>
        </div>
      </section>

      <!-- Features -->
      <section id="features" class="lp-section">
        <div class="lp-container">
          <div class="lp-section-head reveal">
            <p class="lp-kicker">核心能力</p>
            <h2>从知识到成稿，一个平台闭环</h2>
            <p class="lp-section-sub">
              知识加工与报告写作两条主线深度耦合，让领域知识持续沉淀为写作生产力。
            </p>
          </div>
          <div class="lp-features-grid">
            <article
              class="lp-feature reveal"
              v-for="(f, i) in features"
              :key="f.title"
              :style="{ '--stagger': i }"
            >
              <span class="lp-feature-icon">
                <component :is="f.icon" :size="22" />
              </span>
              <h3>{{ f.title }}</h3>
              <p>{{ f.desc }}</p>
            </article>
          </div>
        </div>
      </section>

      <!-- Workflow -->
      <section id="workflow" class="lp-section lp-section-tint">
        <div class="lp-container">
          <div class="lp-section-head reveal">
            <p class="lp-kicker">工作流程</p>
            <h2>四步，从资料到报告</h2>
            <p class="lp-section-sub">
              全过程人机协同：机器负责加工与起草，关键节点由专家复核把关。
            </p>
          </div>
          <ol class="lp-steps">
            <li
              class="lp-step reveal"
              v-for="(s, i) in steps"
              :key="s.title"
              :style="{ '--stagger': i }"
            >
              <div class="lp-step-head">
                <span class="lp-step-icon">
                  <component :is="s.icon" :size="20" />
                </span>
                <span class="lp-step-num">{{ s.num }}</span>
              </div>
              <h3>{{ s.title }}</h3>
              <p>{{ s.desc }}</p>
            </li>
          </ol>
        </div>
      </section>

      <!-- Scenarios -->
      <section id="scenarios" class="lp-section">
        <div class="lp-container">
          <div class="lp-section-head reveal">
            <p class="lp-kicker">应用场景</p>
            <h2>面向工程报告的专业写作场景</h2>
            <p class="lp-section-sub">
              模板、实体与规范知识按领域组织，可为一个领域定制，也可复制到更多领域。
            </p>
          </div>
          <div class="lp-scenarios-grid">
            <article
              class="lp-scenario reveal"
              v-for="(sc, i) in scenarios"
              :key="sc.title"
              :style="{ '--stagger': i }"
            >
              <div class="lp-scenario-top">
                <span class="lp-scenario-icon">
                  <component :is="sc.icon" :size="20" />
                </span>
                <ArrowUpRight :size="18" class="lp-scenario-arrow" />
              </div>
              <h3>{{ sc.title }}</h3>
              <p>{{ sc.desc }}</p>
            </article>
          </div>
        </div>
      </section>

      <!-- CTA -->
      <section class="lp-cta-wrap">
        <div class="lp-container">
          <div class="lp-cta reveal">
            <h2>让下一份工程报告，从智能写作开始</h2>
            <p>知识加工、大纲生成、分章写作、装配交付，现在即可体验完整流程。</p>
            <div class="lp-cta-actions">
              <button class="lp-btn lp-btn-white" @click="goWrite">
                <Rocket :size="18" />
                <span>开始使用</span>
              </button>
              <button
                v-if="!userStore.isLoggedIn"
                class="lp-btn lp-btn-ghost-inverse"
                @click="goLogin"
              >
                登录系统
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer class="lp-footer">
      <div class="lp-container lp-footer-inner">
        <p>{{ infoStore.footer?.copyright || '© All rights reserved' }}</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import {
  Sparkles,
  ArrowRight,
  ArrowDown,
  ArrowUpRight,
  PenLine,
  ShieldCheck,
  BookOpen,
  ListTree,
  Factory,
  Waypoints,
  Upload,
  Layers,
  FileCheck,
  Database,
  FileText,
  PackageCheck,
  ClipboardCheck,
  FileSearch,
  Tags,
  Milestone,
  Rocket,
  Check
} from '@lucide/vue'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()

// Break the hero title at the phrase boundary (never mid-word); fall back to the raw title
const titleLines = computed(() => {
  const title = infoStore.branding.title || ''
  const at = title.indexOf('工程报告')
  if (at < 0) return [title]
  const cut = at + '工程报告'.length
  return [title.slice(0, cut), title.slice(cut)]
})

// Auth-aware entry: mirrors HomeView goToAgent behavior
const goWrite = async () => {
  if (!userStore.isLoggedIn) {
    sessionStorage.setItem('redirect', '/agent')
    router.push('/login')
    return
  }
  await agentStore.initialize()
  if (userStore.isAdmin && agentStore.defaultAgent?.id) {
    router.push(`/agent/${agentStore.defaultAgent.id}`)
  } else {
    router.push('/agent')
  }
}

const goLogin = () => {
  router.push('/login')
}

const goFactory = () => {
  router.push('/domain-factory')
}

// Report workbench mock data
const demoChapters = [
  { name: '第一章 总论', state: 'done' },
  { name: '第二章 工程分析', state: 'done' },
  { name: '第三章 影响预测', state: 'writing' },
  { name: '第四章 污染防治措施', state: 'todo' },
  { name: '第五章 结论与建议', state: 'todo' }
]
const demoLines = [92, 100, 78, 96, 64, 88, 42]

// Metrics reflect real platform mechanics (not fabricated ops data)
const metrics = [
  { icon: ClipboardCheck, value: '5 步加工', desc: '资料到知识，全程可复核' },
  { icon: Tags, value: '6 大分类', desc: '工程知识结构化入图' },
  { icon: Milestone, value: '3 步流转', desc: '草稿、写作、装配，状态全程可视' },
  { icon: FileSearch, value: '章节级溯源', desc: '引用与依据，逐章可查' }
]

const features = [
  {
    icon: ListTree,
    title: '智能大纲生成',
    desc: '基于领域模板库与历史报告自动生成贴合规范的项目大纲，章节结构可调整、可复用。'
  },
  {
    icon: BookOpen,
    title: '检索增强写作',
    desc: '写作过程深度耦合领域知识库，实时检索知识条目作为依据，段落级引用有据可依。'
  },
  {
    icon: PenLine,
    title: '分章协同写作',
    desc: '编排者统一派发章节任务，多个写手并行产出，章节状态与写作进度全程可视。'
  },
  {
    icon: ShieldCheck,
    title: '规范符合性检查',
    desc: '自动比对标准文号与指标限值，输出符合性矩阵，成稿之前先完成合规自检。'
  },
  {
    icon: Factory,
    title: '领域知识工厂',
    desc: '上传领域资料，经解析、泛化与人工复核，沉淀为可复用的模板与实体知识资产。'
  },
  {
    icon: Waypoints,
    title: '知识图谱关联',
    desc: '工程实体与关系结构化入图，跨报告、跨项目串联领域知识网络，支撑关联检索。'
  }
]

const steps = [
  {
    num: '1',
    icon: Upload,
    title: '上传领域资料',
    desc: '项目资料与历史报告批量上传，自动完成解析与分类。'
  },
  {
    num: '2',
    icon: Database,
    title: '知识加工入库',
    desc: '泛化提取工程实体与模板结构，人工复核后入库沉淀。'
  },
  {
    num: '3',
    icon: FileText,
    title: '智能分章写作',
    desc: '生成项目大纲后按章派发写手，结合知识库逐章成文。'
  },
  {
    num: '4',
    icon: PackageCheck,
    title: '装配成稿交付',
    desc: '合并全部完稿章节，输出完整报告文档，支持溯源审阅。'
  }
]

const scenarios = [
  {
    icon: FileCheck,
    title: '环境影响评价报告',
    desc: '环评章节模板与指标限值库，覆盖工程分析、影响预测与防治措施各章节。'
  },
  {
    icon: ShieldCheck,
    title: '安全评价报告',
    desc: '安全检查表与法规条款关联，标准引用自动校验，降低合规风险。'
  },
  {
    icon: Layers,
    title: '工程可行性研究',
    desc: '多源资料汇总与大纲复用，显著缩短可研报告的成稿周期。'
  },
  {
    icon: Upload,
    title: '领域模板定制',
    desc: '为新领域构建专属模板库与实体体系，将写作能力快速复制到新业务。'
  }
]

const isScrolled = ref(false)

// Only show sections when scrolled into view; skip animation entirely for reduced motion
let revealObserver = null
let onScroll = null

const initReveal = () => {
  const els = document.querySelectorAll('.lp .reveal')
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
  onScroll = () => {
    isScrolled.value = window.scrollY > 8
  }
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})

onUnmounted(() => {
  if (revealObserver) {
    revealObserver.disconnect()
    revealObserver = null
  }
  if (onScroll) {
    window.removeEventListener('scroll', onScroll)
    onScroll = null
  }
})
</script>

<style lang="less" scoped>
.lp {
  --lp-font:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', sans-serif;
  font-family: var(--lp-font);
  color: var(--gray-1000);
  background: var(--gray-0);
  min-height: 100vh;
}

.lp-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}

/* ============ Header ============ */
.lp-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--light-85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid transparent;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;

  &.is-scrolled {
    background: var(--light-95);
    border-bottom-color: var(--gray-150);
  }
}

.lp-header-inner {
  display: flex;
  align-items: center;
  gap: 32px;
  height: 64px;
}

.lp-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: var(--gray-1000);
}

.lp-brand-logo {
  width: 30px;
  height: 30px;
  object-fit: contain;
}

.lp-brand-name {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lp-nav {
  display: flex;
  gap: 28px;
  margin-left: 12px;

  a {
    font-size: 14px;
    color: var(--gray-600);
    text-decoration: none;
    transition: color 0.2s ease;

    &:hover {
      color: var(--main-600);
    }
  }
}

.lp-header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ============ Buttons ============ */
.lp-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 22px;
  border: 1px solid transparent;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  text-decoration: none;
  white-space: nowrap;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;

  &:focus-visible {
    outline: 2px solid var(--main-600);
    outline-offset: 2px;
  }
}

.lp-btn-sm {
  min-height: 38px;
  padding: 0 16px;
  font-size: 14px;
}

.lp-btn-primary {
  background: var(--main-600);
  color: var(--gray-0);

  &:hover {
    background: var(--main-500);
    box-shadow: 0 6px 16px var(--shadow-3);
  }

  &:active {
    background: var(--main-700);
  }
}

.lp-btn-outline {
  border-color: var(--gray-200);
  color: var(--gray-1000);
  background: var(--gray-0);

  &:hover {
    border-color: var(--main-400);
    color: var(--main-700);
  }
}

.lp-btn-ghost {
  background: transparent;
  color: var(--gray-600);

  &:hover {
    color: var(--main-700);
    background: var(--main-50);
  }
}

.lp-btn-white {
  background: var(--gray-0);
  color: var(--main-800);

  &:hover {
    background: var(--main-50);
  }
}

.lp-btn-ghost-inverse {
  border-color: var(--light-50);
  color: var(--gray-0);
  background: transparent;

  &:hover {
    background: var(--light-10);
  }
}

/* ============ Hero ============ */
.lp-hero {
  padding: 72px 0 64px;
  background-image:
    radial-gradient(620px 320px at 88% 0%, var(--main-100), transparent 65%),
    radial-gradient(520px 280px at 4% 100%, var(--second-50), transparent 60%),
    repeating-linear-gradient(
      0deg,
      transparent,
      transparent 31px,
      rgba(24, 144, 255, 0.05) 31px,
      rgba(24, 144, 255, 0.05) 32px
    ),
    repeating-linear-gradient(
      90deg,
      transparent,
      transparent 31px,
      rgba(24, 144, 255, 0.05) 31px,
      rgba(24, 144, 255, 0.05) 32px
    );
}

.lp-hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 56px;
  align-items: center;
}

.lp-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--second-200);
  border-radius: 999px;
  background: var(--second-50);
  color: var(--second-800);
  font-size: 13px;
  font-weight: 600;
}

.lp-hero-title {
  margin: 20px 0 16px;
  font-size: clamp(32px, 4.2vw, 50px);
  line-height: 1.22;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-wrap: balance;
  color: var(--gray-1000);
}

.lp-title-line {
  display: block;
}

.lp-hero-sub {
  margin: 0 0 28px;
  max-width: 520px;
  font-size: 16px;
  line-height: 1.75;
  color: var(--gray-600);
}

.lp-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.lp-hero-points {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  margin: 26px 0 0;
  padding: 0;
  list-style: none;

  li {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--gray-600);

    svg {
      color: var(--main-600);
    }
  }
}

/* Hero visual: CSS-only report workbench mock */
.lp-hero-visual {
  position: relative;
}

.lp-window {
  background: var(--gray-0);
  border: 1px solid var(--gray-200);
  border-radius: 14px;
  box-shadow:
    0 24px 60px var(--shadow-3),
    0 2px 8px var(--shadow-1);
  overflow: hidden;
}

.lp-window-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gray-150);
  background: var(--gray-25);
}

.lp-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--gray-200);

  &:nth-child(1) {
    background: var(--main-200);
  }
  &:nth-child(2) {
    background: var(--second-200);
  }
}

.lp-window-title {
  margin-left: 8px;
  font-size: 12px;
  color: var(--gray-500);
}

.lp-window-body {
  display: grid;
  grid-template-columns: 168px minmax(0, 1fr);
}

.lp-chapters {
  padding: 16px 14px;
  border-right: 1px solid var(--gray-150);
  background: var(--gray-10);
}

.lp-chapters-title {
  margin: 0 0 12px;
  font-size: 11px;
  letter-spacing: 1px;
  color: var(--gray-500);
}

.lp-chapter {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  margin-bottom: 4px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--gray-700);
  white-space: nowrap;
}

.lp-chapter-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--gray-300);

  &.done {
    background: var(--color-success-500);
  }
  &.writing {
    background: var(--main-500);
    box-shadow: 0 0 0 3px var(--main-100);
  }
}

.lp-doc {
  padding: 18px 20px;
}

.lp-doc-heading {
  width: 46%;
  height: 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  background: var(--main-200);
}

.lp-line {
  height: 9px;
  margin-bottom: 10px;
  border-radius: 4px;
  background: var(--gray-100);
}

.lp-doc-cite {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--main-50);
  color: var(--main-700);
  font-size: 11px;
}

.lp-float {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 10px;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  box-shadow: 0 10px 28px var(--shadow-2);
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-700);

  svg {
    color: var(--main-600);
  }
}

.lp-float-tr {
  top: -14px;
  right: -10px;
  color: var(--color-success-700);

  svg {
    color: var(--color-success-500);
  }
}

.lp-float-bl {
  bottom: -14px;
  left: -10px;
}

/* ============ Metrics ============ */
.lp-metrics {
  border-top: 1px solid var(--gray-150);
  border-bottom: 1px solid var(--gray-150);
  background: var(--gray-25);
}

.lp-metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding-top: 36px;
  padding-bottom: 36px;
}

.lp-metric {
  position: relative;
  padding: 2px 28px;

  &:first-child {
    padding-left: 0;
  }

  &:last-child {
    padding-right: 0;
  }

  & + & {
    border-left: 1px solid var(--gray-200);
  }
}

/* Blueprint ruler ticks: small engineering accent */
.lp-metric-ticks {
  display: block;
  width: 46px;
  height: 6px;
  margin-bottom: 16px;
  background: repeating-linear-gradient(90deg, var(--main-200) 0 2px, transparent 2px 8px);
}

.lp-metric-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  margin-bottom: 14px;
  border-radius: 9px;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  color: var(--main-600);
}

.lp-metric-value {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: 0.3px;
  color: var(--gray-1000);
  font-variant-numeric: tabular-nums;
}

.lp-metric-desc {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.65;
  color: var(--gray-600);
}

/* ============ Sections ============ */
.lp-section {
  padding: 88px 0;

  &[id] {
    scroll-margin-top: 76px;
  }
}

.lp-section-tint {
  background: var(--gray-25);
  border-top: 1px solid var(--gray-150);
  border-bottom: 1px solid var(--gray-150);
}

.lp-section-head {
  max-width: 640px;
  margin: 0 auto 52px;
  text-align: center;
}

.lp-kicker {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 3px;
  color: var(--main-600);
}

.lp-section-head h2 {
  margin: 0 0 14px;
  font-size: clamp(26px, 3vw, 34px);
  font-weight: 700;
  color: var(--gray-1000);
}

.lp-section-sub {
  margin: 0;
  font-size: 15px;
  line-height: 1.7;
  color: var(--gray-600);
}

/* Features */
.lp-features-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}

.lp-feature {
  padding: 26px 24px;
  border: 1px solid var(--gray-150);
  border-radius: 12px;
  background: var(--gray-0);
  transition:
    box-shadow 0.25s ease,
    transform 0.25s ease,
    border-color 0.25s ease;

  &:hover {
    transform: translateY(-3px);
    border-color: var(--main-200);
    box-shadow: 0 14px 34px var(--shadow-2);
  }

  h3 {
    margin: 16px 0 8px;
    font-size: 17px;
    font-weight: 700;
  }

  p {
    margin: 0;
    font-size: 14px;
    line-height: 1.7;
    color: var(--gray-600);
  }
}

.lp-feature-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--main-50);
  color: var(--main-600);
}

/* Workflow steps */
.lp-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: step;
}

.lp-step {
  position: relative;
  padding: 22px 20px;
  border-radius: 12px;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);

  & + .lp-step::before {
    content: '';
    position: absolute;
    top: 50%;
    left: -21px;
    width: 22px;
    height: 1px;
    background: var(--gray-300);
  }

  h3 {
    margin: 12px 0 8px;
    font-size: 16px;
    font-weight: 700;
  }

  p {
    margin: 0;
    font-size: 13.5px;
    line-height: 1.7;
    color: var(--gray-600);
  }
}

.lp-step-head {
  position: relative;
  width: 44px;
}

.lp-step-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--main-50);
  color: var(--main-600);
}

.lp-step-num {
  position: absolute;
  top: -8px;
  right: -12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 6px;
  border-radius: 999px;
  border: 2px solid var(--gray-0);
  background: var(--main-600);
  color: var(--gray-0);
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* Scenarios */
.lp-scenarios-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;
}

.lp-scenario {
  padding: 24px 22px;
  border: 1px solid var(--gray-150);
  border-radius: 12px;
  background: var(--gray-0);
  transition:
    box-shadow 0.25s ease,
    transform 0.25s ease,
    border-color 0.25s ease;

  &:hover {
    transform: translateY(-3px);
    border-color: var(--second-200);
    box-shadow: 0 14px 34px var(--shadow-2);

    .lp-scenario-arrow {
      color: var(--second-500);
      transform: translate(2px, -2px);
    }
  }

  h3 {
    margin: 14px 0 8px;
    font-size: 16px;
    font-weight: 700;
  }

  p {
    margin: 0;
    font-size: 13.5px;
    line-height: 1.7;
    color: var(--gray-600);
  }
}

.lp-scenario-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.lp-scenario-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--second-50);
  color: var(--second-600);
}

.lp-scenario-arrow {
  color: var(--gray-300);
  transition:
    color 0.25s ease,
    transform 0.25s ease;
}

/* ============ CTA ============ */
.lp-cta-wrap {
  padding: 40px 0 88px;
}

.lp-cta {
  padding: 56px 40px;
  border-radius: 16px;
  text-align: center;
  color: var(--gray-0);
  background: linear-gradient(135deg, var(--main-800) 0%, var(--main-600) 100%);
  box-shadow: 0 24px 60px rgba(9, 109, 217, 0.35);

  h2 {
    margin: 0 0 12px;
    font-size: clamp(24px, 2.8vw, 32px);
    font-weight: 700;
  }

  p {
    margin: 0 0 28px;
    font-size: 15px;
    color: var(--light-85);
  }
}

.lp-cta-actions {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 14px;
}

/* ============ Footer ============ */
.lp-footer {
  border-top: 1px solid var(--gray-150);
  padding: 28px 0;
}

.lp-footer-inner {
  text-align: center;

  p {
    margin: 0;
    font-size: 13px;
    color: var(--gray-500);
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
  .reveal {
    opacity: 1;
    transform: none;
    transition: none;
  }
}

/* ============ Responsive ============ */
@media (max-width: 1024px) {
  .lp-hero-grid {
    grid-template-columns: 1fr;
    gap: 48px;
  }

  .lp-hero-sub {
    max-width: 640px;
  }

  .lp-features-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .lp-steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .lp-step + .lp-step::before {
    display: none;
  }

  .lp-scenarios-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .lp-metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 28px 24px;
  }

  .lp-metric {
    padding: 0;
  }

  .lp-metric + .lp-metric {
    border-left: none;
  }
}

@media (max-width: 767px) {
  .lp-nav {
    display: none;
  }

  .lp-header .lp-btn-ghost {
    display: none;
  }

  .lp-brand-name {
    font-size: 15px;
  }

  .lp-hero {
    padding: 48px 0 56px;
  }

  .lp-hero-actions .lp-btn {
    flex: 1 1 auto;
  }

  .lp-features-grid,
  .lp-steps,
  .lp-scenarios-grid,
  .lp-metrics-grid {
    grid-template-columns: 1fr;
  }

  .lp-metric + .lp-metric {
    border-top: 1px solid var(--gray-200);
    padding-top: 22px;
  }

  .lp-section {
    padding: 64px 0;
  }

  .lp-cta {
    padding: 40px 24px;
  }

  .lp-float-tr {
    right: 0;
  }

  .lp-float-bl {
    left: 0;
  }
}
</style>
