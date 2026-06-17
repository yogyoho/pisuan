<template>
  <div class="login-view" :class="{ 'has-alert': serverStatus === 'error' }">
    <!-- 服务状态提示 -->
    <div v-if="serverStatus === 'error'" class="server-status-alert">
      <div class="alert-content">
        <exclamation-circle-outlined class="alert-icon" />
        <div class="alert-text">
          <div class="alert-title">服务端连接失败</div>
          <div class="alert-message">{{ serverError }}</div>
        </div>
        <a-button type="link" size="small" @click="checkServerHealth" :loading="healthChecking">
          重试
        </a-button>
      </div>
    </div>

    <div class="login-top-action">
      <a-button type="text" size="small" class="back-home-btn" @click="goHome"> 返回首页 </a-button>
    </div>

    <div class="login-layout">
      <!-- 左侧图片区域 -->
      <div class="login-image-section">
        <img :src="loginBgImage" alt="登录背景" class="login-bg-image" />
        <div class="image-overlay">
          <div class="brand-info">
            <h1 class="brand-title">{{ brandName }}</h1>
            <p class="brand-subtitle">{{ brandSubtitle }}</p>
            <p class="brand-description">{{ brandDescription }}</p>
          </div>
          <div class="brand-copyright">
            <p>
              {{ infoStore.footer?.copyright || '吉林化工工程有限公司' }}.
              {{ infoStore.branding?.copyright || '版权所有' }}
            </p>
          </div>
        </div>
      </div>

      <!-- 右侧登录表单区域 -->
      <div class="login-form-section">
        <div class="login-container">
          <header class="login-header">
            <p class="login-title">欢迎登录</p>
            <h1 class="login-brand">{{ brandName }}</h1>
            <p v-if="!isFirstRun && brandSubtitle" class="login-subtitle">{{ brandSubtitle }}</p>
          </header>

          <div class="login-content" :class="{ 'is-initializing': isFirstRun }">
            <!-- 初始化管理员表单 -->
            <div v-if="isFirstRun" class="login-form login-form--init">
              <h2>系统初始化，请创建超级管理员</h2>
              <a-form :model="adminForm" @finish="handleInitialize" layout="vertical">
                <a-form-item
                  label="用户ID"
                  name="user_id"
                  :rules="[
                    { required: true, message: '请输入用户ID' },
                    {
                      pattern: /^[a-zA-Z0-9_]+$/,
                      message: '用户ID只能包含字母、数字和下划线'
                    },
                    {
                      min: 3,
                      max: 20,
                      message: '用户ID长度必须在3-20个字符之间'
                    }
                  ]"
                >
                  <a-input
                    v-model:value="adminForm.user_id"
                    placeholder="请输入用户ID（3-20个字符）"
                    :maxlength="20"
                  />
                </a-form-item>

                <a-form-item
                  label="手机号（可选）"
                  name="phone_number"
                  :rules="[
                    {
                      validator: async (rule, value) => {
                        if (!value || value.trim() === '') {
                          return
                        }
                        const phoneRegex = /^1[3-9]\d{9}$/
                        if (!phoneRegex.test(value)) {
                          throw new Error('请输入正确的手机号格式')
                        }
                      }
                    }
                  ]"
                >
                  <a-input
                    v-model:value="adminForm.phone_number"
                    placeholder="可用于登录，可不填写"
                    :max-length="11"
                  />
                </a-form-item>

                <a-form-item
                  label="密码"
                  name="password"
                  :rules="[{ required: true, message: '请输入密码' }]"
                >
                  <a-input-password v-model:value="adminForm.password" prefix-icon="lock" />
                </a-form-item>

                <a-form-item
                  label="确认密码"
                  name="confirmPassword"
                  :rules="[
                    { required: true, message: '请确认密码' },
                    { validator: validateConfirmPassword }
                  ]"
                >
                  <a-input-password v-model:value="adminForm.confirmPassword" prefix-icon="lock" />
                </a-form-item>

                <a-form-item>
                  <a-button type="primary" html-type="submit" :loading="loading" block
                    >创建管理员账户</a-button
                  >
                </a-form-item>
              </a-form>
            </div>

            <!-- 登录表单 -->
            <div v-else class="login-form">
              <a-form :model="loginForm" @finish="handleLogin" layout="vertical">
                <a-form-item
                  label="登录账号"
                  name="loginId"
                  :rules="[{ required: true, message: '请输入用户ID或手机号' }]"
                >
                  <a-input v-model:value="loginForm.loginId" placeholder="用户ID或手机号">
                    <template #prefix>
                      <user-outlined />
                    </template>
                  </a-input>
                </a-form-item>

                <a-form-item
                  label="密码"
                  name="password"
                  :rules="[{ required: true, message: '请输入密码' }]"
                >
                  <a-input-password v-model:value="loginForm.password">
                    <template #prefix>
                      <lock-outlined />
                    </template>
                  </a-input-password>
                </a-form-item>

                <a-form-item>
                  <a-button
                    type="primary"
                    html-type="submit"
                    :loading="loading"
                    block
                  >
                    登录
                  </a-button>
                </a-form-item>

                <!-- OIDC 登录选项 -->
                <div v-if="oidcChecking || oidcEnabled" class="third-party-login">
                  <div class="divider">
                    <span>其他登录方式</span>
                  </div>
                  <div class="login-icons">
                    <!-- 检查中显示骨架屏 -->
                    <div v-if="oidcChecking" class="login-skeleton">
                      <a-skeleton-button block size="large" :active="true" />
                    </div>
                    <!-- 检查完成后显示按钮 -->
                    <a-button
                      v-else
                      type="default"
                      size="large"
                      block
                      :loading="oidcLoading"
                      @click="handleOIDCLogin"
                    >
                      <template #icon>
                        <key-outlined />
                      </template>
                      {{ oidcButtonText }}
                    </a-button>
                  </div>
                </div>
              </a-form>
            </div>

            <!-- 错误提示 -->
            <div v-if="errorMessage" class="error-message">
              {{ errorMessage }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import { message } from 'ant-design-vue'
import { healthApi } from '@/apis/system_api'
import { authApi } from '@/apis/auth_api'
import {
  UserOutlined,
  LockOutlined,
  KeyOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()

// 品牌展示数据
const loginBgImage = computed(() => {
  return infoStore.organization?.login_bg || '/login-bg.jpg'
})
const brandName = computed(() => {
  const rawName = infoStore.branding?.name ?? ''
  const trimmed = rawName.trim()
  return trimmed || 'Pisuan-Know'
})
const brandSubtitle = computed(() => {
  const rawSubtitle = infoStore.branding?.subtitle ?? ''
  const trimmed = rawSubtitle.trim()
  return trimmed || '大模型驱动的知识库管理工具'
})
const brandDescription = computed(() => {
  const rawDescription = infoStore.branding?.description ?? ''
  const trimmed = rawDescription.trim()
  return trimmed || '结合知识库与知识图谱，提供更准确、更全面的回答'
})

// 状态
const isFirstRun = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const serverStatus = ref('loading')
const serverError = ref('')
const healthChecking = ref(false)

// OIDC 相关状态
const oidcEnabled = ref(false)
const oidcLoading = ref(false)
const oidcChecking = ref(true)
const oidcButtonText = ref('OIDC 登录')

// 登录表单
const loginForm = reactive({
  loginId: '',
  password: ''
})

// 管理员初始化表单
const adminForm = reactive({
  user_id: '',
  password: '',
  confirmPassword: '',
  phone_number: ''
})

const goHome = () => {
  router.push('/')
}

// 密码确认验证
const validateConfirmPassword = async (rule, value) => {
  if (value === '') {
    throw new Error('请确认密码')
  }
  if (value !== adminForm.password) {
    throw new Error('两次输入的密码不一致')
  }
}

// 处理登录
const handleLogin = async () => {
  try {
    loading.value = true
    errorMessage.value = ''

    await userStore.login({
      loginId: loginForm.loginId,
      password: loginForm.password
    })

    message.success('登录成功')

    const redirectPath = sessionStorage.getItem('redirect') || '/'
    sessionStorage.removeItem('redirect')

    if (redirectPath === '/') {
      try {
        await agentStore.initialize()
        router.push('/agent')
      } catch (error) {
        console.error('获取智能体信息失败:', error)
        router.push('/agent')
      }
    } else {
      router.push(redirectPath)
    }
  } catch (error) {
    console.error('登录失败:', error)
    errorMessage.value = error.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}

// 处理 OIDC 登录
const handleOIDCLogin = async () => {
  try {
    oidcLoading.value = true
    errorMessage.value = ''

    const response = await authApi.getOIDCLoginUrl()
    if (response.login_url) {
      const redirectPath =
        sessionStorage.getItem('redirect') || router.currentRoute.value.query.redirect || '/'
      sessionStorage.setItem('oidc_redirect', redirectPath)

      window.location.href = response.login_url
    } else {
      errorMessage.value = '获取 OIDC 登录地址失败'
    }
  } catch (error) {
    console.error('OIDC 登录失败:', error)
    errorMessage.value = error.message || 'OIDC 登录失败，请重试'
  } finally {
    oidcLoading.value = false
  }
}

// 检查 OIDC 配置
const checkOIDCConfig = async () => {
  oidcChecking.value = true
  try {
    const config = await authApi.getOIDCConfig()
    oidcEnabled.value = config.enabled
    if (config.provider_name) {
      oidcButtonText.value = config.provider_name
    }
  } catch (error) {
    console.error('检查 OIDC 配置失败:', error)
    oidcEnabled.value = false
  } finally {
    oidcChecking.value = false
  }
}

// 处理初始化管理员
const handleInitialize = async () => {
  try {
    loading.value = true
    errorMessage.value = ''

    if (adminForm.password !== adminForm.confirmPassword) {
      errorMessage.value = '两次输入的密码不一致'
      return
    }

    await userStore.initialize({
      user_id: adminForm.user_id,
      password: adminForm.password,
      phone_number: adminForm.phone_number || null
    })

    message.success('管理员账户创建成功')
    router.push('/')
  } catch (error) {
    console.error('初始化失败:', error)
    errorMessage.value = error.message || '初始化失败，请重试'
  } finally {
    loading.value = false
  }
}

// 检查是否是首次运行
const checkFirstRunStatus = async () => {
  try {
    loading.value = true
    const isFirst = await userStore.checkFirstRun()
    isFirstRun.value = isFirst
  } catch (error) {
    console.error('检查首次运行状态失败:', error)
    errorMessage.value = '系统出错，请稍后重试'
  } finally {
    loading.value = false
  }
}

// 检查服务器健康状态
const checkServerHealth = async () => {
  try {
    healthChecking.value = true
    const response = await healthApi.checkHealth()
    if (response.status === 'ok') {
      serverStatus.value = 'ok'
    } else {
      serverStatus.value = 'error'
      serverError.value = response.message || '服务端状态异常'
    }
  } catch (error) {
    console.error('检查服务器健康状态失败:', error)
    serverStatus.value = 'error'
    serverError.value = error.message || '无法连接到服务端，请检查网络连接'
  } finally {
    healthChecking.value = false
  }
}

// 组件挂载时
onMounted(async () => {
  if (userStore.isLoggedIn) {
    router.push('/')
    return
  }

  // 显示 OIDC 认证失败的错误信息
  if (route.query.oidc_error) {
    errorMessage.value = String(route.query.oidc_error)
  }

  await checkServerHealth()
  await checkFirstRunStatus()
  checkOIDCConfig()
})


</script>

<style lang="less" scoped>
.login-view {
  height: 100vh;
  width: 100%;
  position: relative;
  padding-top: 0;

  &.has-alert {
    padding-top: 60px;
  }
}

.login-top-action {
  position: absolute;
  top: 24px;
  right: 24px;
  z-index: 10;
}

.back-home-btn {
  color: var(--gray-600);
  font-size: 14px;
  padding: 0 8px;

  &:hover,
  &:focus {
    color: var(--main-color);
    background-color: transparent;
  }
}

.login-layout {
  display: flex;
  min-height: 100%;
  width: 100%;
  background: var(--gray-10);
}

.login-image-section {
  flex: 0 0 52%;
  position: relative;
  overflow: hidden;
  max-height: 100vh;

  .login-bg-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center;
  }

  .image-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.35);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 72px 64px 36px;
  }

  .brand-info {
    text-align: left;
    color: white;
    max-width: 520px;

    .brand-title {
      font-size: 52px;
      font-weight: 700;
      margin-bottom: 20px;
      text-shadow: 0 3px 6px rgba(0, 0, 0, 0.35);
      letter-spacing: -0.5px;
    }

    .brand-subtitle {
      font-size: 24px;
      font-weight: 500;
      margin-bottom: 24px;
      opacity: 0.92;
      text-shadow: 0 2px 4px rgba(0, 0, 0, 0.28);
      line-height: 1.4;
    }

    .brand-description {
      font-size: 18px;
      line-height: 1.6;
      margin: 0;
      opacity: 0.82;
      text-shadow: 0 1px 3px rgba(0, 0, 0, 0.28);
    }
  }

  .brand-copyright {
    align-self: flex-start;

    p {
      margin: 0;
      font-size: 14px;
      color: rgba(255, 255, 255, 0.7);
      text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
      font-weight: 400;
    }
  }
}

