# W2 v2 三条输入小窗 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解 W2 终审挂账三条——渲染器 add 锚点机制（爆破/R3 落位）、渲染顶层 stage/std_ref 真源化、fit 章序位移白名单（豁免 21→≤2）。

**Architecture:** 锚点为 l1 词汇属性（`optional_chapters.insert_after`），渲染器后置重排 pass 落位；stage 元数据从真源 stage JSON 逐字拷贝（D12 单一真源）；序差容差只在 fit 测试判定层（DFS 精确重插变换），渲染/消费链零感知。

**Tech Stack:** Python 3.12 stdlib（渲染器零依赖）；pytest；JSON fixtures。

**Spec:** [2026-10-06-w2-v2-three-input-window-design.md](../specs/2026-10-06-w2-v2-three-input-window-design.md)（§3 普查数据、§8 裁决记录为设计依据，实现疑问先查 spec）

---

## 执行上下文（每个 subagent 必读）

1. **禁碰文件**（严禁卷入提交，属他会话未提交改动）：`backend/package/yuxi/agents/buildin/chatbot/prompt.py`、`backend/server/utils/lifespan.py`、`web/src/components/AgentChatComponent.vue`、`web/src/components/SettingsModal.vue`、`docs/superpowers/specs/2026-09-30-coal-eia-writer-v2-port-design.md`、`docs/superpowers/plans/2026-09-30-coal-eia-writer-v2-port.md`、`docs/superpowers/plans/2026-10-05-w0-bugfix-and-usage-tracking.md`。提交只用明确列出的 `git add <files>`。
2. **提交规范**：中文 Conventional Commits + 尾行 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
3. **测试道**：本窗测试全部自包含（importlib 渲染器 + 读 repo JSON，不 import yuxi 包）→ 宿主机 `--noconftest` 道即可；容器复核道：`MSYS_NO_PATHCONV=1 docker run --rm -v "C:\workspace\pisuan\backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/<file> --noconftest -q`。
4. **不变量**：`backend/package/`、`backend/server/` 零 diff；slot_id 不重编号；阈值断言只升不降；禁静默兜底（fail loud）。
5. **ruff**：`cd backend && python -m ruff check <改动文件>`（line-length=120）；渲染器基线可能存少量存量错，要求**零新增**（报错行不在本次 diff hunk 内即可）。
6. 普查工具在 `.wolf/corpus-census/`（workshop，**不随本窗提交**；词条出处内联进 fixture evidence）。

---

### Task 1: 渲染器锚点机制 + l1 锚点词条

**Files:**
- Modify: `backend/scripts/render_report_skeletons.py`（新增 `_apply_anchors` + render() 接线一行）
- Modify: `backend/templates/coal_mining/report_skeletons/project_eia.json`（爆破词条 +1 字段）
- Modify: `backend/templates/coal_mining/report_skeletons/planning_eia.json`（两个 OPT 词条 +1 字段）
- Modify: `backend/templates/coal_mining/report_skeletons/rules.json`（R2/R3 evidence 注记）
- Test: `backend/test/unit/test_w2v2_render_window.py`（新建，本任务含锚点 5 例）

- [ ] **Step 1: 写失败测试**

新建 `backend/test/unit/test_w2v2_render_window.py`：

