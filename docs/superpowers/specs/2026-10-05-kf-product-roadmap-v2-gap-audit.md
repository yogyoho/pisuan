# 知识工厂产物路线 v2 实现差距清单（排期输入）

> 日期：2026-10-05 ｜ 审计基线：pisuan-custom @ e227a57a
> 审计对象：[2026-10-05-kf-product-roadmap-v2-design.md](2026-10-05-kf-product-roadmap-v2-design.md)（同目录并排）
> 审计方法：符号搜索 + 文件存在性 + changelog 三方交叉实证，逐项留痕；无推测项
> 结论速览：**13 项拍板（AD-1~8）均为决策层批准；代码层仅 W0 窗口兑现（约 1/5），W1-W4 与 §9 八项拍板除埋点外全部未动**

---

## 1. 总览：spec §11 五窗口实现状态

| 窗口 | 内容 | 状态 | 落地证据 / 缺口 |
|---|---|---|---|
| W0 | bug-353/354 修复 + 取用率埋点 | **基本完成** | 见 §2.1；唯 bug-355 ETL 入口防护未做 |
| W1（spec 版） | P1-0/P1-2/P1-1a + 分类器收敛 | **未启动** | 见 §2.2 |
| W2 | 三层源文件 + 渲染器 + 语料适配度 | **未启动** | 见 §2.3 |
| W3 | scope×region 落库 | **未启动** | 见 §2.4 |
| W4 | 消费通道三期 | **未启动** | 见 §2.5 |

## 2. 逐项差距（附实证）

### 2.1 W0 —— 3.5/4 项

| 项 | 状态 | 实证 |
|---|---|---|
| bug-354 校验链字段 | ✅ | `pre_commit_validator.py:32` 读 `classify_type`；service 同族三处已修（changelog:102-103） |
| bug-353 match_count 自增 | ✅ | `domain_factory_service.py:182`（定义）/`:669`（调用）；2026-10-05 横城 ETL 真实流量 `match_count=1×40` 实证 |
| 取用率埋点 | ✅ | `domain_factory_tool_usage` 台账表 + 写手侧 4 工具接线（changelog:105） |
| bug-355 ETL 入口防护 | ❌ | 普查脚本侧已修（`.wolf/corpus-census/patched`），但 ETL 解析入口（`_etl_parse_stage` → `parse_document` 链）无 WPS 病态 docx 防护/显式告警（grep `PackageNotFoundError`/`BadZipFile` 零命中） |

### 2.2 W1（spec 版）—— 0/4 项

| 项 | 状态 | 实证 |
|---|---|---|
| P1-0 统一泛化双产物 | ❌ | 无「双产物/统一泛化/scope 建议」痕迹 |
| P1-1a 结构化输出通道 | ❌ | 泛化调用无 `response_format`/闭式类型词表 |
| P1-2 废弃叙述路径 | ❌ | `_extract_narrative_summaries` 仍在（`:908` 调用、`:3258` 定义）；`para["template"]` 写入路径（`:908` 附近）未移除 |
| 分类器收敛 5+1 | ❌ | `classify_paragraphs`（`:1622`）仍含 `narrative`/`parameter` 双轨类目（7 路未收敛） |

### 2.3 W2 —— 0/3 项

| 项 | 状态 | 实证 |
|---|---|---|
| 三层源文件 v1（5 骨架 + rules + 每章配置） | ❌ | `backend/templates/coal_mining/report_skeletons/` 目录不存在 |
| 渲染器（~100 行纯函数 + applied_rules 留痕） | ❌ | `backend/scripts/render_report_skeletons.py` 不存在 |
| 语料半自动标注 `conditions.json` | ❌ | `.wolf/corpus-census/` 仅 census/chapters/labels/patched，无 conditions.json |

### 2.4 W3 —— 0/4 项

| 项 | 状态 | 实证 |
|---|---|---|
| `DomainFactoryTask` +project_name/region_label/region_key | ❌ | 模型无这些列 |
| `DomainFactoryLearnedTemplate` +scope | ❌ | 无 scope 列 |
| 新表 `domain_factory_regional_facts` | ❌ | 全库零引用 |
| L1/L2/L3 归属判定 | ❌ | L2 依赖 P1-0 便车（未启动）；L1 classify_tags 通道未复活 |

### 2.5 W4 —— 0/3 项

| 项 | 状态 | 实证 |
|---|---|---|
| 一地区一 KB 运营规范 | ⏳ 文档层 | O1 已决（规范库 `kb_9ks49hyvfj` 成立），分库规范待写进 W4 运营文档 |
| `get_slot_registry` 独立工具 | ❌ | 全库零引用 |
| 导出端点 → PR-1 冷替换链 | ❌ | router 无 export 端点；changelog 无 PR-1 |

