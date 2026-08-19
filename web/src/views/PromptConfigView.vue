<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  SaveOutlined,
  ReloadOutlined,
  FileTextOutlined,
  SettingOutlined
} from '@ant-design/icons-vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

const router = useRouter()

// 状态
const loading = ref(false)
const saving = ref(false)
const activeTab = ref('extract')
const promptConfig = ref({
  extract_prompt: '',
  template_prompt: '',
  schema_generation_prompt: '',
  section_generalization_prompt: ''
})

// 默认 Prompt 模板
const defaultPrompts = {
  extract_prompt: `你是一个专业的文档信息提取助手。请从以下文档中提取结构化信息。

## 需要提取的字段：
{variables}

## 文档内容：
{content}

## 输出要求：
请以 JSON 格式返回提取结果，格式如下：
{
  "字段Key": "提取到的值",
  "_confidence_字段Key": 0.0-1.0之间的置信度
}

注意：
1. 只返回 JSON，不要有其他内容
2. 如果某个字段在文档中未找到，设置值为 null
3. 置信度 1.0 表示非常有把握，0.5 表示不确定
4. 只提取文档中明确提到的信息，不要推断`,

  template_prompt: `你是一个专业的模板工程师。请将以下文本泛化为包含槽位的模板格式。

## 原文：
{content}

## 已提取的数据：
{extracted_data}

## 要求：
1. 将原文中的具体数值替换为槽位占位符
2. 槽位格式使用 {{槽位名称}} 表示
3. 保持原文的结构和格式
4. 输出 JSON 格式：
{
  "template": "泛化后的模板文本",
  "slots": ["槽位1名称", "槽位2名称", ...],
  "original_excerpts": ["原始片段1", "原始片段2", ...]
}`,

  schema_generation_prompt: `你是一个专业的领域专家。请根据以下文档内容生成标准化的 Schema 配置。

## 文档领域：
{domain}

## 文档内容摘要：
{content}

## 要求：
1. 识别文档中的关键信息字段
2. 为每个字段指定合适的数据类型和控件类型
3. 生成符合领域规范的字段命名
4. 输出 JSON 格式：
{
  "variables": [
    {
      "key": "字段Key",
      "label": "字段显示名",
      "data_type": "string|number|boolean|date",
      "widget": "Input|InputNumber|Select|DatePicker",
      "unit": "单位",
      "group": "分组名称",
      "required": true/false,
      "prompt": "提取提示词"
    }
  ],
  "chapters": [
    {"key": "ch1", "title": "章节标题"}
  ]
}`,

  section_generalization_prompt: `你是一个专业的环评报告分析助手。请对以下章节进行泛化处理。

## 行业领域：
{industry}

## 报告类型：
{report_type}

## 章节标题：
{title}

## 章节内容：
{content}

## 标准章节代码参考：
{standard_codes}

## 要求：
1. 提取章节的核心内容和结构
2. 生成模板化的章节框架
3. 识别需要填写的关键参数
4. 输出 JSON 格式：
{
  "generalized_content": "泛化后的内容模板",
  "slots": [
    {"name": "参数名称", "source": "数据来源", "required": true/false}
  ],
  "keywords": ["关键词1", "关键词2"],
  "related_sections": ["相关章节1", "相关章节2"]
}`
}

// 获取 Prompt 配置
const fetchPromptConfig = async () => {
  loading.value = true
  try {
    const res = await domainFactoryApi.getPromptConfig()
    if (res?.config) {
      const cfg = res.config
      promptConfig.value = {
        extract_prompt: cfg.extract_prompt || defaultPrompts.extract_prompt,
        template_prompt: cfg.template_prompt || defaultPrompts.template_prompt,
        schema_generation_prompt: cfg.schema_generation_prompt || defaultPrompts.schema_generation_prompt,
        section_generalization_prompt: cfg.section_generalization_prompt || defaultPrompts.section_generalization_prompt
      }
    } else {
      // 使用默认
      promptConfig.value = { ...defaultPrompts }
    }
  } catch (e) {
    console.error('获取 Prompt 配置失败:', e)
    message.error('获取 Prompt 配置失败')
    promptConfig.value = { ...defaultPrompts }
  } finally {
    loading.value = false
  }
}

