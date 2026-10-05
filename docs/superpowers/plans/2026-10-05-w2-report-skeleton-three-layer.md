# W2 条件化模板三层形态实施计划（三层源文件 v1 + 渲染器 + 语料适配度）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 roadmap v2 spec §3 产品一——条件化报告模板三层形态（骨架 + 变体规则 + 每章配置）、确定性渲染器、38 份语料适配度测试（≥36/38 槽位、≥30/38 章序）。

**Architecture:** 三层源文件 = repo 版本化 JSON 资产（`backend/templates/coal_mining/report_skeletons/`），零新表零后端运行时改动；渲染器为构建/交付脚本（`backend/scripts/`，纯函数无 LLM）；适配度测试以 census 数据副本为 fixture。渲染产物为 stage JSON 兼容格式，直接可过 `seed_gen.py` 消费方冒烟。

**Tech Stack:** Python 3.12+ / pytest / json（无新依赖）

**设计依据:** [2026-10-05-kf-product-roadmap-v2-design.md](../specs/2026-10-05-kf-product-roadmap-v2-design.md) §3；差距清单 [2026-10-05-kf-product-roadmap-v2-gap-audit.md](../specs/2026-10-05-kf-product-roadmap-v2-gap-audit.md) 排期序 1

---

## 全局上下文（implementer 必读）

1. **词汇权威源**：4 份既有 stage JSON 是语料定稿词汇——`backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/stages/{planning_eia, project_eia_openpit, project_eia_underground, post_eia, tracking_eia}.json`。其 `chapters` 为 `{"ch1": {"title": ..., "sections": {"ch1_S01": {"id","title","elements":[...]}, ...}}, ...}` dict。**layer-1 章题/节菜单从此派生，不凭记忆造章名**。
2. **语料数据**：`.wolf/corpus-census/{chapters,labels}.json`（41 份，键=docx 文件名）。`chapters.json` 条目 `{"chapters": [{"n": "1 总 论 5", "src": "toc"}]}`（章题带数字前缀+页码尾，需归一化）；`labels.json` 值 `{"family": "项目环评|规划环评|后评价|跟踪评价|复垦方案|简本?", "mine_type": "井工|露天|null", "revision_hint": bool}`。
3. **适配度宇宙 = 35 份（勘误）**：census 41 = 35 份四族完整章树 + 3 份复垦方案 + 简本（横城）+ 坏档（塔然高勒）+ 部分骨架（淖毛湖报批版）。spec §3.6 写「38」是把 3 份复垦计入——与 §3.7 非目标「不覆盖复垦方案族」矛盾，按非目标执行：复垦 3 份排除，适配宇宙 35。**阈值等比收紧**：spec ≥36/38（94.7%）→ **≥34/35**（97.1%）；≥30/38（78.9%）→ **≥28/35**（80%）。R6（total_control）唯一证据档郭家台系复垦、在宇宙外——规则保留（条件驱动），v1 无语料可测，如实记录。
4. **spec 内部张力裁决**：§3.3 注释「layer-1 5 份」vs §3.7 非目标「不覆盖复垦方案族」——**按 §3.7 执行，v1 建 4 族**（planning_eia / project_eia / post_eia / tracking_eia），复垦挂账 O5 不变。
5. **渲染器纯函数无 LLM**；任何步骤都不调用模型、不访问 DB、不写 `backend/package/`。
6. **禁碰文件**（严禁卷入提交）：`backend/package/yuxi/agents/buildin/chatbot/prompt.py`、`backend/server/utils/lifespan.py`、`web/src/components/AgentChatComponent.vue`、`web/src/components/SettingsModal.vue`、`docs/superpowers/specs/2026-09-30-coal-eia-writer-v2-port-design.md`（他会话未提交改动）。提交只用明确列出的 `git add <files>`。
7. **提交信息**：中文 Conventional Commits + `Co-Authored-By: Claude Code <noreply@anthropic.com>`。测试放 `backend/test/`，本计划用 `backend/test/unit/`；fixtures 放 `backend/test/data/corpus_census/`（该 data 目录已存在）。
8. **Windows 宿主跑 python**：本计划全部脚本在宿主 Git-Bash 跑（`python` 即系统 python，仅标准库）。容器内不需要。
9. census 章题归一化对照（渲染题 → 语料题）靠 **aliases 别名表**，别名从语料自动聚类派生（Task 2 派生脚本），人工过目后入库——禁止静默匹配。

---

### Task 1: conditions.json 半自动标注 + 语料 fixtures 入库