### 2.6 §9 Q4 八项拍板 —— 1/8

| # | 项 | 状态 | 实证 |
|---|---|---|---|
| PR-1 | references 冷替换口子 | ❌ 决策已批未落地 | 三重闸无实现 |
| M11 | gate1_code_checks 接线 | ❌ | 无 standards_check 痕迹 |
| M12 | 实体泄漏机械门 | ❌ | 无（changelog D1-D6 是另一批缺陷清理，勿混淆） |
| C5 | get_slot_registry | ❌ | 同 W4 |
| 埋点 | 取用率测量 | ✅ | 唯一已落地项 |
| M9 | v1 孤儿删除押后 | ⏳ 按决策不动 | 性质即「不做」，无欠账 |
| R4 | seed_gen README 人工通道 | ❌ | README/develop-guides 零命中 |
| cw_k | formula_runner 缺参破例记录 | ⏳ 决策已记 | vibe 文档 `:113` 有决策；脚本侧显式破例注释未见 |

## 3. 两个偏差说明（排期前必须知晓）

1. **窗口错位**：spec-W1 = P1-0/P1-2/P1-1a + 分类器收敛；但实际会话执行的「W1」窗口做的是 **bug-359 / bug-363 / bug-365** 三个缺陷项（bug-363/365 于 2026-10-05 收口推送）。spec-W1 四项被整体搁置，**无显式重排决策记录**——本清单即为补记录。
2. **勾账债**：W0 计划文档 `2026-10-05-w0-bugfix-and-usage-tracking.md` checkbox **0/31 未勾**，但工作实际完成且 changelog 落账。纯账面债，随手可清。

## 4. 排期依赖图（谁挡谁）

```
W2（三层+渲染器）──────────→ W2 验收（conditions.json 标注前置）
   │ 不依赖 W1；只依赖语料证据（已有）+ bug-353 埋点（已修）
   ↓
W4 导出端点 ←── W3（scope×region 落库）←── W1 P1-0（L2 归属便车）
                   ↑
spec-W1 验证（横城 ETL 重跑对比）←─ ⛔ agnes 免费档配额耗尽（2026-10-05 拍板 D 挂起）
bug-355 ETL 入口防护（独立小项，可入任意窗口）
O6/D2 时钟：写手侧 source 调用仍为 0（2026-10-05 实测）——模板线停机条款计时中
```

关键依赖事实：
- **spec-W1 的验证手段被外部阻塞**：横城 ETL 重跑对比需要 phase-2 泛化模型配额；agnes 免费档为耗尽型（非冷却窗口），恢复条件 = 用户升级 key / 换 provider / 接受本地 gguf 质量折衷（待拍板）。
- **W3 依赖 W1**：§4.2 L2 归属判定明确「搭 P1-0 统一泛化便车，零新增 LLM 调用」——P1-0 不做，W3 只能做 L1 规则 + L3 人工部分。
- **W2 完全可先行**：三层源文件与渲染器是确定性资产生产，不需要 W1 的任何产物；唯一前置是 conditions.json 标注（半天级人工 + 文件名校规则）。
- **W4 依赖 W3 的数据**：get_slot_registry 接口第一天带 scope/region/fact_type——表不存在则接口无从谈起。

## 5. 排期建议（供拍板，未定案）

| 序 | 候选 | 理由 | 体量感 |
|---|---|---|---|
| 1 | **W2 整窗先行**（三层文件 + 渲染器 + 标注 + §3.6 验收） | 唯一零阻塞窗口；产物直接兼容 v2 stage JSON 格式，消费者现成；PR-1 的第一用户 | 中（规则表数据已备于 spec §2/§3.3） |
| 2 | bug-355 ETL 入口防护 | 独立小项；等配额期间可清 | 小 |
| 3 | spec-W1（P1-0/P1-2/P1-1a + 分类器收敛） | 阻塞 W3；验证依赖配额恢复——代码可先写，横城对比跑押后 | 中大 |
| 4 | W3 → W4 | 顺序依赖如上图 | 大 |

约束重申（改模型/数据面时适用）：
- manager.py 上游共享 → 模型变更走 **additive 白名单**，改前 git 判定出处（spec §8.2）
- 工具层埋点改动 → tools.py 上游共享层先 git 判定出处（spec §9）
- 写手侧区域数值红线：只经 ingest 表单 → `{{TABLE}}` 渲染（spec §8.3）

## 6. 关联

- 审计会话：2026-10-05（横城 retry 第 2 跑同段会话），memory.md 20:22 条
- spec-W1 搁置期间实际执行的窗口项：bug-359（domain-unify-match-rule）、bug-363（静态模板激活）、bug-365（storage_path 迁移）
- 外部阻塞台账：bug-334（agnes 免费档三次观测 + 拍板 D 挂起）