.login-form-section {
  flex: 1;
  min-width: 420px;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 64px 72px;
  background: var(--main-20);
}

.login-container {
  width: 100%;
  max-width: 460px;
  padding: 40px;
  background: var(--gray-0);
  border-radius: 24px;
  border: 1px solid var(--gray-150);
  box-shadow: 0 18px 36px rgba(66, 66, 66, 0.05);
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.login-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
}

.login-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--gray-600);
  text-transform: uppercase;
}

.login-brand {
  margin: 0;
  font-size: 30px;
  font-weight: 600;
  color: var(--main-color);
  line-height: 1.25;
}

.login-subtitle {
  margin: 0;
  font-size: 16px;
  color: var(--gray-600);
  line-height: 1.6;
}

.login-content {
  display: flex;
  flex-direction: column;
  gap: 24px;

  &.is-initializing {
    gap: 28px;
  }
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;

  :deep(.ant-form) {
    width: 100%;
  }

  :deep(.ant-form-item) {
    margin-bottom: 18px;
  }

  :deep(.ant-input-affix-wrapper) {
    padding: 10px 11px;
    height: auto;
  }

  :deep(.ant-btn) {
    font-size: 16px;
    padding: 0.5rem;
    height: auto;
  }
}

.login-form--init {
  padding: 24px;
  border-radius: 18px;
  background: var(--main-30);
  border: 1px solid var(--main-200);

  h2 {
    margin-bottom: 16px;
    font-size: 22px;
    font-weight: 600;
    color: var(--main-color);
    text-align: left;
  }
}