**Files:**
- Create: `.wolf/corpus-census/conditions.json`（38 份 6 维条件 + 排除记录，本地证据链）
- Create: `backend/test/data/corpus_census/{chapters,labels,conditions}.json`（测试 fixture 副本，入库）

- [ ] **Step 1: 写派生脚本（ad-hoc，不提交）并存到 `.wolf/corpus-census/derive_conditions.py`**

```python
"""从 labels/chapters 派生 38 份 6 维条件标注。运行: python derive_conditions.py"""
import json, re
from pathlib import Path

CENSUS = Path('.wolf/corpus-census')
labels = json.loads((CENSUS/'labels.json').read_text(encoding='utf-8'))
chapters = json.loads((CENSUS/'chapters.json').read_text(encoding='utf-8'))

FAMILY_MAP = {'规划环评': 'planning_eia', '项目环评': 'project_eia',
              '后评价': 'post_eia', '跟踪评价': 'tracking_eia'}
MINE_MAP = {'井工': 'underground', '露天': 'openpit'}

def norm(s: str) -> str:
    s = re.sub(r'\s+', '', s)
    s = re.sub(r'\d+$', '', s)                       # 尾页码
    s = re.sub(r'^第?[一二三四五六七八九十\d]+\s*[章节篇][\s\.、：:]*', '', s)
    s = re.sub(r'^\d+(\.\d+)*[\s\.、：:]*', '', s)     # 数字前缀
    return s

SENSITIVE_KW = [('胡杨林沙漠公园', '胡杨林沙漠公园'), ('沙漠公园', '胡杨林沙漠公园'),
                ('乡镇', '乡镇'), ('自然保护区', '自然保护区'), ('水源地', '水源地'),
                ('风景名胜区', '风景名胜区')]
GUIDELINE_KW = ('三线一单', '不确定性')   # revised2019 章级/节级标志（spec §2）
POLICY_KW = '总量控制'                     # total_control（郭家台 ch16 证据）

out, excluded = {}, []
for fname, lab in labels.items():
    chs = chapters.get(fname, {})
    titles = [norm(c['n']) for c in chs.get('chapters', [])]
    note = chs.get('note')
    reason = None
    if lab['family'] == '简本?': reason = '简本，非完整报告'
    elif note: reason = f'坏档：{note}'
    elif len(titles) < 5: reason = f'部分骨架（{len(titles)} 章）'
    if reason or lab['family'] not in FAMILY_MAP:
        excluded.append({'file': fname, 'family': lab['family'], 'reason': reason or '族不在 v1 范围（复垦挂账 O5）'})
        continue
    joined = ''.join(titles)
    conds = {
        'report_family': FAMILY_MAP[lab['family']],
        'mine_type': MINE_MAP.get(lab.get('mine_type')),
        'guideline_version': 'revised2019' if any(k in joined for k in GUIDELINE_KW) else 'legacy',
        'round': 'revision' if lab.get('revision_hint') else 'first',
        'sensitive_targets': sorted({tag for kw, tag in SENSITIVE_KW if kw in joined}),
        'policy_flags': ['total_control'] if POLICY_KW in joined else [],
        'exemptions': {},   # 院家风豁免登记处：{"order": true} 或 {"slots": ["章题"]}
    }
    out[fname] = conds

assert len(out) == 35, f'适配宇宙应 35 份（四族，复垦按 §3.7 排除），实得 {len(out)}'
(CENSUS/'conditions.json').write_text(
    json.dumps({'universe': out, 'excluded': excluded}, ensure_ascii=False, indent=2) + '\n',
    encoding='utf-8')
print(f'conditions: {len(out)} 份；excluded: {len(excluded)} 份')
for e in excluded: print('  -', e['file'][:40], '→', e['reason'])
```

- [ ] **Step 2: 运行并核对**

Run: `cd /c/workspace/pisuan && python .wolf/corpus-census/derive_conditions.py`
Expected: `conditions: 35 份；excluded: 6 份`，排除清单 = 横城简本/塔然高勒坏档/淖毛湖报批版 + 3 份复垦方案（§3.7 非目标）。**非 35 即停手上报**（派生规则或 census 数据问题）。

- [ ] **Step 3: 抽检 6 个代表性条件**

Run: `python -c "import json; d=json.load(open('.wolf/corpus-census/conditions.json',encoding='utf-8'))['universe']
for f,v in d.items():
    if '伊宁' in f or '横城' in f: print(f[:30], json.dumps(v, ensure_ascii=False))"`
人工核对：规划修编 → `round=revision`；含三线一单章的报告 → `guideline_version=revised2019`（预期少量，五间房/淖毛湖系）；井工项目环评 → `mine_type=underground`。异常值记入提交说明。

