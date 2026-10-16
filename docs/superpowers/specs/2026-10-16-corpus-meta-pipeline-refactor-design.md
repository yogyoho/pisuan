# 语料元数据抽取管线重构设计（front-extract 侧车 + cover 层）

日期：2026-10-16 ｜ 状态：待用户评审 ｜ 分支：pisuan-custom

## 1. 背景与动机

- 语料元数据标注页（MetaPanel）与原型 s10 对比结论：UI 已对齐，差异在**数据映射**——原型的「文号/报告名」「编制单位」列在真实页没有对应数据。
- 报告名称在原始 docx **第一页封面**上（用户指认，实测证实：三段式「省份/主体名/环境影响报告书」+ 中文数字日期）。但 `prepare_corpus.py` 的边界说明明写「范围裁剪：首个节号标题之前的内容（封面/编制单位页）整体丢弃」——封面信息被管线有意丢弃，导致下游只能靠正文启发式反推。
- rid 由 `{目录排序位:03d}-{文件名ASCII残渣}` 生成，观感混乱；但**位置号语义保证幂等重跑 rid 逐字符稳定**，且已烙进切片文件名/bank_index/corpus_meta/DB，重编成本远超收益。
- 原始语料目录已定位：`C:\项目管理\样例文件\`（41 份 docx，与 manifest 31 份 + 10 份缺号对位文件完全吻合）。

## 2. 用户裁定记录（需求裁决）

1. **字段清单**：收 `report_title`（报告名）、`eia_org`（环评单位/编制单位）、`year`（年份）、`cover_scale`（封面总规模）、`project_no`（工程编号）；**文号不收**（实测 0/31，报告本体无批复文号，消费方未落地）；**建设单位不收**（原型无消费方）。
2. **省份升级**：封面标题命中法（`basis=cover`）插入既有 `manual > body频次` 之间——用户提出，实测支持（规划类标题 18/18 含省名）。
3. **报告范围**：41 → **33 份**（31 存量 + 九龙川 `011` + 巴拉素 `020` 两份新环评）；**4 份非环评体裁排除**（复垦方案×3、监测报告×1，用户裁定 a：本库只做环评报告书）；**4 份重复副本排除**（哈希后缀/旧版本）。
4. **rid 冻结**：存量 31 份 rid 不迁移；新收录份按目录排序位拿号（九龙川 `011-800-2026-2`、巴拉素 `020-2023-4`）；展示层报告名主显、rid 退为技术主键。
5. **方案乙**：front-extract 侧车脚本，31 份存量切片零接触；prepare_corpus 只为 2 份新环评做完整切片。

## 3. 实测证据（设计依据）

封面/前置区字段命中率（31 份全量，抽取器打磨后）：

| 字段 | 命中 | 备注 |
|---|---|---|
| 报告名（三段式拼接） | 29/31 | 规划类 18/18 全对；016/032 封面缺失待查（→needs_review 人工兜底）；028 封面本身有错别字（津毛湖/〈修编〉）→ 人工标注改写 |
| 封面日期→年份 | 28/31 | 中文数字（二〇二五年六月）与阿拉伯（2024年4月）双格式 |
| 环评单位（封面标签行） | 12/31 | 仅项目类有「环评单位：」标签；规划类需正文委托句兜底（实测噪声样本 007 类，须严格化正则） |
| 工程编号 | 26/31 | 形如 H75041Z / ZH7091BG / Z0078 / H05060(1)Z |
| 封面总规模 | 9/31 | 仅规划类；`矿区开发总规模：21.40 Mt/a` |
| 前置区文号 | 0/31 | 批复文号在报告外，不可抽取（用户裁定不收的依据） |

10 份缺号对位：6 份新文档（九龙川、巴拉素 = 环评；四季屯/红庆梁/郭家台复垦 = 排除；塔然高勒监测 = 排除）+ 4 份副本（横城-1、横城哈希、三塘湖哈希、郭家台4.14旧版 = 排除）。

## 4. 数据流

```
C:\项目管理\样例文件\*.docx (41)
  │
  ├─ front_extract.py（新，stdlib-only，zipfile+XML，不入 git 的 docx 只读）
  │    门1 体裁：文件名含 复垦|监测报告|水土保持 → 跳过 + stderr 记录
  │    门2 去重：--exclude 可重复参数（显式清单），出处记入 workdir manifest
  │    产出 references/samples_bank/front_matter.json（提交物，33 份，幂等 sort_keys）
  │
  ├─ prepare_corpus.py --only <文件名>…（现有脚本加 include 过滤参数）
  │    产出 011-800-2026-2 / 020-2023-4 切片 + manifest 条目
  │    （stage 默认 project_eia_underground，执行期人工过目定稿；存量 31 份切片零接触）
  │
  ├─ bank_compile.py 聚合重生成（31 份条目逐字符不变 + 2 份新增）
  │
  └─ corpus_meta.py（扩：--front-matter 读 front_matter.json，默认 samples_bank 下）
       31 → 33 份；reports 每条新增/升级字段见 §5
