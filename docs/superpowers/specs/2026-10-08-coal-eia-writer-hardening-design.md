# coal-eia-writer 技能薄弱项优化（部分一）设计 spec

- 日期：2026-10-08
- 状态：设计已批准（brainstorming 会话产出），待 writing-plans 出实施计划
- 前置：`docs/vibe/2026-10-08-kf-refactor-direction-from-skill-testing.md`（薄弱点 W/D/G 清单与知识工厂方向）；本 spec 为其中「部分一：技能自身薄弱项优化」，部分二（知识工厂知识/数据支撑）另行立项
- 方案选型：用户选定方案 B（语料驱动全量加工），否决了方案 A（实测种子针对性供给）与 C（最小防线）

## 一、背景

技能全面梳理（2026-10-08）结论：骨架健康（状态机/门/组装经 bug-393/394/395 三轮实战加固），薄弱集中在**四类供给断链**：

1. **范式供给过粗**（W1/W5）：4 角色 md 共 188 行覆盖 77 异质节；无「表格引导句」形态正样本（bug-394 实测 215 处句中嵌表）。
2. **数据期望过粗**（D1/W3）：data_expectations.json 仅章级 13 章（ch6 noise 仅 4 条文本期望），与 formula_runner 字段级消费（`noise.distances.point`）脱节——point_level 缺数 `[待确认]` 的直接机制。
3. **样例衍生物断链**（G2/N1/N2）：bank_compile.py 编译器就绪但从未对 coal 语料执行（`samples_bank/` 目录不存在）；calibrate.py 用法过时（指向单文件输出），depth_targets 为手维值。
4. **schema 无静态检查**（G3/N5）：bug-366/393/394 三轮人修 stage forms（label/竖线/族 label）；其余 4 个 stage 未做同等体检。

## 二、范围

**做**：

- `scripts/prepare_corpus.py`（新建）：41 份语料 docx → bank_compile 输入格式
- `scripts/bank_compile.py`（扩展，向后兼容）：新增两族衍生物编译
- `scripts/schema_linter.py`（新建）：5 stage forms 静态体检
- `references/paradigms/forms_catalog.json`（新建）：三形态统计+例句池
- `references/section_expectations.json`（新建）：节级数值-口径清单
- `references/data_expectations.json`：GBK 乱码修复（仅编码，结构不动）
- `scripts/calibrate.py`：适配 5-stage 目录输出
- SKILL.md：轻改（范式引用 + 写前对账指令）
- 测试：linter / bank_compile 新衍生物 / prepare_corpus / 门逻辑系统测试

**不做（边界）**：

- 管线脚本不动：build_output.py / consistency.py / progress.py / ingest.py / chapter_planner.py / mapping.py / snapshot.py
- stage JSON 本体不动（linter 只报告不修复；修复另行立项）
- 知识工厂功能不动（既有约束「现有知识工厂的功能先别动」）
- yuxi core 不动
- XS2 一致性门的机器断言升级（留后续项；本 spec 只做写前对账的契约面接入）
- seed_gen.py / get_chapter_outline 桥接改造（属部分二）

## 三、管线架构

```
41 份 docx（C:\项目管理\样例文件）
   │  ① prepare_corpus.py：docx→md（节号标题识别 + GFM 表格 + 目录页剔除 + 范围裁剪）
   ▼
<workdir>/<report_id>/source.md + manifest.json（bank_compile 既定输入格式）
   │  ② bank_compile.py：现有能力（切片库 + SL3 指纹池 + 深度基线）
   │     + 新增两族衍生物（形态统计 / 节级期望）
   ▼
references/ 衍生物：
   samples_bank/<stage>/slices/...      写手范文切片（git 入库）
   samples/<stage>/chN__<rid>.md        SL3 指纹池（consistency.py:422 消费）
   depth_targets/<stage>.json           calibrate 复算替换手维值
   paradigms/forms_catalog.json         三形态统计+例句池 ★新
   section_expectations.json            节级×字段×单位×口径 ★新
   │  ③ schema_linter.py（独立于语料）：5 stage forms 五类检查
   ▼
验收面：linter 全量报告 + test2 重跑门告警对比 + 新增测试全绿
```

