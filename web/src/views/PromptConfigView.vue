<script setup>
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { NotebookPen, RotateCw, Save } from '@lucide/vue'
import { domainFactoryApi } from '@/apis/domain_factory_api'

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

## 文档类型：
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
        schema_generation_prompt:
          cfg.schema_generation_prompt || defaultPrompts.schema_generation_prompt,
        section_generalization_prompt:
          cfg.section_generalization_prompt || defaultPrompts.section_generalization_prompt
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
  <div class="ewp prompt-config-view">
    <!-- 页头（EIA page-head 配方）：四组 Prompt seg 分段器收进 ph-actions -->
    <div class="page-head">
      <div class="ph-icon">
        <NotebookPen :size="18" />
      </div>
      <div>
        <h2>Prompt 模板管理</h2>
        <div class="ph-sub">文档解析、模板泛化处理时的 LLM 提示词配置</div>
      </div>
      <div class="ph-actions">
        <div class="seg">
          <button :class="{ on: activeTab === 'extract' }" @click="activeTab = 'extract'">文档解析</button>
          <button :class="{ on: activeTab === 'template' }" @click="activeTab = 'template'">模板泛化</button>
          <button :class="{ on: activeTab === 'schema' }" @click="activeTab = 'schema'">Schema 生成</button>
          <button :class="{ on: activeTab === 'section' }" @click="activeTab = 'section'">章节泛化</button>
        </div>
        <button class="btn btn-sec" :disabled="loading" @click="handleRefresh">
          <RotateCw :size="14" /> 刷新
        </button>
        <button class="btn btn-pri" :disabled="saving" @click="handleSave">
          <Save :size="14" /> 保存配置
        </button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <!-- 文档解析 Prompt -->
      <div v-show="activeTab === 'extract'" class="card">
        <div class="card-hd">
          <h3>文档解析 / 信息抽取 Prompt</h3>
          <span class="hd-sub">用于从文档中抽取结构化信息的提示词</span>
          <div class="hd-right">
            <button class="btn btn-sm btn-sec" @click="handleReset('extract_prompt')">重置为默认</button>
          </div>
        </div>
        <div class="prompt-editor">
          <div class="variable-hint">
            <span>可用变量：</span>
            <button
              v-for="v in variables.extract"
              :key="v"
              class="slot-chip var-chip"
              @click="insertVariable('extract_prompt', v)"
            >
              {{ v }}
            </button>
          </div>
          <a-textarea
            v-model:value="promptConfig.extract_prompt"
            :rows="16"
            placeholder="请输入文档解析 Prompt..."
            class="prompt-textarea"
          />
        </div>
      </div>

      <!-- 模板泛化 Prompt -->
      <div v-show="activeTab === 'template'" class="card">
        <div class="card-hd">
          <h3>模板泛化 Prompt</h3>
          <span class="hd-sub">用于将原始文本泛化为带插槽模板的提示词</span>
          <div class="hd-right">
            <button class="btn btn-sm btn-sec" @click="handleReset('template_prompt')">重置为默认</button>
          </div>
        </div>
        <div class="prompt-editor">
          <div class="variable-hint">
            <span>可用变量：</span>
            <button
              v-for="v in variables.template"
              :key="v"
              class="slot-chip var-chip"
              @click="insertVariable('template_prompt', v)"
            >
              {{ v }}
            </button>
          </div>
          <a-textarea
            v-model:value="promptConfig.template_prompt"
            :rows="16"
            placeholder="请输入模板泛化 Prompt..."
            class="prompt-textarea"
          />
        </div>
      </div>

      <!-- Schema 生成 Prompt -->
      <div v-show="activeTab === 'schema'" class="card">
        <div class="card-hd">
          <h3>Schema 生成 Prompt</h3>
          <span class="hd-sub">用于从示例文档中自动生成领域 Schema 配置的提示词</span>
          <div class="hd-right">
            <button class="btn btn-sm btn-sec" @click="handleReset('schema_generation_prompt')">
              重置为默认
            </button>
          </div>
        </div>
        <div class="prompt-editor">
          <div class="variable-hint">
            <span>可用变量：</span>
            <button
              v-for="v in variables.schema"
              :key="v"
              class="slot-chip var-chip"
              @click="insertVariable('schema_generation_prompt', v)"
            >
              {{ v }}
            </button>
          </div>
          <a-textarea
            v-model:value="promptConfig.schema_generation_prompt"
            :rows="16"
            placeholder="请输入 Schema 生成 Prompt..."
            class="prompt-textarea"
          />
        </div>
      </div>

      <!-- 章节泛化 Prompt -->
      <div v-show="activeTab === 'section'" class="card">
        <div class="card-hd">
          <h3>章节泛化抽取 Prompt</h3>
          <span class="hd-sub">用于对样例报告进行章节提取和泛化处理的提示词</span>
          <div class="hd-right">
            <button class="btn btn-sm btn-sec" @click="handleReset('section_generalization_prompt')">
              重置为默认
            </button>
          </div>
        </div>
        <div class="prompt-editor">
          <div class="variable-hint">
            <span>可用变量：</span>
            <button
              v-for="v in variables.section"
              :key="v"
              class="slot-chip var-chip"
              @click="insertVariable('section_generalization_prompt', v)"
            >
              {{ v }}
            </button>
          </div>
          <a-textarea
            v-model:value="promptConfig.section_generalization_prompt"
            :rows="16"
            placeholder="请输入章节泛化 Prompt..."
            class="prompt-textarea"
          />
        </div>
      </div>
    </a-spin>
  </div>
</template>

<style lang="less" scoped>
/* 公共配方（page-head/seg/btn/card/card-hd/slot-chip）在 factory-core/factory-ui.less */
.prompt-editor {
  padding: 12px 16px 16px;
}

/* 变量 chip：slot-chip 配方可点击化（mono 仅技术标识，正文不 mono） */
.variable-hint {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;

  > span {
    font-size: 12px;
    color: var(--color-text-tertiary);
  }
}

.var-chip {
  appearance: none;
  border: none;
  cursor: pointer;
  padding: 2px 8px;
  transition:
    background 0.15s,
    color 0.15s;

  &:hover {
    background: var(--main-100);
  }
}

/* 编辑区：AntD textarea 罩到 .inp 配方（灰边/6px/主色 focus ring），正文 mono */
.prompt-textarea {
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  background: var(--gray-0);
  transition: border-color 0.15s;

  &:focus {
    border-color: var(--main-500);
    box-shadow: 0 0 0 2px var(--main-50);
  }

  font-family: 'JetBrains Mono', ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text);
}
</style>

<style lang="less" src="../components/factory-core/factory-ui.less"></style>