// 保存配置
const handleSave = async () => {
  saving.value = true
  try {
    await domainFactoryApi.updatePromptConfig(promptConfig.value)
    message.success('Prompt 配置已保存')
  } catch (e) {
    console.error('保存 Prompt 配置失败:', e)
    message.error('保存 Prompt 配置失败')
  } finally {
    saving.value = false
  }
}

// 刷新
const handleRefresh = () => {
  fetchPromptConfig()
}

// 重置为默认
const handleReset = (type) => {
  promptConfig.value[type] = defaultPrompts[type]
}

// 插入变量
const insertVariable = (type, variable) => {
  promptConfig.value[type] += variable
}

const variables = {
  extract: ['{variables}', '{content}', '{domain}', '{confidence}'],
  template: ['{content}', '{extracted_data}', '{slots}', '{original_excerpts}'],
  schema: ['{domain}', '{content}', '{variables}', '{chapters}'],
  section: ['{industry}', '{report_type}', '{title}', '{content}', '{standard_codes}']
}

onMounted(() => {
  fetchPromptConfig()
})
</script>

<template>
  <div class="prompt-config-view">
    <!-- Header -->
    <div class="page-header">
      <div class="title-group">
        <div class="title-with-back">
          <a-button type="text" class="back-btn" @click="router.back()">
            <template #icon><ArrowLeftOutlined /></template>
            返回
          </a-button>
          <div>
            <h1>Prompt 模板管理</h1>
            <p class="page-desc">管理文档解析、模板泛化处理时的 LLM 提示词配置</p>
          </div>
        </div>
      </div>
      <div class="header-actions">
        <a-button @click="handleRefresh" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
        <a-button type="primary" @click="handleSave" :loading="saving">
          <template #icon><SaveOutlined /></template>
          保存配置
        </a-button>
      </div>
    </div>

    <!-- Main Content -->
    <div class="content-area">
      <a-spin :spinning="loading">
        <a-tabs v-model:activeKey="activeTab" type="card" size="large">
          <a-tab-pane key="extract" tab="文档解析 Prompt">
            <div class="prompt-editor">
              <div class="prompt-header">
                <div>
                  <h3>文档解析/信息抽取 Prompt</h3>
                  <p class="prompt-desc">用于从文档中抽取结构化信息的提示词</p>
                </div>
                <a-button size="small" @click="handleReset('extract_prompt')">重置为默认</a-button>
              </div>
              <div class="variable-hint">
                <span>可用变量：</span>
                <a-tag
                  v-for="v in variables.extract"
                  :key="v"
                  class="clickable-tag"
                  @click="insertVariable('extract_prompt', v)"
                >
                  {{ v }}
                </a-tag>
              </div>
              <a-textarea
                v-model:value="promptConfig.extract_prompt"
                :rows="16"
                placeholder="请输入文档解析 Prompt..."
                class="prompt-textarea"
              />
            </div>
          </a-tab-pane>

          <a-tab-pane key="template" tab="模板泛化 Prompt">
            <div class="prompt-editor">
              <div class="prompt-header">
                <div>
                  <h3>模板泛化 Prompt</h3>
                  <p class="prompt-desc">用于将原始文本泛化为带插槽模板的提示词</p>
                </div>
                <a-button size="small" @click="handleReset('template_prompt')">重置为默认</a-button>
              </div>
              <div class="variable-hint">
                <span>可用变量：</span>
                <a-tag
                  v-for="v in variables.template"
                  :key="v"
                  class="clickable-tag"
                  @click="insertVariable('template_prompt', v)"
                >
                  {{ v }}
                </a-tag>
              </div>
              <a-textarea
                v-model:value="promptConfig.template_prompt"
                :rows="16"
                placeholder="请输入模板泛化 Prompt..."
                class="prompt-textarea"
              />
            </div>
          </a-tab-pane>

          <a-tab-pane key="schema" tab="Schema 生成 Prompt">
            <div class="prompt-editor">
              <div class="prompt-header">
                <div>
                  <h3>Schema 生成 Prompt</h3>
                  <p class="prompt-desc">用于从示例文档中自动生成领域 Schema 配置的提示词</p>
                </div>
                <a-button size="small" @click="handleReset('schema_generation_prompt')">重置为默认</a-button>
              </div>
              <div class="variable-hint">
                <span>可用变量：</span>
                <a-tag
                  v-for="v in variables.schema"
                  :key="v"
                  class="clickable-tag"
                  @click="insertVariable('schema_generation_prompt', v)"
                >
                  {{ v }}
                </a-tag>
              </div>
              <a-textarea
                v-model:value="promptConfig.schema_generation_prompt"
                :rows="16"
                placeholder="请输入 Schema 生成 Prompt..."
                class="prompt-textarea"
              />
            </div>
          </a-tab-pane>

          <a-tab-pane key="section" tab="章节泛化 Prompt">
            <div class="prompt-editor">
              <div class="prompt-header">
                <div>
                  <h3>章节泛化提取 Prompt</h3>
                  <p class="prompt-desc">用于对样例报告进行章节提取和泛化处理的提示词</p>
                </div>
                <a-button size="small" @click="handleReset('section_generalization_prompt')">重置为默认</a-button>
              </div>
              <div class="variable-hint">
                <span>可用变量：</span>
                <a-tag
                  v-for="v in variables.section"
                  :key="v"
                  class="clickable-tag"
                  @click="insertVariable('section_generalization_prompt', v)"
                >
                  {{ v }}
                </a-tag>
              </div>
              <a-textarea
                v-model:value="promptConfig.section_generalization_prompt"
                :rows="16"
                placeholder="请输入章节泛化 Prompt..."
                class="prompt-textarea"
              />
            </div>
          </a-tab-pane>
        </a-tabs>
      </a-spin>
    </div>
  </div>