### 已确认的决策输入

- **语料位置**：`C:\项目管理\样例文件`（41 份 docx；census 元数据在 `.wolf/corpus-census/census.json`）
- **入库策略**：切片随 git 入库（explicit add），先例为 23 个 sample_entities/*.json
- **样例库载体**：技能内文件夹，不进 Milvus——SL3 门是文件 glob（`consistency.py:422`），需要确定性指纹，向量检索不可替代

## 四、产物 schema

### 4.1 `references/paradigms/forms_catalog.json`（全局一份）

**聚合规则**：41 份语料切片按章题归一化到 stage 规范节 → 提取「表 X-Y 题行前一非空行」→ 形态聚类 → 统计+例句池。**消费方**：写手（SKILL.md 派发契约引用），给正样本而非禁令。以下 stats 数值为形态示意，实际以语料统计为准。

```json
{
  "version": "1.0",
  "generated": "2026-10-08",
  "source": "41 份语料切片统计",
  "forms": {
    "table_lead": {
      "desc": "表题行前一非空行形态",
      "stats": {"complete_sentence": 0.62, "colon_lead": 0.28, "standalone_caption": 0.10},
      "templates": ["……{主题}如下表所列。", "……{主题}详见表 {ch}-{seq}。", "……{主题}："],
      "examples": ["（高频真实例句，带 report_id 溯源）"]
    },
    "numeric_citation": {
      "desc": "数值引用形态（治 W3 四舍五入漂移）",
      "stats": {"exact_with_unit": 0.78, "range_form": 0.14, "rounded": 0.08},
      "templates": ["{量}为 {value} {unit}", "…介于 {v1}～{v2} {unit} 之间"],
      "examples": ["…"]
    },
    "caliber_disambiguation": {
      "desc": "同标签多值消歧写法（治 W4/XS6）",
      "stats": {"caliber_suffix": 0.71, "table_column": 0.22, "other": 0.07},
      "templates": ["按{口径A}为 {v1}，按{口径B}为 {v2}"],
      "examples": ["…"]
    }
  }
}
```

### 4.2 `references/section_expectations.json`（按 stage 分节）

**聚合规则**：逐节抽取语料实引数值（数值+单位+所在句语境）→ 归并到字段路径（对齐 formula_runner 派生输入）→ 频率统计定 tier。**消费接入（v1）**：SKILL.md 派发契约加「写前对账」指令——写手开节前将本节 expected_quantities 与 data/ 对账，缺项提前暴露；不改机器门。

```json
{
  "version": "1.0",
  "stage_scope": "planning_eia",
  "sections": {
    "ch6_S05": {
      "title": "声环境影响评价",
      "expected_quantities": [
        {"field": "noise.line_level", "unit": "dB(A)", "caliber": "铁路最近敏感点处预测声级",
         "tier": "required", "corpus_freq": 0.83},
        {"field": "noise.distances.point", "unit": "m", "caliber": "点源达标距离（昼/夜分列）",
         "tier": "required", "corpus_freq": 0.91}
      ],
      "tables": ["noise", "standards_confirm", "monitoring"]
    }
  }
}
```

`tier` 划档：`required`（corpus_freq ≥ 0.6）/ `optional`（0.2–0.6）/ `contextual`（< 0.2，仅留档）。

与 data_expectations.json 的关系：章级骨架保留管「收集什么」（ingest 面），节级清单管「写作前须有何」（对账面），通过 field 路径互查。

### 4.3 `scripts/schema_linter.py` 检查面（五类）

| # | 检查 | 对应历史 bug |
|---|---|---|
| L1 | forms 族标量字段缺中文 label | bug-366（135 字段） |
| L2 | label/description/enum 值含 `\|` 字符（裂表） | bug-393（28 组） |
| L3 | 数值型字段缺 unit | bug-394 关联 |
| L4 | 表格族列键英文裸奔（无中文 label） | bug-368 |
| L5 | 枚举值含英文/重复/超长 | 弱检查（canon 清单可后续挂） |

输出：逐 stage 违规报告（stage × L1–L5 × 明细），有违规 exit 1。**只报告不修复**。

## 五、归一化与解析边界

### 章题归一化（两级）

- **章级**：复用 corpus-census 已人工过目的 44 条 aliases（planning 18 / project 22 / post 4 / tracking 0）+ `_layer1_draft.json` canonical 章题清单
- **节级**：语料切片标题 → stage json 节 title 三级降档匹配（精确 → 去空格/标点变体 → 子串）；未命中落「未归并池」显式列出不静默丢弃，人工过目后补 alias

### prepare_corpus.py 解析边界

| 边界 | 处理 |
|---|---|
| 标题识别 | 正文行节号模式匹配为主（`数字(.数字)* + 空格 + 题名`；census 实测 679 标题仅 81 个有 style 标记），命中加 `##/###` |
| 目录页剔除 | 「标题+尾随页码」密集区段检测剔除 |
| 表格转换 | docx table → GFM（列数取齐） |
| 范围裁剪 | 剔封面/编制单位/批复页；元数据进 manifest |
| stage 标注 | manifest 草稿从 census.json 族分布机械生成；underground/openpit 与边界 case 人工过目 |
| 解析失败 | 逐份 stderr 警告 + 跳过（bank_compile 既有惯例） |

## 六、实施顺序（L0→L3）

```
L0 语料准备   prepare_corpus.py + 测试 → 41 份转换 → manifest 人工过目
              → bank_compile 现有能力跑通（切片+SL3 池+深度基线）★即时收益：SL3 warn 消除
L1 schema linter（独立，可与 L0 并行）  schema_linter.py + 测试 → 5 stage 报告落档
L2 统计衍生物（依赖 L0）  bank_compile 扩展：forms_catalog + section_expectations
              + calibrate 适配 5-stage 目录 + 各自测试
L3 接入与验收  SKILL.md 轻改（范式引用+写前对账）+ GBK 修复
              + 门逻辑系统测试 + test2 重跑对比
```

## 七、验收 checklist

- [ ] linter 对 5 stage 跑通，bug-366/393/394 三轮人修项可被重发现；N5 疑点（4 个未体检 stage）得到回答
- [ ] `references/samples/<stage>/` 指纹池 + samples_bank 切片就位（git 入库）；test2 重跑 SL3 warn 消除
- [ ] depth_targets 5 份由 calibrate 复算替换手维值（diff 可解释）；tracking_eia 无语料如实保留手维并注明
- [ ] forms_catalog 三形态各有统计占比+例句池（41 份语料支撑）
- [ ] section_expectations 抽 ≥3 节人工核对：清单与样例实引数值对得上
- [ ] 抽 1 节（ch6_S05 复验）用新范式+期望清单重写：单章门通过、写前对账能提前暴露缺项
- [ ] 门逻辑系统测试全绿；既有 bug-393/394/395/bug3229 回归不退化
- [ ] yuxi core 不动、知识工厂功能不动、管线脚本不动

## 八、已知边界（如实声明）

- tracking_eia 语料 0 份——该 stage 样例面维持现状（SL3 warn 与手维基线保留并注明）
- 节级归一化匹配率不承诺 100%（未归并池兜底，人工补 alias 是持续动作）
- linter 只报告不修复，stage JSON 修复另行立项
- 41 份语料为真实项目环评报告书（依法公开文件）；切片入库前剔除编制单位等元数据页

## 九、关联

- 薄弱点来源：`docs/vibe/2026-10-08-kf-refactor-direction-from-skill-testing.md`（W1–W5/D1–D3/G1–G3）
- 部分二接口：seed_gen.py（stage→KF 单向桥已存在）；bank_compile 的「编译器→衍生物」模式即部分二知识工厂加工通道的技能侧原型
- 既有积累复用：`.wolf/corpus-census/`（41 份普查元数据、44 条 aliases、layer1 canonical 清单）