.error-message {
  margin-top: 16px;
  padding: 10px 12px;
  background-color: var(--stats-error-bg);
  border: 1px solid rgba(220, 38, 38, 0.25);
  border-radius: 8px;
  color: var(--stats-error-color);
  font-size: 14px;
}

.third-party-login {
  margin-top: 20px;

  .divider {
    position: relative;
    text-align: center;
    margin: 16px 0;

    &::before,
    &::after {
      content: '';
      position: absolute;
      top: 50%;
      width: calc(50% - 60px);
      height: 1px;
      background-color: var(--gray-200);
    }

    &::before {
      left: 0;
    }

    &::after {
      right: 0;
    }

    span {
      display: inline-block;
      padding: 0 12px;
      background-color: var(--gray-0);
      position: relative;
      color: var(--gray-600);
      font-size: 14px;
    }
  }

  .login-icons {
    display: flex;
    justify-content: center;
    margin-top: 16px;
    flex-direction: column;
    gap: 12px;

    :deep(.ant-btn) {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      height: 44px;
      font-size: 16px;
      border-color: var(--gray-300);
      color: var(--gray-700);

      &:hover {
        border-color: var(--main-color);
        color: var(--main-color);
        background-color: var(--main-10);
      }

      .anticon {
        color: var(--main-color);
      }
    }
  }

  .login-skeleton {
    :deep(.ant-skeleton-button) {
      width: 100% !important;
      height: 44px;
      border-radius: 8px;
    }
  }
}

.server-status-alert {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 12px 20px;
  background: linear-gradient(135deg, #ff4d4f, #ff7875);
  color: white;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(255, 77, 79, 0.3);

  .alert-content {
    display: flex;
    align-items: center;
    max-width: 1200px;
    margin: 0 auto;

    .alert-icon {
      font-size: 20px;
      margin-right: 12px;
      color: white;
    }

    .alert-text {
      flex: 1;

      .alert-title {
        font-weight: 600;
        font-size: 16px;
        margin-bottom: 2px;
      }

      .alert-message {
        font-size: 14px;
        opacity: 0.9;
      }
    }

    :deep(.ant-btn-link) {
      color: white;
      border-color: white;

      &:hover {
        color: white;
        background-color: rgba(255, 255, 255, 0.1);
      }
    }
  }
}
</style>