- [ ] **Step 4: fixtures 入库**

```bash
mkdir -p backend/test/data/corpus_census
cp .wolf/corpus-census/chapters.json .wolf/corpus-census/labels.json .wolf/corpus-census/conditions.json backend/test/data/corpus_census/
git add backend/test/data/corpus_census/chapters.json backend/test/data/corpus_census/labels.json backend/test/data/corpus_census/conditions.json
git commit -m "feat(w2): 语料 6 维条件标注 conditions.json + 适配度测试 fixtures

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 三层源文件 v1（4 族骨架 + rules + 每章配置）

**Files:**
- Create: `backend/templates/coal_mining/report_skeletons/{planning_eia,project_eia,post_eia,tracking_eia}.json`（layer-1）
- Create: `backend/templates/coal_mining/report_skeletons/rules.json`（layer-2）
- Create: `backend/templates/coal_mining/report_skeletons/{planning_eia,project_eia,post_eia,tracking_eia}-chapters.json`（layer-3）

- [ ] **Step 1: 写 layer-1 派生脚本（ad-hoc，不提交）存 `.wolf/corpus-census/derive_layer1.py`**

```python
"""从既有 stage JSON（语料定稿词汇）派生 layer-1 骨架。运行: python derive_layer1.py"""
import json
from pathlib import Path

STAGES = Path('backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/stages')
OUT = Path('backend/templates/coal_mining/report_skeletons')
OUT.mkdir(parents=True, exist_ok=True)

def load(sid): return json.loads((STAGES/f'{sid}.json').read_text(encoding='utf-8'))

def from_stage(sid, family, note):
    s = load(sid)
    order = [c['title'] for c in s['chapters'].values()]
    chapters = {}
    for cid, c in s['chapters'].items():
        chapters[c['title']] = {
            'slot_id': cid.upper(),
            'sections': [x['title'] for x in c.get('sections', {}).values()],
        }
    return {'family': family, 'base_source': sid, 'note': note,
            'canonical_order': order, 'optional_chapters': {}, 'chapters': chapters}

files = [
    from_stage('planning_eia', 'planning_eia', 'HJ463 规划环评 13 章定稿序'),
    from_stage('tracking_eia', 'tracking_eia', '跟踪评价独有 11 章骨架（淖毛湖跟踪）'),
]
# project_eia：合并 underground+openpit 两 stage（其差集恰为沉陷/爆破章）
ug, op = from_stage('project_eia_underground', 'project_eia', ''), from_stage('project_eia_openpit', 'project_eia', '')
merged_order, merged_ch = [], {}
for src in (ug, op):
    for t in src['canonical_order']:
        if t not in merged_ch:
            merged_ch[t] = src['chapters'][t]; merged_order.append(t)
files.append({'family': 'project_eia', 'base_source': 'project_eia_underground+project_eia_openpit',
              'note': '两矿型 stage 合并；沉陷(井工)/爆破(露天)为 optional，由 R1/R2 激活',
              'canonical_order': merged_order, 'optional_chapters': {}, 'chapters': merged_ch})
files.append(from_stage('post_eia', 'post_eia', 'v1 由 R8 从 project_eia 派生；本文件仅存已知差异节题（后评价口径）'))

# 规则可激活的槽位（spec §3.3 R1-R9 指名章）登记为 optional
EXTRA = {
    'planning_eia': {'三线一单及空间管控': ['三线一单', '空间管控'], '不确定性分析': ['不确定性', '环境不确定']},
    'project_eia': {'地表沉陷预测与影响评价': ['地表沉陷预测', '沉陷预测'], '爆破影响评价': ['爆破影响', '爆破'],
                    '总量控制': ['总量控制']},
    'post_eia': {'措施优化与调整': ['措施优化调整', '优化调整']},
}
for f in files:
    for t, aliases in EXTRA.get(f['family'], {}).items():
        if t not in f['chapters']:
            f['optional_chapters'][t] = {'aliases': aliases, 'sections': []}
    for t, ch in f['chapters'].items():
        ch['aliases'] = []
