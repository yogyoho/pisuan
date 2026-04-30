import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { brandApi } from '@/apis/system_api'

export const useInfoStore = defineStore('info', () => {
  // 状态
  const infoConfig = ref({})
  const isLoading = ref(false)
  const isLoaded = ref(false)
  const debugMode = ref(false)

  // 计算属性 - 组织信息
  const organization = computed(
    () =>
      infoConfig.value.organization || {
        name: 'Pisuan-Know',
        logo: '/favicon.svg',
        avatar: '/avatar.svg'
      }
  )

  // 计算属性 - 品牌信息
  const branding = computed(
    () =>
      infoConfig.value.branding || {
        name: 'Pisuan-Know',
        title: 'Pisuan-Know',
        subtitle: '大模型驱动的知识平台，融合知识库与知识图谱',
        subtitles: []
      }
  )

  // 计算属性 - 功能特性
  const features = computed(
    () =>
      infoConfig.value.features || [
        {
          label: '知识库',
          value: '1000+',
          description: '文档和知识点',
          icon: 'library'
        },
        {
          label: '智能问答',
          value: '50+',
          description: 'AI Agent 能力',
          icon: 'bot'
        },
        {
          label: '知识图谱',
          value: '500+',
          description: '实体关系连接',
          icon: 'graph'
        },
        {
          label: '扩展技能',
          value: '20+',
          description: 'MCP 工具集成',
          icon: 'extension'
        }
      ]
  )

  const actions = computed(
    () =>
      infoConfig.value.actions || [
        {
          name: '文档中心',
          icon: 'docs',
          url: 'https://xerrors.github.io/Yuxi/'
        },
        {
          name: '演示视频',
          icon: 'video',
          url: 'https://www.bilibili.com/video/xxx'
        },
        {
          name: '提交反馈',
          icon: 'feedback',
          url: 'https://github.com/xerrors/Yuxi/issues'
        }
      ]
  )

  // 计算属性 - 页脚信息
  const footer = computed(
    () =>
      infoConfig.value.footer || {
        copyright: '© 2025 Pisuan-Know All rights reserved'
      }
  )

  // 动作方法
  function setInfoConfig(newConfig) {
    infoConfig.value = newConfig
    isLoaded.value = true
  }

  function toggleDebugMode() {
    debugMode.value = !debugMode.value
  }

  async function loadInfoConfig(force = false) {
    // 如果已经加载过且不强制刷新，则不重新加载
    if (isLoaded.value && !force) {
      return infoConfig.value
    }

    try {
      isLoading.value = true
      const response = await brandApi.getInfoConfig()

      if (response.success && response.data) {
        setInfoConfig(response.data)
        console.debug('信息配置加载成功:', response.data)
        return response.data
      } else {
        console.warn('信息配置加载失败，使用默认配置')
        return null
      }
    } catch (error) {
      console.error('加载信息配置时发生错误:', error)
      return null
    } finally {
      isLoading.value = false
    }
  }

  return {
    // 状态
    infoConfig,
    isLoading,
    isLoaded,
    debugMode,

    // 计算属性
    organization,
    branding,
    footer,

    // 方法
    toggleDebugMode,
    loadInfoConfig
  }
})
