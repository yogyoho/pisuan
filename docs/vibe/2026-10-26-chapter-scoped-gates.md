# 分章管线门1/门2 按目标章裁剪（bug-4143 方案A）

> 日期：2026-10-26 ｜ 分支 pisuan-custom ｜ 触发：用户对话实测「只写第2章却被要求收全局7族」

## 需求与裁决

用户在分章编写实测中发现：声明只写第 2 章后，门 1 仍要求收齐全局 7 族（air/investment/mine_plan/noise/solid_waste/subsidence_params/water），其中 6 族是第 6/7/9 章才消费的。经查证数据消费事实（per_chapter：ch2 只消费 mine_plan + 逐章族 planning_indicators/economy/compliance_plans），裁定为「工程级开工条件」与「单章任务」的口径错配。三方案裁决：**A 按目标章裁剪（采纳）/ B 规程降档放行（否，矛盾后移）/ C 维持现状只解释（否，解决不了被卡）**。

## 裁剪口径

目标章集 C 的全局族 =（C 各章 sections 的 `{{SLOT:family.}}`/`{{TABLE:family}}` 引用族 ∪ C 消费公式族的 `FORMULA_FORM_DEPS` 依赖）∩ `global_families`。

- 公式键族（subsidence 等）经与 global_families 交集自然滤除。
- 未知章 id → 回退全量全局族（正确性优先，同 `resolve_scope` 的 SCOPE_FALLBACK）。
- 门 2 同口径切片冻结（派生常算块照常计算；后续章跨章公式推迟到 3a 增量冻结，setdefault 合并不重算）。

## 改动清单

| 文件 | 改动 |
|---|---|
| `scripts/derive_globals.py` | +`scope_globals(stage, chapter_ids)`（引用族推导，None=回退全量） |
| `scripts/ingest.py` | check 子命令 +`--chapters`；`GLOBAL_SCOPE:`/`GLOBAL_SCOPE_FALLBACK:` 日志 |
| `scripts/progress.py` | `run-stage freeze` +`--chapters` 透传（缺省全量零变化） |
| `scripts/tests/test_ingest_global_scope.py` | 新增 8 例（推导/集成/未知章回退/真数据健全性） |
| `scripts/tests/test_run_stage_chapters.py` | 新增 2 例（透传/缺省零变化） |
| `scripts/tests/test_global_families.py` | Namespace 补 chapters=None |
| `coal-eia-chapter-writer/SKILL.md` | 步骤1 目标章集+预告两栏 / 门1 裁剪 / 步骤2 切片冻结 / 3a 补收 / 速查表 |

脚本为 writer↔chapter-writer 双胞胎（sync_chapter_skill.py 同步，1152 文件字节一致）。

## 验收标准与实测

1. 空资料目录 + `--global-only --chapters ch2` → 只缺 mine_plan（原 7 族）✅ 容器 CLI 实测
2. 缺省（不带 --chapters）→ 行为字节级不变 ✅ test_freeze_default_full_unchanged + 既有 174 测试零回归
3. 双包测试各 176 全绿 ✅；ruff 新增行零错误（基线 29~30 不变）✅
4. 用户故事语义：第2章是定性章，门2 切片后零公式消费直接过 ✅（resolve_scope 空集合法）

## 连带发现与修复

- **bug-4144 栈漂移**：容器内两包测试数 176/172 不一致，暴露昨天 bug-4138/4139 的 4 个回归测试没同步进栈上 chapter-writer 的 `test_build_output_bug394.py`（文件在、内容旧）——整目录重落栈 + 双包 sha256 逐文件核对（drift=0）修复。教训：skill-sources 栈目录不经 sync-dev，技能脚本改动须两包全目录落栈并哈希核对，单文件手工 cp 易漏。
- 开题卡「结构声明」模板本身是技术口径（上一轮用户沟通规范的漏网点），writer/chapter-writer SKILL.md 模板已改业务措辞，数据预告补「数据族展示中文名、禁占位符记号」规则。

## 复测回归（bug-4145，同日）

- 现象：新会话实测预告卡仍 7 族全量。Langfuse trace（session `ac036794…`）实证三清白：技能激活正确（chapter-writer）、目标章集已记录（write_todos「先写第2章」）、沙箱脚本已是裁剪版（`--chapters`/`scope_globals`/`GLOBAL_SCOPE_FALLBACK` grep 全命中）。
- 根因：全会话 `ingest.py check` 零调用——agent 跳过门1，用 `ingest.py forms` 自查表单字段 + `data_expectations` 7 族直接组题；裁剪裁决只存在于门1 内部，跳过即全量。SKILL.md 步骤1「收集」(item3) 排在「门1」(item4) 之前给了逃逸口。
- 修复：步骤1 重排为「开题路由 → 门1 先行 → 缺项收集」（rc=0 不提问 / rc=2 缺项清单=预告卡唯一来源）+ 红线 P9「问什么由门1 裁决」。已落栈 skill-sources + skill-projections 四副本哈希核对，待新会话复测。
- 排查副产物：栈上技能三副本布局（skill-sources / skill-projections\_<uid>＝运行时+沙箱活挂载 / package/pisuan…buildin＝安装包非激活源）；package 副本停留在 10-25（含语言规范前），待重建链统一。Langfuse v4 events_only 下 v1 API 禁用，查 trace 直查 clickhouse `default.events_core`。

## ch2 全程复盘（bug-4146~4151，同日）

第 2 章写完后的全链路复盘（trace 9fbac13e + 终稿 state 副本重放门）：

- **bug-4146 mark 绕门（最重）**：02:06 门 FAIL（1714<14599）→ 降档放行 → 重写后 mark REVIEWED→CONFIRMED，终稿从未重跑门。state 副本重放实证：终稿 FAIL 3 项（S01 残留内部词「登记口径」；文风门 3 项全挂——数字密度 17.8/36.2、表密度 0、文表联动 1/13；深度 4227<14599）。**已 CONFIRMED ≠ 过门**。
- **bug-4147 样例来源错位（用户指认）**：写作全程范式上下文只有 references/paradigms 通用范式文档（模板库），0 次 samples_bank 样例切片读取、0 次 query_kb——SKILL.md 把切片注入写成契约项、模板检索写成「可选增强」，执行时双双落空。修复方向：samples_bank 同章片段包注入脚本化必做，paradigms 降级 fallback。
- **bug-4148 深度地板口径**：ch2 地板 14599 按样例整章（11 个三级节）折算，压在 4 节章投影上，结构性到不了 → 门恒 FAIL → 只能降档。地板须按投影节集折算或下沉节级。
- **bug-4149 深度基线双口径**：/tmp stage 拷贝改名致 build_output 注册表查找不中（stage_planning_eia vs planning_eia）走默认，gate 走注册 stage_path 按 14599——同章两口径。真源统一到 progress.json 的 stage_path。
- **bug-4150/4151 过程摩擦**：freeze rc=3 ×2 未停下处置；mark 语法错 ×2、发明 `--gate FAIL`、`| head` 遮蔽 rc。
- 正面实证：门1 裁剪实测生效（GLOBAL_SCOPE ['mine_plan']，零提问）；状态机非法转移拒绝生效；章门 13→11 项按节归因修复闭环在工作。

## 遗留

- 「本次必需 / 后续章可缓」两栏预告卡的实际卡面效果待下一轮对话实测回看。
- 王坡工程（eia-report）按用户裁定不作为测试对象；`eia-report-hengcheng-ch` 降档收口缺口（bug-4140）仍待裁决。
