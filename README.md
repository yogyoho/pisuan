llama-server -hf unsloth/gemma-4-E4B-it-GGUF:UD-Q4_K_XL -c 8196 --host 0.0.0.0
让智能体可构建、可编排、可落地
统一编排 Agent、知识库、图谱与工具链
让智能体可落地，让流程可编排，让协作可扩展
让智能体可构建，让知识可连接，让决策可验证
让数据可沉淀，让能力可复用，让系统可进化
开源智能体平台套件，融合 RAG 与知识图谱

请详细分析C:\workspace\know\目录下知识工厂页面中数据源管理tab页中，文件报告上传后的处理逻辑，目前本系统的文档报告上传后，进行文档解析、提取、泛化过程有问题，表格数据被切碎了。

请详细分析C:\workspace\know\目录下知识工厂页面中数据源管理tab页中，文件报告上传后的处理逻辑，目前本系统的文档报告上传后，进行文档解析、提取、泛化过程中，模板泛化有问题，请详细分析源系统是如何实现的，参照源系统来修复。先对比两者实现上有啥不同和差异

我在本系统领域知识工厂模块中将工程类的报告样例上传，然后进行了文档解析、章节、段落、表格等元素的提取、将段落泛化成模
  板，然后通过人工校验，保存到lightRAG知识库中，我希望加工后数据可以封装成skills，然后在Agent对话页面中，在报告智能编写
  过程中被Agent调用。想设计三个skills主要是
  1.段落模板的智能推荐：根据用户提问中
  关键字，从相应领域知识库中搜索相应章节和段落，如果给定某某章节和章节标题，就要搜索该章节及其子章节，需要合并输出。
  2.智能填插槽：如果上文中已经给出了选定的章节及段落模板，那就需要要根据上下文或用户提供附件文件，智能给段落模板中插槽
  填文字和数据，不允许编造数据，给出每个填充后数据的置信度，填不上的，让用户补充填写。
  注意：
   - 智能填槽skill依赖段落模板推荐skill。
   - 数据不能插槽数据不能编造。
   - 整个章节模板推荐要将该章节及其子章节和段落合并后完整推荐。



{
  "id": "p4",
  "title": "",
  "content": "伊宁矿区北区位于伊犁盆地北缘，地势东高西低，北高南低，东南部地表起伏不平，东北部稍高但较为平坦，属低山丘陵地貌，海拔标高一般为+630 m～+1200 m，一般相对高差50～150 m。",
  "is_title": false,
  "level": 0,
  "section_path": [
    "1",
    "1.1",
    "1.1.1"
  ],
  "section_code": "SEC_1_1.1_1.1.1",
  "word_count": 93,
  "char_count": 93,
  "parent_title": "1",
  "source": "paragraph",
  "is_table": false
}


总结一下 Prompt 模板管理的改动：

  改动内容

  1. 新增配置文件 backend/package/yuxi/config/static/prompt_templates.yaml

  - 4 种 prompt 模板：extract、template、schema_generation、section_generalization
  - 每种模板都有中文注释说明可用的占位符
  - 与前端 PromptConfigView.vue 的 defaultPrompts 保持同步

  2. 修改 domain_factory_service.py

  - _load_prompt_templates() — 先从 YAML 文件读取，再用数据库记录覆盖
  - _load_prompts_from_file() — 从 prompt_templates.yaml 加载
  - _render_prompt() — 统一的占位符替换方法
  - _build_extract_prompt() — 使用 DB/文件模板替代硬编码
  - _build_text_generalize_prompt() — 使用 DB/文件模板替代硬编码
  - generalize_paragraphs() — 预加载模板，一次 DB 查询复用
  - save_prompt_config() — 保存后清除缓存，下次生效

  数据流

  prompt_templates.yaml (文件默认值)
          ↓ 覆盖
  DomainFactoryPromptConfig 表 (用户自定义)
          ↓ 缓存
  _render_prompt() 占位符替换
          ↓
  ETL 流程实际使用

  现在前端"提示词管理"页面编辑的 prompt 会真正影响文档处理流程。



---

# 领域知识工厂解析、提取、泛化过程的提示词

你是一名严谨的领域信息抽取专家，正在处理 {domain_label} 领域的环境影响报告。
请根据提供的 Schema 变量和章节提示，从下方文本中抽取结构化信息。

要求：
1. 仅输出 JSON，不要包含额外说明，不要输出任何自然语言解释；
2. 若无法确定某字段的值，请输出 null；
3. 数值统一转换到对应字段的单位（例如吨/年 -> Mt/a）；
4. 如果文本包含多个对象，优先选择与当前章节最相关的内容，并在 `candidates` 中给出引用的原文片段；
5. 仅使用 Schema 中定义的字段；
6. 严格禁止输出代码块标记（例如 ```json 或 ```），也不要在 JSON 前后添加任何多余字符。

可用 Schema 变量：
{schema_variables}
当前章节：{chapter_hint}

文本片段：
"""
{paragraph}
"""

必需输出 JSON，如：
{{
  "base_info": {{ ... }}
}}

---


你是一个专业的文档信息提取助手。请从以下文档中提取结构化信息。

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
4. 只提取文档中明确提到的信息，不要推断



---