```python
"""W2 v2 三条输入小窗——渲染器锚点机制 + 顶层 stage/std_ref 单测。

自包含：importlib 渲染器 + 读 repo 真源 JSON，不依赖 yuxi 包（宿主 --noconftest 可跑）。
spec: docs/superpowers/specs/2026-10-06-w2-v2-three-input-window-design.md
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
RENDERER = BACKEND / "scripts" / "render_report_skeletons.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("rrs", RENDERER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _titles(rendered: dict) -> list[str]:
    return [c["title"] for c in rendered["chapters"].values()]


# ---- 锚点机制（Task 1）----


def test_openpit_blast_anchored_after_solidwaste():
    """R2 add 爆破按 insert_after 落固废之后（非尾部）。"""
    rrs = _load_renderer()
    conds = {"report_family": "project_eia", "mine_type": "openpit"}
    rendered = rrs.render(conds, rrs.load_layers())
    ts = _titles(rendered)
    assert "爆破环境影响评价" in ts
    assert ts.index("爆破环境影响评价") == ts.index("固体废物环境影响评价") + 1
    assert "R2" in rendered["generated_from"]["applied_rules"]


def test_underground_no_blast_no_r2():
    """井工：无爆破、无 R2（基线行为不回归）。"""
    rrs = _load_renderer()
    conds = {"report_family": "project_eia", "mine_type": "underground"}
    rendered = rrs.render(conds, rrs.load_layers())
    ts = _titles(rendered)
    assert "爆破环境影响评价" not in ts
    assert "R2" not in rendered["generated_from"]["applied_rules"]


def test_revised2019_r3_chapters_anchored():
    """R3 两章按锚落位：三线一单→论证后；不确定性→环管后。"""
    rrs = _load_renderer()
    conds = {"report_family": "planning_eia", "guideline_version": "revised2019"}
    rendered = rrs.render(conds, rrs.load_layers())
    ts = _titles(rendered)
    assert ts.index("三线一单及空间管控") == ts.index("规划方案综合论证及优化调整建议") + 1
    assert ts.index("不确定性分析") == ts.index("环境管理、监测计划与跟踪评价") + 1
    assert "R3" in rendered["generated_from"]["applied_rules"]


def _mini_layers(insert_after: str | None):
    """合成三层：3 canonical 章 + 1 optional 章（可选锚）。"""
    chapters = {
        t: {"slot_id": f"CH{i}", "aliases": [], "sections": [], "key_elements": [], "writing_patterns": []}
        for i, t in enumerate(["甲章", "乙章", "丙章"], 1)
    }
    opt = {"slot_id": "OPT_9", "aliases": [], "sections": [], "key_elements": [], "writing_patterns": []}
    if insert_after:
        opt["insert_after"] = insert_after
    l1 = {"canonical_order": ["甲章", "乙章", "丙章"], "chapters": chapters, "optional_chapters": {"附加章": opt}}
    return {"planning_eia": {"l1": l1, "l3": {}}, "rules": [{"id": "RA", "when": {}, "add": ["附加章"]}]}


def test_anchor_missing_fails_loud():
    rrs = _load_renderer()
    with pytest.raises(KeyError, match="锚章不在渲染集"):
        rrs.render({"report_family": "planning_eia"}, _mini_layers("不存在的章"))


def test_no_anchor_appends_tail():
    """无锚词条维持旧行为（尾部追加），向后兼容。"""
    rrs = _load_renderer()
    rendered = rrs.render({"report_family": "planning_eia"}, _mini_layers(None))
    assert _titles(rendered)[-1] == "附加章"
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `cd backend && python -m pytest test/unit/test_w2v2_render_window.py --noconftest -q`
Expected: `test_openpit_blast_anchored_after_solidwaste` 与 `test_revised2019_r3_chapters_anchored` FAIL（爆破/两 OPT 章在尾部）；`test_anchor_missing_fails_loud` FAIL（无锚机制不 raise）；其余 3 例 PASS。

- [ ] **Step 3: 实现锚点机制**

`backend/scripts/render_report_skeletons.py`——在 `_copy_ch` 之后（:62 附近）新增：

```python
def _apply_anchors(chapters: dict, l1: dict) -> None:
    """W2v2 spec §4.1 后置重排：在场章若 l1 optional 词条声明 insert_after，摘出重插到锚章之后。

    同锚多章按处理序稳定；锚章不在场 fail loud（禁静默）；无锚词条维持现位；
    链式锚（锚章自身被锚定）有限轮收敛，不收敛即 ValueError。
    """
    anchors = {
        t: spec_["insert_after"]
        for t, spec_ in l1.get("optional_chapters", {}).items()
        if t in chapters and spec_.get("insert_after")
    }
    if not anchors:
        return
    missing = sorted({a for a in anchors.values() if a not in chapters})
    if missing:
        raise KeyError(f"insert_after 锚章不在渲染集: {missing}")
    for _ in range(len(anchors) + 1):
        keys = list(chapters)
        changed = False
        for a in anchors:
            i = keys.index(a)
            if i != keys.index(anchors[a]) + 1:
                keys.pop(i)
                keys.insert(keys.index(anchors[a]) + 1, a)
                changed = True
        if not changed:
            return
        reordered = {k: chapters[k] for k in keys}
        chapters.clear()
        chapters.update(reordered)
    raise ValueError(f"insert_after 链不收敛: {anchors}")
```

`render()` 内、l3 覆盖循环之后、`# 输出章键` 注释之前（:131 附近）插入一行：

```python
    # W2v2 spec §4.1：锚点后置重排（optional 章 insert_after）——add/require 落位与规则解耦
    _apply_anchors(chapters, l1)
```

- [ ] **Step 4: l1 词条 + rules 注记**