</template>

<style lang="less" scoped>
.prompt-config-view {
  padding: 24px;
  background: var(--gray-0);
  min-height: 100vh;

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--gray-150);

    .title-group {
      .title-with-back {
        display: flex;
        align-items: flex-start;
        gap: 8px;

        .back-btn {
          margin-top: 4px;
        }

        h1 {
          margin: 0;
          font-size: 20px;
          font-weight: 600;
        }

        .page-desc {
          margin: 4px 0 0;
          color: var(--gray-500);
          font-size: 13px;
        }
      }
    }

    .header-actions {
      display: flex;
      gap: 8px;
    }
  }

  .content-area {
    background: var(--gray-0);

    .prompt-editor {
      padding: 16px;

      .prompt-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;

        h3 {
          margin: 0;
          font-size: 16px;
        }

        .prompt-desc {
          margin: 4px 0 0;
          color: var(--gray-500);
          font-size: 13px;
        }
      }

      .variable-hint {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 12px;
        padding: 12px;
        background: var(--gray-50);
        border-radius: 8px;

        span {
          font-size: 13px;
          color: var(--gray-600);
          font-weight: 500;
        }

        .clickable-tag {
          cursor: pointer;
          transition: all 0.2s;

          &:hover {
            background: var(--main-100);
            border-color: var(--main-color);
          }
        }
      }

      .prompt-textarea {
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 13px;
        line-height: 1.6;
      }
    }
  }
}

:deep(.ant-tabs-card) {
  .ant-tabs-nav {
    margin: 0;
  }

  .ant-tabs-tab {
    padding: 12px 24px;
    font-size: 14px;
  }
}
</style>
