<template>
  <div class="home-container">
    <!-- 动态背景装饰 -->
    <div class="bg-decoration">
      <div class="gradient-orb orb-1"></div>
      <div class="gradient-orb orb-2"></div>
      <div class="gradient-orb orb-3"></div>
      <div class="grid-pattern"></div>
    </div>

    <div class="hero-section">
      <div class="glass-header">
        <div class="logo">
          <img :src="infoStore.organization.logo" :alt="infoStore.organization.name" class="logo-img" />
          <span class="logo-text">{{ infoStore.organization.name }}</span>
        </div>
        <nav class="nav-links">
          <router-link to="/dashboard" class="nav-link" v-if="userStore.isLoggedIn && userStore.isAdmin">
            <span>Dashboard</span>
          </router-link>
          <router-link to="/database" class="nav-link" v-if="userStore.isLoggedIn">
            <span>知识库</span>
          </router-link>
          <router-link to="/graph" class="nav-link" v-if="userStore.isLoggedIn && userStore.isAdmin">
            <span>知识图谱</span>
          </router-link>
          <router-link to="/extensions" class="nav-link" v-if="userStore.isLoggedIn && userStore.isSuperAdmin">
            <span>扩展</span>
          </router-link>
        </nav>
        <div class="header-actions">
          <UserInfoComponent :show-button="true" />
        </div>
      </div>

      <div class="hero-layout">
        <div class="hero-content">
          <div class="hero-badge">
            <Sparkles :size="16" />
            <span>AI 驱动的知识平台</span>
          </div>
          <h1 class="title">
            <span class="title-line">{{ infoStore.branding.title }}</span>
            <span class="title-gradient-underline"></span>
          </h1>
          <p class="subtitle">{{ infoStore.branding.subtitle }}</p>
          <div class="hero-actions">
            <button class="button-base primary" @click="goToAgent">
              <Rocket :size="20" />
              <span>开始体验</span>
            </button>
            <button class="button-base secondary" @click="goToDomainFactory">
              <Factory :size="20" />
              <span>知识加工</span>
            </button>
          </div>
        </div>

        <div class="insight-panel" v-if="featureCards.length">
          <div class="stat-card" v-for="(card, index) in featureCards" :key="card.label" :style="{ animationDelay: `${index * 0.1}s` }">
            <div class="stat-icon-wrapper" v-if="card.icon">
              <span class="stat-icon">
                <component :is="card.icon" />
              </span>
            </div>
            <div class="stat-content">
              <p class="stat-value">{{ card.value }}</p>
              <p class="stat-label">{{ card.label }}</p>
              <p class="stat-description" v-if="card.description">{{ card.description }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="section action-section" v-if="actionLinks.length">
      <div class="section-header">
        <h2>快速访问</h2>
        <p>探索平台核心功能模块</p>
      </div>
      <div class="action-grid">
        <a
          v-for="(action, index) in actionLinks"
          :key="action.name"
          class="action-card"
          :href="action.url"
          :target="action.isExternal ? '_blank' : undefined"
          :rel="action.isExternal ? 'noopener noreferrer' : undefined"
          @click="!action.isExternal && handleInternalLink($event, action.url)"
          :style="{ animationDelay: `${index * 0.05}s` }"
        >
          <div class="action-icon-wrapper">
            <span class="action-icon" v-if="action.icon">
              <component :is="action.icon" />
            </span>
          </div>
          <div class="action-meta">
            <p class="action-title">{{ action.name }}</p>
            <p class="action-url">{{ action.url }}</p>
          </div>
          <div class="action-arrow">
            <ArrowRight :size="18" />
          </div>
        </a>
      </div>
    </div>

    <footer class="footer">
      <div class="footer-content">
        <p class="copyright">{{ infoStore.footer?.copyright || '© 2025 All rights reserved' }}</p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import UserInfoComponent from '@/components/UserInfoComponent.vue'
import {
  Sparkles,
  Rocket,
  Factory,
  ArrowRight,
  BarChart3,
  LibraryBig,
  Waypoints,
  FileText,
  Layers,
  Database,
  Bot,
  Settings
} from 'lucide-vue-next'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()

const goToAgent = async () => {
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

const goToDomainFactory = () => {
  if (!userStore.isLoggedIn) {
    sessionStorage.setItem('redirect', '/domain-factory')
    router.push('/login')
    return
  }
  router.push('/domain-factory')
}

const goToDashboard = () => {
  if (!userStore.isLoggedIn) {
    sessionStorage.setItem('redirect', '/dashboard')
    router.push('/login')
    return
  }
  router.push('/dashboard')
}

const handleInternalLink = (event, url) => {
  event.preventDefault()
  if (!userStore.isLoggedIn) {
    sessionStorage.setItem('redirect', url)
    router.push('/login')
    return
  }
  router.push(url)
}

onMounted(async () => {
  await infoStore.loadInfoConfig()
})

const iconKey = (value) => (typeof value === 'string' ? value.toLowerCase() : '')

const featureIconMap = {
  stars: BarChart3,
  issues: LibraryBig,
  resolved: FileText,
  commits: Database,
  license: Settings,
  default: BarChart3
}

const featureCards = computed(() => {
  const list = Array.isArray(infoStore.features) ? infoStore.features : []
  return list
    .map((item) => {
      if (typeof item === 'string') {
        return {
          label: item,
          value: '',
          description: '',
          icon: featureIconMap.default
        }
      }

      const key = iconKey(item.icon || item.type)
      return {
        label: item.label || item.name || '',
        value: item.value || '',
        description: item.description || '',
        icon: featureIconMap[key] || featureIconMap.default
      }
    })
    .filter((item) => item.label || item.value || item.description)
})

const actionLinks = computed(() => {
  const links = []

  links.push({
    name: 'Dashboard',
    url: '/dashboard',
    icon: BarChart3,
    isExternal: false
  })

  links.push({
    name: '知识库',
    url: '/database',
    icon: LibraryBig,
    isExternal: false
  })

  links.push({
    name: '知识图谱',
    url: '/graph',
    icon: Waypoints,
    isExternal: false
  })

  links.push({
    name: '智能问答',
    url: '/agent',
    icon: Bot,
    isExternal: false
  })

  links.push({
    name: '扩展中心',
    url: '/extensions',
    icon: Layers,
    isExternal: false
  })

  return links
})
</script>

<style scoped lang="less">
.home-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #fafcfd 0%, #f5f7f7 100%);
  position: relative;
  overflow-x: hidden;
}

/* 动态背景装饰 */
.bg-decoration {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.gradient-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.3;
  animation: float 20s ease-in-out infinite;
}

.orb-1 {
  width: 500px;
  height: 500px;
  background: linear-gradient(135deg, var(--main-300), var(--main-500));
  top: -200px;
  right: -100px;
  animation-delay: 0s;
}

.orb-2 {
  width: 400px;
  height: 400px;
  background: linear-gradient(135deg, var(--color-info-400), var(--color-accent-500));
  bottom: -150px;
  left: -100px;
  animation-delay: 5s;
}

.orb-3 {
  width: 350px;
  height: 350px;
  background: linear-gradient(135deg, var(--color-secondary-400), var(--main-400));
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation-delay: 10s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(30px, -30px) scale(1.1);
  }
  66% {
    transform: translate(-20px, 20px) scale(0.9);
  }
}