`project_eia.json` → `optional_chapters["爆破环境影响评价"]` 末尾加：

```json
    "insert_after": "固体废物环境影响评价"
```

`planning_eia.json` → `optional_chapters["三线一单及空间管控"]` 末尾加：

```json
    "insert_after": "规划方案综合论证及优化调整建议"
```

`optional_chapters["不确定性分析"]` 末尾加：

```json
    "insert_after": "环境管理、监测计划与跟踪评价"
```

`rules.json` → R2 的 `"evidence": "露天 6/6 反之"` 改为：

```json
      "evidence": "露天 6/6 反之；锚点=固废后（普查 2026-10-06：4/5 位于固废→风险空档）"
```

R3 的 `"evidence": "五间房章级;淖毛湖报批版节级"` 改为：

```json
      "evidence": "五间房章级;淖毛湖报批版节级；锚点：三线一单→论证后、不确定性→环管后（普查 2026-10-06，n=1 五间房）"
```

- [ ] **Step 5: 跑测试确认 GREEN**

Run: `cd backend && python -m pytest test/unit/test_w2v2_render_window.py test/unit/test_report_skeleton_fit.py --noconftest -q`
Expected: 5 passed + 37 passed（fit 37 例不受影响——order 判定还是旧逻辑，锚点只改变 openpit/revised2019 渲染序，其 5 份在豁免清单内）。
若 fit 出现非豁免文件新 fail：停下核查 `_apply_anchors` 是否误伤 canonical 序（不应——锚只作用于 l1 optional 词条声明的章）。

- [ ] **Step 6: ruff + 提交**

Run: `cd backend && python -m ruff check scripts/render_report_skeletons.py test/unit/test_w2v2_render_window.py`
Expected: 零新增（存量错行不在本次 diff 内）。

```bash
git add backend/scripts/render_report_skeletons.py backend/templates/coal_mining/report_skeletons/project_eia.json backend/templates/coal_mining/report_skeletons/planning_eia.json backend/templates/coal_mining/report_skeletons/rules.json backend/test/unit/test_w2v2_render_window.py
git commit -m "feat(w2v2): 渲染器锚点机制——optional 章 insert_after 后置重排 + 爆破/R3 三锚点词条落账

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 渲染顶层 stage/std_ref 真源化

**Files:**
- Modify: `backend/scripts/render_report_skeletons.py`（新增 `STAGES_DIR` + `_stage_meta`；`render()` 接线两处）
- Test: `backend/test/unit/test_w2v2_render_window.py`（追加 3 例）

- [ ] **Step 1: 写失败测试**（追加到 test_w2v2_render_window.py）

```python
# ---- 顶层 stage/std_ref（Task 2）----


def test_stage_meta_derives_by_mine_type():
    """project 族按矿型拼 stage_id，其余族直用 family；字段从真源逐字可读。"""
    rrs = _load_renderer()
    assert rrs._stage_meta({"mine_type": "openpit"}, "project_eia")["stage_id"] == "project_eia_openpit"
    assert rrs._stage_meta({"mine_type": "underground"}, "project_eia")["stage_id"] == "project_eia_underground"
    meta = rrs._stage_meta({}, "planning_eia")
    assert meta["stage_id"] == "planning_eia"
    assert meta["stage"] and meta["std_ref"]  # 真源非空


def test_stage_meta_missing_stage_fails_loud():
    rrs = _load_renderer()
    with pytest.raises(FileNotFoundError):
        rrs._stage_meta({"mine_type": "nonexistent"}, "project_eia")


def test_rendered_top_level_fields():
    """渲染产物顶层三件套非空且 stage_id 为真值（不再用 family 冒充）。"""
    rrs = _load_renderer()
    rendered = rrs.render({"report_family": "project_eia", "mine_type": "openpit"}, rrs.load_layers())
    assert rendered["stage_id"] == "project_eia_openpit"
    assert rendered["stage"]
    assert rendered["std_ref"]