```

原始 docx 不入 git（大文件）；`front_matter.json` 记录 `source_file` + `source_sha1` 保证可追溯、可复现。

## 5. Schema 变更

### front_matter.json（每 rid 平铺，null = 未命中）

```json
{
  "007-3": {
    "source_file": "3灵台矿区总体规划（修编）环境影响报告书 .docx",
    "source_sha1": "…",
    "report_title": "甘肃省灵台矿区总体规划（修编）环境影响报告书",
    "eia_org": null,
    "eia_org_candidates": [],
    "year": 2025,
    "project_no": "H75041Z",
    "cover_scale_mt_a": 21.4
  }
}
```

抽取规则要点（精确正则/参数在实施计划中定稿）：
- **rid 推导（前置约束）**：front_extract 按目录**全量排序位（含被排除文件）**复算 `make_rid`，保证与 prepare_corpus 逐字符一致；体裁/去重两门在 rid 计算之后应用——否则新份 rid 与后续切片入库对不上。
- **report_title**：尾段命中《环境影响报告书|报告表|跟踪评价报告书|后评价报告书|环评报告书》结尾的段落，向前回溯拼接 ≤3 段短段（≤50 字、不含 年月/：/数字开头）。
- **eia_org**：封面标签行（`环评单位：`/`编制单位：`等）优先；正文委托句兜底——句含「委托…编制」、机构名 6–30 字、含机构后缀（有限公司|研究院|中心|大学），排除含 公告/第二次/基本 等噪声句；多值进 `eia_org_candidates`。
- **year**：`[〇零一二三四五六七八九]{4}年[一二三四五六七八九十]{1,3}月` 与 `\d{4}年\d{1,2}月` 双格式，转 int，范围守卫 2000–2100。
- **project_no**：`工程编号：` 行（含全角空格变体归一）。
- **cover_scale_mt_a**：`矿区?开发?总规模：` 行（行长 ≤40 防 prose 误捕），解析 float（Mt/a）。

### corpus_meta.json（schema 1 → 2，reports 条目）

| 字段 | 判定优先级 | basis 取值 |
|---|---|---|
| `report_title` / `report_title_basis`（新） | cover > DB人工（展示层覆盖） | `cover` / `needs_review` |
| `eia_org` / `eia_org_basis`（新） | cover 标签行 > 正文委托句 > 无 | `cover` / `body` / `needs_review` |
| `year_hint` / `year_basis`（升级） | 人工 ann > 封面日期 | `manual` / `cover` |
| `province` / `province_basis`（升级） | 人工 ann > **封面标题含省名 > 封面首段省名开头** > 正文频次（既有 detect_province） | `manual` / `cover` / `regex` / `needs_review` |
| `project_no`（新） | 封面直取 | 无需 basis（单一来源） |
| `scale_candidates`（升级） | 封面总规模追加为候选（`label=封面总规模`，按值去重），仅 scale_basis=needs_review 时注入 | 不变 |

`detect_province(text, ann)` 签名扩 front 参数；build_corpus_meta 增 front_matter 入参。**人工层优先级不变**：DB 标注永远压过自动层（`list_reports` 的 `ann.get(x, auto_x)` 机制零改动）。

## 6. 服务层（eia_meta_service.py）

- `_ANNOTATION_FIELDS` 扩为 `{"year_hint", "scale_mt_a", "report_title", "eia_org"}`；新增两字段校验：非空 strip 字符串 ≤200 字；`_validate_annotations` 对应扩展。
- `list_reports` 每个 item 增：`auto_report_title`、`auto_eia_org`、`project_no`、`report_title_basis`、`eia_org_basis`（province 已有，零改动）。
- `set_annotation` / `export_annotations` / `import_annotations` 逻辑零改动（白名单自动生效）。

## 7. 前端（MetaPanel.vue）

- 首列由裸 rid 改为**报告名主显 + rid 副显**（mono 小字），列数保持 7 不变。
- `report_title_basis`/`eia_org_basis` 为 needs_review 时打黄点（同规模 needs_review 惯例）。
- 标注弹窗增「报告书名」「编制单位」输入框，预填自动层值。
- 初始化骨架列宽同步调整（延续 16a3c1a6 的骨架工作）。

## 8. 测试与验收标准

| 层 | 测试 | 验收 |
|---|---|---|
| front_extract | `scripts/tests/test_front_extract.py`：测试内联构造最小 docx zip（stdlib），覆盖三段式标题/标签行/双格式日期/工程编号/封面规模/体裁门/排除门/字段缺失容错 | 33 份产出；31 存量 rid 逐一命中；8 份排除有 stderr + manifest 记录 |
| corpus_meta | 扩 `scripts/tests/test_corpus_meta.py`：cover 层合入、manual>cover、省份四级、scale_candidates 注入去重 | schema=2；幂等重跑字节一致 |
| service | 扩单测：新字段校验/合并/导出往返 | docker 内 pytest 过 |
| 前端 | prettier→sync→eslint 链路 + 浏览器 QA（isolatedContext，GET-only） | 报告名列 + 黄点 + 弹窗改写落库 + 导出物化往返 |

**整体验收**：
- AC1 corpus_meta.json 重编译 33 份；存量 31 份因 cover 层产生的值变化（province 修正/year_hint 补齐/scale 候选增加）**逐份 diff 表过目**，非 cover 类字段零漂移。
- AC2 九龙川/巴拉素 stage 人工确认后入库；词表抑制重扫出现新候选（预期行为）。
- AC3 028 封面错别字通过人工标注改写并被展示层正确覆盖（人工链路实证）。

## 9. 实施顺序建议（writing-plans 输入）

1. front_extract.py + 单测 → 跑出 front_matter.json（33 份）
2. corpus_meta.py cover 层 + 单测 → 重编译（31 份新字段）→ diff 表过目
3. prepare_corpus `--only` + bank_compile → 2 份新环评入库 → corpus_meta 再编译（33 份）
4. eia_meta_service 字段扩展 + 单测（docker pytest）
5. MetaPanel UI + 链路检查 + 浏览器 QA
6. changelog / 文档同步

## 10. 非目标（明确不做）

- 文号（用户裁定）、建设单位、rid 重编迁移
- 存量 31 份重新切片（bank 资产零风险红线）
- 横城多版本重裁（004 报批版已定稿）
- 写手溯源消费端（文号/机构引用功能另立项）
- 028 封面错别字自动纠正（人工标注改写，正好实证人工覆盖链路）
- 复垦方案/监测报告体裁（将来单独立项）

## 11. 开放项（计划期定稿）

- 标题拼接器精确参数（回溯段数/长度阈值的最终取值，以 33 份全量跑测为准）
- 委托句严格正则的最终形态（以噪声样本回归为准）
- 九龙川/巴拉素的 stage 人工确认（默认 project_eia_underground）
- MetaPanel 首列报告名+rid 的具体排版（同行 vs 次行）
- 016/032 封面缺失原因（图像封面/特殊版式）与 needs_review 呈现