.grid-pattern {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-image:
    linear-gradient(var(--gray-200) 1px, transparent 1px),
    linear-gradient(90deg, var(--gray-200) 1px, transparent 1px);
  background-size: 50px 50px;
  opacity: 0.3;
}

.hero-section {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
}

.glass-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 2rem;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.03);

  .logo {
    display: flex;
    align-items: center;
    gap: 0.75rem;

    .logo-img {
      height: 36px;
      width: 36px;
      object-fit: contain;
      border-radius: 8px;
    }

    .logo-text {
      font-size: 1.25rem;
      font-weight: 700;
      background: linear-gradient(135deg, var(--main-color) 0%, var(--main-bright) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
  }

  .nav-links {
    display: flex;
    gap: 0.5rem;

    .nav-link {
      color: var(--gray-700);
      text-decoration: none;
      font-weight: 500;
      padding: 0.5rem 1rem;
      border-radius: 0.5rem;
      transition: all 0.2s;

      &:hover {
        color: var(--main-color);
        background: var(--main-50);
      }

      &.router-link-active {
        color: var(--main-color);
        background: var(--main-100);
      }
    }
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
}

.hero-layout {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8rem 2rem 4rem;
  gap: 4rem;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.hero-content {
  flex: 1;
  max-width: 600px;
  animation: fadeInUp 0.8s ease-out;

  .hero-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: linear-gradient(135deg, var(--main-100), var(--main-200));
    color: var(--main-color);
    border-radius: 2rem;
    font-size: 0.875rem;
    font-weight: 600;
    margin-bottom: 1.5rem;
    animation: pulse 2s ease-in-out infinite;
  }

  .title {
    position: relative;
    display: inline-block;
    margin-bottom: 1.5rem;

    .title-line {
      font-size: 3.5rem;
      font-weight: 800;
      line-height: 1.2;
      color: var(--gray-700);
      display: block;
      letter-spacing: -0.02em;
    }

    .title-gradient-underline {
      position: absolute;
      bottom: -8px;
      left: 0;
      width: 100%;
      height: 8px;
      background: linear-gradient(90deg, var(--main-color), var(--main-bright), var(--color-accent-500));
      border-radius: 4px;
      animation: expandWidth 1s ease-out 0.3s both;
    }
  }

  .subtitle {
    font-size: 1.25rem;
    color: var(--gray-600);
    margin-bottom: 2.5rem;
    line-height: 1.8;
  }

  .hero-actions {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.05);
  }
}

@keyframes expandWidth {
  from {
    width: 0;
  }
  to {
    width: 100%;
  }
}

.button-base {
  padding: 1rem 2rem;
  border-radius: 1rem;
  font-size: 1rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.3);
    transform: translate(-50%, -50%);
    transition: width 0.6s, height 0.6s;
  }

  &:hover::before {
    width: 300px;
    height: 300px;
  }

  &.primary {
    background: linear-gradient(135deg, var(--main-color) 0%, var(--main-bright) 100%);
    color: white;
    box-shadow: 0 8px 24px rgba(24, 144, 255, 0.3);

    &:hover {
      transform: translateY(-3px);
      box-shadow: 0 12px 32px rgba(24, 144, 255, 0.4);
    }

    &:active {
      transform: translateY(-1px);
    }
  }

  &.secondary {
    background: white;
    color: var(--main-color);
    border: 2px solid var(--main-color);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);

    &:hover {
      background: var(--main-50);
      transform: translateY(-3px);
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
    }

    &:active {
      transform: translateY(-1px);
    }
  }
}