```

- [ ] **Step 2: 跑测试确认 RED**

Run: `cd backend && python -m pytest test/unit/test_w2v2_render_window.py --noconftest -q`
Expected: 新 3 例 FAIL（`_stage_meta` 不存在 → AttributeError）；Task 1 的 5 例仍 PASS。

- [ ] **Step 3: 实现**

`render_report_skeletons.py`——`LAYER_DIR` 行（:18）之后加：

```python
STAGES_DIR = (
    Path(__file__).resolve().parent.parent
    / "package/yuxi/agents/skills/buildin/coal-eia-writer/references/stages"
)
```

`_apply_anchors` 之前（或之后）加：

```python
def _stage_meta(conds: dict, family: str) -> dict:
    """W2v2 spec §4.2 stage 元数据：project 族按矿型拼 stage_id，其余族直用 family。

    真源 = references/stages/{stage_id}.json（D12 单一真源），字段逐字拷贝；
    stage 文件不存在或 project 缺 mine_type → fail loud。
    """
    stage_id = f"{family}_{conds['mine_type']}" if family == "project_eia" else family
    path = STAGES_DIR / f"{stage_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"stage_id 推导失败，真源不存在: {path}")
    src = json.loads(path.read_text(encoding="utf-8"))
    return {"stage": src["stage"], "stage_id": stage_id, "std_ref": src["std_ref"]}
```

`render()` 开头 `family = conds["report_family"]`（:66）之后加：

```python
    meta = _stage_meta(conds, family)  # fail fast：条件→真源映射先于任何渲染工作
