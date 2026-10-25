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

## 遗留

- 「本次必需 / 后续章可缓」两栏预告卡的实际卡面效果待下一轮对话实测回看。
- 王坡工程（eia-report）按用户裁定不作为测试对象；`eia-report-hengcheng-ch` 降档收口缺口（bug-4140）仍待裁决。