.doc-text-link {
  display: inline-flex;
  align-items: center;
  color: var(--main-color);
  font-weight: 600;
  text-decoration: none;
  border-bottom: 1px dashed var(--main-300);
  padding-bottom: 0.15rem;
  transition: color 0.2s ease, border-color 0.2s ease;

  &:hover {
    color: var(--main-700);
    border-color: var(--main-500);
  }
}

.insight-panel {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
  max-width: 500px;
}

.stat-card {
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  border-radius: 1.25rem;
  padding: 1.75rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid rgba(255, 255, 255, 0.8);
  animation: fadeInUp 0.6s ease-out both;

  &:hover {
    transform: translateY(-8px) scale(1.02);
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.12);
    border-color: var(--main-300);
  }

  .stat-icon-wrapper {
    margin-bottom: 1rem;

    .stat-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 48px;
      height: 48px;
      border-radius: 1rem;
      background: linear-gradient(135deg, var(--main-100) 0%, var(--main-300) 100%);
      color: var(--main-color);
      box-shadow: 0 4px 12px rgba(24, 144, 255, 0.2);
    }
  }

  .stat-content {
    .stat-value {
      font-size: 2.25rem;
      font-weight: 800;
      color: var(--gray-700);
      margin: 0 0 0.5rem 0;
      line-height: 1;
    }

    .stat-label {
      font-size: 0.875rem;
      color: var(--gray-600);
      margin: 0 0 0.5rem 0;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .stat-description {
      font-size: 0.8rem;
      color: var(--gray-500);
      margin: 0;
      line-height: 1.5;
    }
  }
}

