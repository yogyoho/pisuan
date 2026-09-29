import { ref } from 'vue'
import { defineStore } from 'pinia'
import { theme } from 'ant-design-vue'

export const useThemeStore = defineStore('theme', () => {
  // 从 localStorage 读取保存的主题，默认为浅色
  const isDark = ref(localStorage.getItem('theme') === 'dark')

  // [pisuan-custom] 公共主题配置 - 青云素雅主题 (Tailwind indigo-600)：主色与字体均为 pisuan 定制（上游默认拂晓蓝 #1890ff + 系统字体栈），同步时保留
  const commonTheme = {
    token: {
      fontFamily:
        '"Inter Variable", "Inter", "PingFang SC", "Noto Sans SC", "Microsoft Yahei", "微软雅黑", Arial, sans-serif',
      colorPrimary: '#4f46e5', // [pisuan-custom] 青云素雅：AntD token 需参与主色派生计算，var() 不解析
      colorLink: 'var(--main-color)',
      colorLinkHover: 'var(--main-600)',
      colorLinkActive: 'var(--main-800)',
      borderRadius: 10,
      wireframe: false
    }
  }

  // 浅色主题配置
  const lightTheme = {
    ...commonTheme
  }

  // 深色主题配置（shadcn zinc 暗色基准，主色提亮为 indigo-500）
  const darkTheme = {
    ...commonTheme,
    token: {
      ...commonTheme.token,
      // [pisuan-custom] 暗色主色提亮为 indigo-500（上游 darkAlgorithm 不覆盖主色），同步时保留
      colorPrimary: '#6366f1' // [pisuan-custom] 青云素雅：同上，AntD token 字面值，var() 不解析
    },
    algorithm: theme.darkAlgorithm
  }

  // 当前主题配置
  const currentTheme = ref(isDark.value ? darkTheme : lightTheme)

  // 切换主题
  function toggleTheme() {
    setTheme(!isDark.value)
  }

  // 设置主题
  function setTheme(dark) {
    isDark.value = dark
    currentTheme.value = dark ? darkTheme : lightTheme
    localStorage.setItem('theme', dark ? 'dark' : 'light')
    updateDocumentTheme()
  }

  // 更新 document 的主题类
  function updateDocumentTheme() {
    if (isDark.value) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  // 初始化时设置主题
  updateDocumentTheme()

  return {
    isDark,
    currentTheme,
    toggleTheme,
    setTheme
  }
})