```

`return {` 块（:155-160）改为：

```python
    return {
        "version": "2.0-rendered",
        "stage": meta["stage"],
        "stage_id": meta["stage_id"],
        "std_ref": meta["std_ref"],
        "generated_from": {"conditions": conds, "applied_rules": applied},
        "chapters": out_chapters,
    }
```

- [ ] **Step 4: 跑测试确认 GREEN + 全量回归**

Run: `cd backend && python -m pytest test/unit/test_w2v2_render_window.py test/unit/test_report_skeleton_fit.py --noconftest -q`
Expected: 8 passed + 37 passed（fit 的 env fixture 走真源 conds，project 族渲染现要求 conds 含 mine_type——universe 35 份全带，若有缺 → 该份条件数据缺陷，如实上报裁决）。

- [ ] **Step 5: ruff + 提交**

Run: `cd backend && python -m ruff check scripts/render_report_skeletons.py test/unit/test_w2v2_render_window.py`

```bash
git add backend/scripts/render_report_skeletons.py backend/test/unit/test_w2v2_render_window.py
git commit -m "feat(w2v2): 渲染顶层 stage/std_ref 真源化——stage_id 按条件推导（project 族拼矿型）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 6 存档重渲 + seed_gen 冒烟复跑

**Files:**
- Modify: `backend/templates/coal_mining/report_skeletons/rendered/`（6 份全部重渲覆盖）

- [ ] **Step 1: 重渲 6 份存档**

每份 `--only` 渲染单件到临时目录（main() 只写一个 slug 文件），再覆盖归档名：

```bash
cd /c/workspace/pisuan
R=backend/templates/coal_mining/report_skeletons/rendered
C=backend/test/data/corpus_census/conditions.json
render_one() {  # $1=归档名  $2=universe 条件表达式（变量 v）
  f=$(python -c "
import json
d = json.load(open('$C', encoding='utf-8'))['universe']
print(next(f for f, v in d.items() if $2))")
  python backend/scripts/render_report_skeletons.py --conditions "$C" --only "$f" --out /tmp/w2v2-render
  mv /tmp/w2v2-render/*.json "$R/$1"
}
render_one planning_eia_first.json        "v['report_family']=='planning_eia' and v.get('round')=='first'"
render_one planning_eia_revised2019.json  "v['report_family']=='planning_eia' and v.get('guideline_version')=='revised2019'"
render_one project_eia_underground.json   "v['report_family']=='project_eia' and v.get('mine_type')=='underground'"
render_one project_eia_openpit.json       "v['report_family']=='project_eia' and v.get('mine_type')=='openpit'"
render_one post_eia.json                  "v['report_family']=='post_eia'"
render_one tracking_eia.json              "v['report_family']=='tracking_eia'"
```

- [ ] **Step 2: 变更范围核对 + 双跑字节级稳定**

Run: `git diff --stat backend/templates/coal_mining/report_skeletons/rendered/` 然后 `bash` 重复 Step 1 全部命令再跑一次 `git diff --stat`。
Expected: 6 份全变；diff 内容 = 顶层三字段（4 份仅此）+ openpit 爆破位/沉陷移除 + revised2019 两 OPT 章位；第二次运行后 diff 与第一次**完全相同**（byte-identical，确定性铁证）。若第二次 diff 变化 → 渲染器存在非确定性，必须查因。

- [ ] **Step 3: seed_gen 冒烟复跑（4 完整 + 2 结构断言）**

```bash
cd backend/package/yuxi/agents/skills/buildin/coal-eia-writer
G=C:/workspace/pisuan/backend/templates/coal_mining/report_skeletons/rendered
python scripts/seed_gen.py gen --stage "$G/planning_eia_first.json" --output /tmp/w2v2-seed-planning.json
python scripts/seed_gen.py gen --stage "$G/project_eia_underground.json" --output /tmp/w2v2-seed-underground.json
python scripts/seed_gen.py gen --stage "$G/post_eia.json" --output /tmp/w2v2-seed-post.json
python scripts/seed_gen.py gen --stage "$G/tracking_eia.json" --output /tmp/w2v2-seed-tracking.json
```

Expected（每条）：`SEED_READY: stage=<中文显示名>` **显示名非空**（W2 时为空——本窗 DoD②）+ `SEED_SELFCHECK` 通过。**不传 `--depth-targets`**——W2 曾须显式传（stage_id 失配），本窗修复后按 stage_id 默认推断必须自洽（project_eia_underground → project_eia_underground.json），失败即缺陷，禁止加回显式 flag 掩盖。断言数量级对照 W2：planning 454 / underground 589 / post 469 / tracking 294（章集未变，应逐位一致）。

结构断言（openpit 必缺 2 键喂 depth FAIL 属设计行为，禁造表）：

```bash
python - <<'EOF'
import json
g = json.load(open("C:/workspace/pisuan/backend/templates/coal_mining/report_skeletons/rendered/project_eia_openpit.json", encoding="utf-8"))
ts = [c["title"] for c in g["chapters"].values()]
ks = list(g["chapters"])
i_b, i_s = ts.index("爆破环境影响评价"), ts.index("固体废物环境影响评价")
assert i_b == i_s + 1, f"爆破未落固废后: {ts}"
assert "地表沉陷预测及影响评价" not in ts and "R2" in g["generated_from"]["applied_rules"]
assert all(k == k.lower() for k in ks), "章键必须小写"
print(f"openpit OK: {len(ks)} 章, 爆破@{i_b} 固废后")
r = json.load(open("C:/workspace/pisuan/backend/templates/coal_mining/report_skeletons/rendered/planning_eia_revised2019.json", encoding="utf-8"))
assert "opt_1" in r["chapters"] and "opt_2" in r["chapters"] and "R3" in r["generated_from"]["applied_rules"]
print(f"revised2019 OK: {len(r['chapters'])} 章 含 OPT×2")
EOF
```

顺手探针（结果两可，均合法）：revised2019 若 depth_targets/planning_eia.json 含 OPT_N 键则 gen 可过——过了就升级为第 5 份完整冒烟并记录；不过（缺键 FAIL）保持结构断言并记录。

- [ ] **Step 4: depth_targets 文件名对齐核对**

Run: `ls backend/package/yuxi/agents/skills/buildin/coal-eia-writer/references/depth_targets/`
Expected: 5 文件名与 6 份存档的 stage_id 推导值一一对应（planning_eia 双变体共享）。渲染产物 `stage_id` 抽查：`python -c "import json,glob; [print(f.split('/')[-1], json.load(open(f,encoding='utf-8'))['stage_id']) for f in glob.glob('backend/templates/coal_mining/report_skeletons/rendered/*.json')]"`

- [ ] **Step 5: 提交**

```bash
git add backend/templates/coal_mining/report_skeletons/rendered/
git commit -m "feat(w2v2): 6 存档重渲——爆破/R3 落锚位 + 顶层 stage/std_ref 真源化；seed_gen 冒烟 4+2 复跑过

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: fit order 位移白名单 + 豁免收敛

**Files:**
- Create: `backend/test/data/corpus_census/order_whitelist.json`
- Modify: `backend/test/unit/test_report_skeleton_fit.py`（判定升级 + 阈值 33 + 豁免 ≤2 断言）
- Modify: `backend/test/data/corpus_census/conditions.json`（order 豁免收缩）

- [ ] **Step 1: 写白名单 fixture**

`backend/test/data/corpus_census/order_whitelist.json`（初值 = spec §3.3 + 复测补 1 条，共 11 条）：

```json
{
  "comment": "fit order 位移白名单——词条=章可重插到允许前置章之后。出处：.wolf/corpus-census 普查 2026-10-06（35 份语料 hit 邻居统计），复测以 fit 测试 + classify_order_divergence 为准。",
  "moves": [
    {"chapter": "环境管理、监测计划与跟踪评价", "family": "planning_eia",
     "after": ["规划方案综合论证及优化调整建议", "公众参与", "矿区清洁生产与循环经济分析", "不确定性分析"],
     "evidence": "论证后10x/公众参与后6x/清洁生产后1x/不确定性后1x"},
    {"chapter": "环境影响识别与评价指标体系", "family": "planning_eia",
     "after": ["区域自然和社会经济概况"],
     "evidence": "区域概况后3x（canonical 回顾后14x 不受影响）"},
    {"chapter": "规划方案综合论证及优化调整建议", "family": "planning_eia",
     "after": ["不确定性分析"],
     "evidence": "五间房1x（不确定性后）"},
    {"chapter": "矿区清洁生产与循环经济分析", "family": "planning_eia",
     "after": ["规划实施环境影响减缓措施"],
     "evidence": "减缓后2x"},
    {"chapter": "资源综合利用与清洁生产评价", "family": "project_eia",
     "after": ["环境风险影响评价", "环境管理与环境监测计划", "环境经济损益分析", "土壤环境影响评价", "项目选址环境可行性"],
     "evidence": "风险后6x/环管后5x/损益后1x/土壤后1x/选址后1x"},
    {"chapter": "环境空气影响评价", "family": "project_eia",
     "after": ["地下水环境影响评价"],
     "evidence": "地下水后6x"},
    {"chapter": "固体废物环境影响评价", "family": "project_eia",
     "after": ["土壤环境影响评价", "地表水环境影响评价"],
     "evidence": "土壤后6x/地表水后1x"},
    {"chapter": "污染物排放总量控制分析", "family": "project_eia",
     "after": ["项目选址环境可行性"],
     "evidence": "选址后2x（郭家台两份）"},
    {"chapter": "地表水环境影响评价", "family": "project_eia",
     "after": ["环境空气影响评价"],
     "evidence": "空气后5x"},
    {"chapter": "环境经济损益分析", "family": "project_eia",
     "after": ["资源综合利用与清洁生产评价", "项目选址环境可行性"],
     "evidence": "资源后5x/选址后1x（canonical 环管后7x 不受影响）"},
    {"chapter": "爆破环境影响评价", "family": "project_eia",
     "after": ["土壤环境影响评价"],
     "evidence": "土壤后2x（锚后 canonical=固废后 不受影响）"}
  ]
}
```

- [ ] **Step 2: 写判定升级的失败测试**

`test_report_skeleton_fit.py` 顶部 import 区加 `from collections import Counter`；`FIXTURES = ...` 行之后加：

```python
ORDER_WHITELIST = json.loads((FIXTURES / "order_whitelist.json").read_text(encoding="utf-8"))["moves"]
```

`test_fit_thresholds` 之前加判定函数：

```python
def _order_pass(expected: list[str], hit_seq: list[str], moves_by_chapter: dict[str, set[str]]) -> bool:
    """序差判定（W2v2 spec §4.3）：精确全等 OR hit_seq 可由 expected 经
    「摘 mover→重插允许前置章之后」精确到达（DFS，visited 去重，mover 可多次跳移）。
    multiset 不等直接 False（槽位异常归 slots 判定管）。"""
    if expected == hit_seq:
        return True
    if Counter(expected) != Counter(hit_seq):
        return False
    target = tuple(hit_seq)
    seen: set[tuple[str, ...]] = set()

    def dfs(seq: tuple[str, ...]) -> bool:
        if seq == target:
            return True
        if seq in seen:
            return False
        seen.add(seq)
        for i, ch in enumerate(seq):
            allowed = moves_by_chapter.get(ch)
            if not allowed:
                continue
            rest = seq[:i] + seq[i + 1:]
            for j, pred in enumerate(rest):
                if pred in allowed:
                    nxt = rest[: j + 1] + (ch,) + rest[j + 1:]
                    if nxt not in seen and dfs(nxt):
                        return True
        return False

    return dfs(tuple(expected))
```

`test_fit_thresholds` 整体替换为：

```python
def test_fit_thresholds(env):
    rrs, layers, _, chapters = env
    slot_ok, order_ok, diffs = 0, 0, []
    modes = {"natural": 0, "whitelist": 0, "exempt": 0}
    for fname in FIT_FILES:
        rendered_titles, hits, unmatched = _match_file(env, fname)
        ex = FIT_UNIVERSE[fname].get("exemptions", {})
        if not [t for t in unmatched if t not in ex.get("slots", [])]:
            slot_ok += 1
        else:
            diffs.append((fname, "slots", unmatched))
        hit_set = set(hits)
        expected = [t for t in rendered_titles if t in hit_set]
        hit_seq = list(hits)
        fam_moves: dict[str, set[str]] = {}
        for e in ORDER_WHITELIST:
            if e["family"] == FIT_UNIVERSE[fname]["report_family"]:
                fam_moves.setdefault(e["chapter"], set()).update(e["after"])
        if expected == hit_seq:
            order_ok += 1
            modes["natural"] += 1
        elif _order_pass(expected, hit_seq, fam_moves):
            order_ok += 1
            modes["whitelist"] += 1
        elif ex.get("order"):
            order_ok += 1
            modes["exempt"] += 1
        else:
            diffs.append((fname, "order", list(zip(expected, hit_seq))))
    report = "\n".join(f"{k} {f[:40]}: {v}" for f, k, v in diffs)
    summary = f"[natural={modes['natural']} whitelist={modes['whitelist']} exempt={modes['exempt']}]"
    assert slot_ok >= 34, f"槽位匹配 {slot_ok}/35 < 34\n{report}"
    assert order_ok >= 33, f"章序匹配 {order_ok}/35 < 33 {summary}\n{report}"
    assert modes["exempt"] <= 2, f"order 豁免 {modes['exempt']} 份 > 2 {summary}"
```

Run: `cd backend && python -m pytest test/unit/test_report_skeleton_fit.py --noconftest -q`
Expected: FAIL——`order 豁免 21 份 > 2`（21 份豁免还在 conditions.json，未消费）。

- [ ] **Step 3: 豁免收缩循环**

先批量摘除全部 order 豁免：

```bash
python - <<'EOF'
import json
p = "backend/test/data/corpus_census/conditions.json"
d = json.load(open(p, encoding="utf-8"))
n = 0
for v in d["universe"].values():
    ex = v.get("exemptions")
    if ex and ex.pop("order", None) is not None:
        n += 1
        if not ex:
            v.pop("exemptions")
open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
print(f"removed {n} order exemptions")
EOF
```

跑 fit，对每份 order fail：
1. 复跑普查定位形态：`python .wolf/corpus-census/classify_order_divergence.py && cat .wolf/corpus-census/order_divergence_report.txt`
2. 三选一：(a) 该章缺词条/词条缺前置 → 补 `order_whitelist.json` 条目（evidence 引用普查输出具体份数+邻居）；(b) 词条已覆盖但 DFS 未达 → 核对 expected 序是否被 Task 1 锚点改变（revised2019/openpit 份），必要时按新 expected 复核词条；(c) 真异常（非系统性）→ 该文件登记 `{"order": true}` 豁免 + 差异单留痕
3. 重复至 `exempt <= 2` 且 `order_ok >= 33`（预期 whitelist 吸收 16+ 份；余量进豁免）
4. **禁止**为凑数放宽词条语义（如给某章登记全部前置章=变相关闭判定）

- [ ] **Step 4: 全绿确认（宿主 + 容器双道）**

```bash
cd backend && python -m pytest test/unit/test_report_skeleton_fit.py test/unit/test_w2v2_render_window.py --noconftest -q
MSYS_NO_PATHCONV=1 docker run --rm -v "C:\workspace\pisuan\backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_report_skeleton_fit.py /app/test/unit/test_w2v2_render_window.py --noconftest -q
```
Expected: 两道均 `45 passed`（37 fit + 8 w2v2），summary 行 natural+whitelist ≥33。

- [ ] **Step 5: 提交**

```bash
git add backend/test/data/corpus_census/order_whitelist.json backend/test/data/corpus_census/conditions.json backend/test/unit/test_report_skeleton_fit.py
git commit -m "feat(w2v2): fit order 位移白名单——DFS 精确重插判定 + 豁免 21→≤N 收敛（natural+whitelist ≥33/35）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: changelog + 勾账 + 终审

**Files:**
- Modify: `docs/develop-guides/changelog.md`
- Modify: `docs/superpowers/specs/2026-10-06-w2-v2-three-input-window-design.md`（§1 checklist 勾账）
- Modify: 本计划文件（执行记录追加）

- [ ] **Step 1: changelog 追加**（docs/develop-guides/changelog.md，W2 条目之后）

内容要点：渲染器锚点机制（insert_after 词汇属性 + 后置重排）；顶层 stage/std_ref 真源化（stage_id 条件推导）；fit 位移白名单（DFS 判定，豁免 21→≤2，natural+whitelist ≥33/35）；6 存档重渲 + seed_gen 默认 depth 推断自洽。

- [ ] **Step 2: spec §1 checklist 勾账 + 实测数字回填**（豁免终值、modes 终值）

- [ ] **Step 3: 终审**——fresh-eyes 只读独立复验 subagent：DoD 六项逐条对账（spec §6）；`git log --oneline` 提交卫生（禁碰 7 文件零卷入、backend/package|server 零 diff：`git diff e160ea5e..HEAD --stat -- backend/package backend/server` 为空）；双渲 byte-identical 抽验 1 份。

- [ ] **Step 4: 提交勾账**

```bash
git add docs/develop-guides/changelog.md docs/superpowers/specs/2026-10-06-w2-v2-three-input-window-design.md docs/superpowers/plans/2026-10-06-w2-v2-three-input-window.md
git commit -m "docs(w2v2): 终审落账——changelog + spec checklist + DoD 对账

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 5（可选，用户拍板）: sync-dev 同步运行栈**——先核 `git status` 禁碰文件仍在（预期在，零增量），跑 `.\scripts\sync-dev.ps1`，验证 localized 树含 `insert_after` 与 `_stage_meta`。

---

## Self-Review 记录

- **Spec 覆盖**：§4.1→T1、§4.2→T2、§4.4→T3、§4.3→T4、§1 checklist/§6 DoD→T5；无缺口。
- **占位符**：无 TBD；T4 豁免终值/词条增量由普查循环实测填（机制明确，非占位）。
- **类型一致**：`_apply_anchors(chapters: dict, l1: dict) -> None`、`_stage_meta(conds, family) -> dict{stage,stage_id,std_ref}`、`_order_pass(expected, hit_seq, moves_by_chapter) -> bool` 各任务引用与定义一致；白名单 fixture 键 `{chapter,family,after,evidence}` 与 `_order_pass` 消费一致。

---

## 执行记录（2026-10-06）

**提交序列**（T1–T5 实现提交 8 笔）：

- **T1 渲染器锚点机制**：eeabdd65（insert_after 后置重排 + 爆破/R3 三锚点词条）→ f7837d32（同锚多章稳定落位，锚块语义替换互挤重插，bug-372）→ 66aa040f（同锚稳定序与 rules add 序解耦属性固化）
- **T2 渲染顶层 stage/std_ref 真源化**：98fdfc5d（stage_id 条件推导 + 字段逐字拷贝）→ 3de04075（缺真源用例补 match 断言，防异源 FileNotFoundError 冒充）
- **T3 6 存档重渲 + seed_gen 冒烟**：cff2c279（爆破/R3 落锚位 + 顶层元数据；冒烟 4 完整 454/589/469/294 断言 + 2 结构断言，双渲 byte-identical）
- **T4 fit order 位移白名单 + 豁免收敛**：0d3600e8（白名单 17 词条 + 三档判定，豁免 21→0，natural+whitelist 35/35）→ 143a7035（docstring 阈值与三档判定口径同步，质量评审 Important 项）
- **T5 勾账**：本笔（changelog + spec checklist 勾账 + 执行记录）

**收敛循环三选一决策**：21 份 order 差异全部走「补白名单词条」（词条全部带普查出处），不走豁免登记、不改规则——豁免终值 0，优于设计 ≤2；终态 modes natural=14 / whitelist=21 / exempt=0（35/35）。

**必要偏差（2 项，均为执行期必要修正）**：

1. **DFS → best-first（bug-374）**：任务书提供的递归 DFS 重插可达判定在多 mover 文件触发 RecursionError（移动序列长度无界、超递归上限）；改显式 best-first（heapq 逐位差异启发式 + visited 去重），可达性语义等价、判定结果不变，模块耗时 41s→0.16s。文档统一 best-first 表述（早期提交信息「DFS」系措辞沿革）。
2. **渲染驱动 shell → 单 Python 进程（bug-373）**：T3 原 shell 管道（python 选键 → bash `$()` 捕获 → 第二个 python `--only`）在 Windows 下 GBK/UTF-8 双重损坏致 6 份渲染全失败；合并为单个 Python 驱动进程（subprocess 列表参数，CreateProcessW 全程 Unicode），渲染器本体零改动。

**评审记录**：

- T1 质量评审捕获同锚振荡（同锚两章互挤震荡不收敛，bug-372），f7837d32 锚块语义修复 + 66aa040f 属性测试固化。
- T4 评审 spec/质量双 ✅；Important 项 docstring 口径（阈值 28→33、三档判定）以 143a7035 修正收口。