.section {
  padding: 5rem 2rem;
  max-width: 1400px;
  margin: 0 auto;
  position: relative;
  z-index: 1;
}

.section-header {
  text-align: center;
  margin-bottom: 3rem;

  h2 {
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--gray-700);
    margin-bottom: 0.75rem;
  }

  p {
    font-size: 1.125rem;
    color: var(--gray-600);
    margin: 0;
  }
}

.action-section {
  background: transparent;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
}

.action-card {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding: 1.75rem;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  border-radius: 1.25rem;
  text-decoration: none;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
  position: relative;
  overflow: hidden;
  animation: fadeInUp 0.6s ease-out both;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: linear-gradient(180deg, var(--main-color), var(--main-bright));
    transform: scaleY(0);
    transition: transform 0.3s ease;
  }

  &:hover {
    transform: translateX(8px);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.1);
    border-color: var(--main-300);

    &::before {
      transform: scaleY(1);
    }

    .action-arrow {
      transform: translateX(4px);
    }
  }

  .action-icon-wrapper {
    .action-icon {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 56px;
      height: 56px;
      border-radius: 1rem;
      background: linear-gradient(135deg, var(--main-100) 0%, var(--main-300) 100%);
      color: var(--main-color);
      flex-shrink: 0;
      box-shadow: 0 4px 12px rgba(24, 144, 255, 0.2);
    }
  }

  .action-meta {
    flex: 1;
  }

  .action-title {
    font-size: 1.125rem;
    font-weight: 700;
    color: var(--gray-700);
    margin: 0 0 0.375rem 0;
  }

  .action-url {
    font-size: 0.875rem;
    color: var(--gray-500);
    margin: 0;
  }

  .action-arrow {
    color: var(--main-color);
    transition: transform 0.3s ease;
  }
}

.footer {
  background: var(--gray-1000);
  color: white;
  padding: 2.5rem 2rem;
  text-align: center;
  position: relative;
  z-index: 1;

  .footer-content {
    max-width: 1400px;
    margin: 0 auto;
  }

  .copyright {
    margin: 0;
    color: var(--gray-400);
    font-size: 0.875rem;
  }
}

@media (max-width: 1024px) {
  .hero-layout {
    flex-direction: column;
    gap: 3rem;
    padding-top: 6rem;
  }

  .hero-content {
    text-align: center;

    .title .title-line {
      font-size: 2.75rem;
    }

    .hero-actions {
      justify-content: center;
    }
  }

  .insight-panel {
    max-width: 100%;
  }
}

@media (max-width: 768px) {
  .glass-header {
    flex-wrap: wrap;
    gap: 1rem;
    padding: 1rem;

    .nav-links {
      order: 3;
      width: 100%;
      justify-content: center;
      gap: 0.25rem;

      .nav-link {
        padding: 0.5rem 0.75rem;
        font-size: 0.875rem;
      }
    }
  }

  .hero-content {
    .title .title-line {
      font-size: 2rem;
    }

    .subtitle {
      font-size: 1rem;
    }
  }

  .insight-panel {
    grid-template-columns: 1fr;
  }

  .action-grid {
    grid-template-columns: 1fr;
  }

  .section {
    padding: 3rem 1rem;
  }

  .section-header h2 {
    font-size: 1.75rem;
  }
}
</style>