(OUT/'_layer1_draft.json').write_text(json.dumps(files, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('draft →', OUT/'_layer1_draft.json')
```

Run 后人工拆分为 4 份 `<family>.json`（键：`family/canonical_order/optional_chapters/chapters`；`chapters[题] = {slot_id, aliases, sections[]}`）。

- [ ] **Step 2: 从语料派生 aliases（ad-hoc）**

对 38 份语料的归一化章题做频次统计，凡与 layer-1 章题**不相等但编辑距离 ≤4 或含相同 4-gram** 的，登记进该章 `aliases`。示例（预期出现的真实对）：语料「总论」→ planning「总则」alias；「地表沉陷预测及影响评价」→「地表沉陷预测与影响评价」alias。**纯机械聚类 + 人工过目，禁止臆造**。统计脚本模板：

```python
import json, re
from collections import Counter
def norm(s):
    s = re.sub(r'\s+', '', s); s = re.sub(r'\d+$', '', s)
    s = re.sub(r'^第?[一二三四五六七八九十\d]+\s*[章节篇][\s\.、：:]*', '', s)
    return re.sub(r'^\d+(\.\d+)*[\s\.、：:]*', '', s)
chs = json.load(open('backend/test/data/corpus_census/chapters.json', encoding='utf-8'))
conds = json.load(open('backend/test/data/corpus_census/conditions.json', encoding='utf-8'))['universe']
freq = Counter()
for f in conds:
    for c in chs[f]['chapters']: freq[norm(c['n'])] += 1
# 输出按频次降序全部归一化章题 → 人工对照 layer-1 章题表登记 aliases
for t, n in freq.most_common(): print(n, t)
```

- [ ] **Step 3: 写 `rules.json`（layer-2，spec §3.3 R1-R9 原样落地）**

```json
{ "rules": [
  { "id": "R1", "when": {"report_family": "project_eia", "mine_type": "underground"},
    "add": ["地表沉陷预测与影响评价"], "remove": ["爆破影响评价"], "evidence": "井工 7/7 有沉陷章 0 爆破章" },
  { "id": "R2", "when": {"report_family": "project_eia", "mine_type": "openpit"},
    "add": ["爆破影响评价"], "remove": ["地表沉陷预测与影响评价"], "evidence": "露天 6/6 反之" },
  { "id": "R3", "when": {"report_family": "planning_eia", "guideline_version": "revised2019"},
    "add": ["三线一单及空间管控", "不确定性分析"], "evidence": "五间房章级;淖毛湖报批版节级" },
  { "id": "R4", "when": {"report_family": "planning_eia", "round": "revision"},
    "require": ["回顾评价"], "evidence": "修编 18/18 必含回顾性评价章" },
  { "id": "R5", "when": {"sensitive_targets": "*"},
    "add_section_under": {"host": "预测与评价", "template": "对{sensitive_target}影响分析"}, "evidence": "淖毛湖 6.10/6.11" },
  { "id": "R6", "when": {"policy_flags": "total_control"},
    "add": ["总量控制"], "evidence": "郭家台 ch16" },
  { "id": "R8", "when": {"report_family": "post_eia"}, "base": "self",
    "note": "post_eia.json stage 已按『项目环评(露天)骨架+后评价口径章名』定稿（白音华 2/2），v1 直接用其 canonical；渲染器的 base 克隆+rename_suffix 机制保留，待第三份后评价语料需要时启用", "evidence": "白音华 2/2 沿用项目环评(露天)骨架" },
  { "id": "R9", "when": {"report_family": "tracking_eia"},
    "base": "self", "evidence": "淖毛湖跟踪 11 章独有骨架（canonical 即 standalone）" }
] }
```

注意 R7 缺号是有意的（spec 原文即无 R7，保持 id 对齐 spec 便于审计）。R8 用 self-base 是对 spec §3.3 的有记录偏离：base 克隆+改名机制在渲染器 `_resolve_base` 中保留可用，但 v1 数据不启用（理由见 note）——spec §2 实测后评价仅 2 份且 post_eia.json stage 已是该骨架的定稿。

- [ ] **Step 4: 写 layer-3 每章配置（v1 只配高频差异章，spec O2）**

`<family>-chapters.json` 格式：`{ "章题": { "depth": "deep|normal", "tables": ["表名"...], "sections": ["节菜单"...] } }`。v1 范围（spec §3.3 示例 + 高频差异）：project_eia 的「地表沉陷预测与影响评价」（depth=deep，tables=["地表沉陷敏感目标一览表","保护煤柱留设表","预测参数表"]，sections=["预测模型","预测参数","预测方案","移动变形预测","影响分析","岩移观测计划"]）、「爆破影响评价」（depth=deep，sections=["爆破器材与起爆方式","爆破安全距离","爆破影响预测","防护措施"]）；planning_eia 的「承载力分析」「综合论证」（depth=deep）；其余章 v1 不配置（渲染时缺省 depth=normal、无 tables、sections 取 layer-1）。**全量表单清单是 P2 数据作业（O2），不在本窗口**。

- [ ] **Step 5: 结构自检 + 提交**

Run: `python -c "
import json, pathlib
d = pathlib.Path('backend/templates/coal_mining/report_skeletons')
fams = ['planning_eia','project_eia','post_eia','tracking_eia']
for f in fams:
    l1 = json.loads((d/f'{f}.json').read_text(encoding='utf-8'))
    assert l1['family'] == f and l1['canonical_order'] and l1['chapters']
    assert all(t in l1['chapters'] for t in l1['canonical_order'])
    json.loads((d/f'{f}-chapters.json').read_text(encoding='utf-8'))
r = json.loads((d/'rules.json').read_text(encoding='utf-8'))
assert [x['id'] for x in r['rules']] == ['R1','R2','R3','R4','R5','R6','R8','R9']
print('layer files OK')"`
Expected: `layer files OK`

```bash
git add backend/templates/coal_mining/report_skeletons/planning_eia.json backend/templates/coal_mining/report_skeletons/project_eia.json backend/templates/coal_mining/report_skeletons/post_eia.json backend/templates/coal_mining/report_skeletons/tracking_eia.json backend/templates/coal_mining/report_skeletons/rules.json backend/templates/coal_mining/report_skeletons/planning_eia-chapters.json backend/templates/coal_mining/report_skeletons/project_eia-chapters.json backend/templates/coal_mining/report_skeletons/post_eia-chapters.json backend/templates/coal_mining/report_skeletons/tracking_eia-chapters.json
git commit -m "feat(w2): 条件化模板三层源文件 v1（4 族骨架+R1-R9 变体规则+每章配置）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 渲染器 `render_report_skeletons.py`

**Files:**
- Create: `backend/scripts/render_report_skeletons.py`

- [ ] **Step 1: 实现渲染器（完整代码如下）**

```python
"""条件化报告骨架渲染器（roadmap v2 spec §3.4）。

确定性纯函数，无 LLM。输入 6 维条件 + 三层源文件，输出 stage JSON 兼容骨架 +
applied_rules 留痕。属构建/交付脚本，非运行时组件。

用法:
  python backend/scripts/render_report_skeletons.py --conditions <conditions.json> \
      [--only <docx文件名>] --out <输出目录>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LAYER_DIR = Path(__file__).resolve().parent.parent / "templates/coal_mining/report_skeletons"
FAMILIES = ("planning_eia", "project_eia", "post_eia", "tracking_eia")


def _when_match(when: dict, conds: dict) -> bool:
    """when 子句匹配：标量键精确相等；sensitive_targets 支持通配 '*'；policy_flags 支持成员判断。"""
    for key, want in when.items():
        have = conds.get(key)
        if key == "sensitive_targets" and want == "*":
            if not have:
                return False
        elif key == "policy_flags":
            if want not in (have or []):
                return False
        elif have != want:
            return False
    return True


def _resolve_base(family: str, conds: dict, layers: dict, seen: tuple[str, ...] = ()) -> list[str]:
    """R8 base 派生：post_eia 从 project_eia 按 openpit 条件解析后克隆。防环：seen 记录链。"""
    if family in seen:
        raise ValueError(f"base 循环引用: {seen + (family,)}")
    l1 = layers[family]["l1"]
    rules = layers["rules"]
    base_rule = next((r for r in rules if r.get("base") and r["when"].get("report_family") == family), None)
    if base_rule and base_rule["base"] != "self":
        b = base_rule["base"]
        base_conds = {**conds, "report_family": b["family"], "mine_type": b.get("mine_type")}
        order = _resolve_base(b["family"], base_conds, layers, seen + (family,))
        suffix = base_rule.get("rename_suffix", "")
        return [t + suffix if suffix else t for t in order]
    return list(l1["canonical_order"])


def render(conds: dict, layers: dict) -> dict:
    """渲染单份骨架。conds=6 维条件；layers={family: {"l1":..., "l3":...}, "rules": [...]}."""
    family = conds["report_family"]
    l1, l3 = layers[family]["l1"], layers[family]["l3"]
    applied: list[str] = []

    order = _resolve_base(family, conds, layers)
    chapters: dict[str, dict] = {}
    for t in order:
        src = l1["chapters"].get(t, {})
        chapters[t] = {"slot_id": src.get("slot_id", ""), "sections": list(src.get("sections", []))}

    optional = l1.get("optional_chapters", {})
    for rule in layers["rules"]:
        if not _when_match(rule["when"], conds):
            continue
        rid = rule["id"]
        if rid == "R8" or rid == "R9":   # base 已在 _resolve_base 处理；此处仅留痕 add
            applied.append(rid)
        for t in rule.get("add", []):
            src = optional.get(t) or ({t: l1["chapters"][t]} if t in l1["chapters"] else None)
            if src is None:
                raise KeyError(f"{rid}: add 章不在 layer-1 词汇表: {t}")
            if t not in chapters:
                chapters[t] = {"slot_id": "", "sections": list(src.get("sections", []))}
            applied.append(rid)
        for t in rule.get("remove", []):
            chapters.pop(t, None)
            applied.append(rid)
        for t in rule.get("require", []):
            if t not in chapters:
                src = optional.get(t) or l1["chapters"].get(t)
                if src is None:
                    raise KeyError(f"{rid}: require 章无定义: {t}")
                chapters[t] = {"slot_id": src.get("slot_id", ""), "sections": list(src.get("sections", []))}
            applied.append(rid)
        if "add_section_under" in rule:
            spec_ = rule["add_section_under"]
            host, template = spec_["host"], spec_["template"]
            for target in conds.get("sensitive_targets", []):
                sec_title = template.replace("{sensitive_target}", target)
                for ch in chapters.values():
                    pass  # host 章定位在下方按题名处理
                host_ch = next((c for c in chapters if c == host or host in c), None)
                if host_ch and sec_title not in chapters[host_ch]["sections"]:
                    chapters[host_ch]["sections"].append(sec_title)
            applied.append(rid)

    # layer-3 覆盖（深度/表格/节菜单）
    for t, cfg in l3.items():
        if t in chapters:
            chapters[t].update({k: v for k, v in cfg.items() if k in ("depth", "tables", "sections")})

    out_chapters = {}
    for i, (t, body) in enumerate(chapters.items(), 1):
        secs = {f"ch{i}_S{j:02d}": {"id": f"ch{i}_S{j:02d}", "title": s} for j, s in enumerate(body["sections"], 1)}
        out_chapters[f"ch{i}"] = {
            "title": t,
            "slot_id": body["slot_id"],
            "depth": body.get("depth", "normal"),
            "sections": secs,
        }
    return {
        "version": "2.0-rendered",
        "stage_id": family,
        "generated_from": {"conditions": conds, "applied_rules": applied},
        "chapters": out_chapters,
    }


def load_layers() -> dict:
    layers: dict = {"rules": json.loads((LAYER_DIR / "rules.json").read_text(encoding="utf-8"))["rules"]}
    for fam in FAMILIES:
        layers[fam] = {
            "l1": json.loads((LAYER_DIR / f"{fam}.json").read_text(encoding="utf-8")),
            "l3": json.loads((LAYER_DIR / f"{fam}-chapters.json").read_text(encoding="utf-8")),
        }
    return layers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--conditions", required=True)
    ap.add_argument("--only", help="只渲染该 docx 文件名对应的条件")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.conditions).read_text(encoding="utf-8"))
    universe = {args.only: data["universe"][args.only]} if args.only else data["universe"]
    layers = load_layers()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    for fname, conds in universe.items():
        rendered = render(conds, layers)
        slug = "".join(c if c.isalnum() else "_" for c in fname)[:60]
        (outdir / f"{slug}.json").write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"RENDERED {fname[:40]} chapters={len(rendered['chapters'])} rules={rendered['generated_from']['applied_rules']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 冒烟——渲染 1 份井工项目环评**

Run: `python backend/scripts/render_report_skeletons.py --conditions backend/test/data/corpus_census/conditions.json --only "$(python -c "import json;d=json.load(open('backend/test/data/corpus_census/conditions.json',encoding='utf-8'))['universe'];print(next(f for f,v in d.items() if v['report_family']=='project_eia' and v['mine_type']=='underground'))")" --out /tmp/w2-smoke`
Expected: `RENDERED ... chapters=... rules=['R1']`（含沉陷章、无爆破章——`python -c "import json,glob; d=json.load(open(sorted(glob.glob('/tmp/w2-smoke/*.json'))[0],encoding='utf-8')); ts=[c['title'] for c in d['chapters'].values()]; assert any('沉陷' in t for t in ts) and not any('爆破' in t for t in ts); print('R1 生效 OK')"`）。

- [ ] **Step 3: 提交**

```bash
git add backend/scripts/render_report_skeletons.py
git commit -m "feat(w2): 条件化骨架渲染器（确定性纯函数+规则留痕，stage JSON 兼容输出）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 语料适配度测试 + 差异单

**Files:**
- Create: `backend/test/unit/test_report_skeleton_fit.py`

- [ ] **Step 1: 写测试（完整代码）**

```python
"""语料适配度测试（roadmap v2 spec §3.6）。

对 35 份语料（四族，复垦按 §3.7 排除）逐份渲染骨架，与 chapters.json 实测章树对比：
- 槽位集合完全匹配 >= 34/35（spec 36/38 等比收紧）
- 章序完全一致 >= 28/35（spec 30/38 等比收紧；声明院家风豁免后计）
不匹配项必须落差异单（--report 模式），改规则或登记豁免二选一，禁止静默忽略。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
FIXTURES = BACKEND / "test/data/corpus_census"
RENDERER = BACKEND / "scripts/render_report_skeletons.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("rrs", RENDERER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\d+$", "", s)
    s = re.sub(r"^第?[一二三四五六七八九十\d]+\s*[章节篇][\s\.、：:]*", "", s)
    return re.sub(r"^(\d+(\.\d+)*)[\s\.、：:]*", "", s)


def _alias_index(l1: dict) -> dict[str, str]:
    """归一化题/别名 → 章题。"""
    idx = {}
    for t, body in l1["chapters"].items():
        idx[_norm(t)] = t
        for a in body.get("aliases", []):
            idx[_norm(a)] = t
    for t, body in l1.get("optional_chapters", {}).items():
        idx.setdefault(_norm(t), t)
        for a in body.get("aliases", []):
            idx.setdefault(_norm(a), t)
    return idx


@pytest.fixture(scope="module")
def env():
    rrs = _load_renderer()
    layers = rrs.load_layers()
    conds = json.loads((FIXTURES / "conditions.json").read_text(encoding="utf-8"))
    chapters = json.loads((FIXTURES / "chapters.json").read_text(encoding="utf-8"))
    return rrs, layers, conds, chapters


FIT_UNIVERSE = json.loads((Path(__file__).resolve().parent.parent.parent / "test/data/corpus_census/conditions.json").read_text(encoding="utf-8"))["universe"]
FIT_FILES = sorted(FIT_UNIVERSE)


def test_universe_is_35():
    assert len(FIT_FILES) == 35


def _match_file(env, fname):
    """返回 (slot_hits: list[章题], corpus_titles: list[归一化题], unmatched: list)。"""
    rrs, layers, _, chapters = env
    rendered = rrs.render(FIT_UNIVERSE[fname], layers)
    rendered_titles = [c["title"] for c in rendered["chapters"].values()]
    l1 = layers[FIT_UNIVERSE[fname]["report_family"]]["l1"]
    idx = _alias_index(l1)
    hits, unmatched = [], []
    for c in chapters[fname]["chapters"]:
        t = _norm(c["n"])
        if t in idx:
            hits.append(idx[t])
        else:
            unmatched.append(t)
    return rendered_titles, hits, unmatched


@pytest.mark.parametrize("fname", FIT_FILES)
def test_per_file_slot_match(env, fname):
    _, hits, unmatched = _match_file(env, fname)
    exemptions = FIT_UNIVERSE[fname].get("exemptions", {}).get("slots", [])
    effective_unmatched = [t for t in unmatched if t not in exemptions]
    assert not effective_unmatched, f"{fname[:40]} 未命中槽位（差异单必须处理）: {effective_unmatched}"


def test_fit_thresholds(env):
    rrs, layers, _, chapters = env
    slot_ok, order_ok, diffs = 0, 0, []
    for fname in FIT_FILES:
        rendered_titles, hits, unmatched = _match_file(env, fname)
        ex = FIT_UNIVERSE[fname].get("exemptions", {})
        if not [t for t in unmatched if t not in ex.get("slots", [])]:
            slot_ok += 1
        else:
            diffs.append((fname, "slots", unmatched))
        rendered_set = [t for t in rendered_titles]
        hit_seq = [t for t in hits]
        expected = [t for t in rendered_set if t in set(hit_seq)]
        if expected == hit_seq or ex.get("order"):
            order_ok += 1
        else:
            diffs.append((fname, "order", list(zip(expected, hit_seq))))
    report = "\n".join(f"{k} {f[:40]}: {v}" for f, k, v in diffs)
    assert slot_ok >= 34, f"槽位匹配 {slot_ok}/35 < 34\n{report}"
    assert order_ok >= 28, f"章序匹配 {order_ok}/35 < 28\n{report}"
```

- [ ] **Step 2: 调参循环（预期需要 2-4 轮）**

Run: `python -m pytest backend/test/unit/test_report_skeleton_fit.py -x -q 2>&1 | tail -30`
对每份不匹配：**(a)** 改 layer-1 aliases（语料别名漏登记）或 **(b)** 改 rules.json（规则缺失/误加）或 **(c)** 在 conditions.json 该文件 `exemptions` 登记 `{"order": true}` 或 `{"slots": ["章题"]}`（院家风豁免，必须显式留痕）。禁止放宽阈值、禁止吞断言。
每轮记录：`slot_ok/order_ok` 数字轨迹，写入提交说明。

- [ ] **Step 3: 达标提交**

```bash
git add backend/test/unit/test_report_skeleton_fit.py backend/templates/coal_mining/report_skeletons/ backend/test/data/corpus_census/conditions.json
git commit -m "test(w2): 语料适配度测试达标（槽位 x/35 章序 y/35，差异单全处理）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

（x≥34、y≥28，以实际数字填。）

---

### Task 5: 渲染产物存档 + seed_gen 消费方冒烟

**Files:**
- Create: `backend/templates/coal_mining/report_skeletons/rendered/`（4 份代表条件渲染存档）

- [ ] **Step 1: 渲染 4 份代表条件存档**

```bash
python backend/scripts/render_report_skeletons.py --conditions backend/test/data/corpus_census/conditions.json --out backend/templates/coal_mining/report_skeletons/rendered --only "$(python -c "import json;d=json.load(open('backend/test/data/corpus_census/conditions.json',encoding='utf-8'))['universe'];print(next(f for f,v in d.items() if v['report_family']=='planning_eia' and v['round']=='first'))")"
# 依次对 planning_eia(revision)、project_eia(underground)、project_eia(openpit)、post_eia、tracking_eia 各渲染一份
# 每份产物重命名为 <stage_id>_<关键条件>.json（如 planning_eia_first.json / project_eia_underground.json）
git add backend/templates/coal_mining/report_skeletons/rendered/
```

- [ ] **Step 2: seed_gen 冒烟（真实消费方，spec §3.6-3）**

```bash
cd backend/package/yuxi/agents/skills/buildin/coal-eia-writer
python scripts/seed_gen.py gen --stage "C:/workspace/pisuan/backend/templates/coal_mining/report_skeletons/rendered/planning_eia_first.json" --output /tmp/w2-seed-planning.json
```
Expected: `SEED_READY: stage=...(planning_eia) chapters=13 sections=...` + `SEED_SELFCHECK` 通过（断言数 >0）。对 4 份存档各跑一次。
若 build_seed 因渲染产物缺字段报错：**把缺的字段加进渲染器输出**（这就是兼容契约的发现过程），在提交说明里记录「seed_gen 要求字段 X/Y/Z」，然后重跑。禁止改 seed_gen 本体。

- [ ] **Step 3: 提交**

```bash
git add backend/templates/coal_mining/report_skeletons/rendered/ backend/scripts/render_report_skeletons.py
git commit -m "feat(w2): 渲染产物存档 + seed_gen 消费方冒烟通过

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 收尾

- [ ] **Step 1: 格式检查**（宿主有 ruff 则跑；无则 `python -m py_compile backend/scripts/render_report_skeletons.py backend/test/unit/test_report_skeleton_fit.py`）
- [ ] **Step 2: changelog**——`docs/develop-guides/changelog.md` 的 `### pisuan 定制增量（2026-10-05）` 小节追加一行：`- feat(w2): 条件化报告模板三层形态落地（4 族骨架+R1-R9 规则+渲染器+38 份语料适配度 x/38、y/38，stage JSON 兼容产物经 seed_gen 冒烟）`
- [ ] **Step 3: 计划勾账**——本文 checkbox 全勾 + 执行记录（含调参轮次轨迹、豁免清单汇总）
- [ ] **Step 4: 提交**

```bash
git add docs/develop-guides/changelog.md docs/superpowers/plans/2026-10-05-w2-report-skeleton-three-layer.md
git commit -m "docs: w2 收尾——适配度数字落账 + changelog

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 完成定义（DoD）

1. `conditions.json`（38+3）+ 三层源文件（4 族 + rules + 4 份每章配置）+ 渲染器 + 适配度测试全部入库。
2. 适配度达标：槽位 ≥34/35、章序 ≥28/35（spec §3.6 勘误后口径，见全局上下文 3），差异单全处理（豁免显式留痕）。
3. 4 份渲染存档过 seed_gen 消费方冒烟（SEED_READY + selfcheck 断言 >0）。
4. 零运行时后端改动（`backend/package/`、`backend/server/` 无 diff）；零 LLM 调用。

## Out of scope

- 复垦方案族（O5 挂账）、全量表单清单（O2 → P2）、工厂侧登记（P2）、消费通道代码（P1-1b/W4）、运行时热替换（PR-1 三重闸另立）。
