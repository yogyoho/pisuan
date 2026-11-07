"""eia_limit_llm_classifier 单测（Task 13 B 通道）：判别通道/探测缓存/fail-closed + 服务层接线。

LLM 调用全部 mock：结构化通道桩 with_structured_output().ainvoke，prompt 通道桩 adapter.call；
不触真实模型端点与 DB。宿主运行：cd backend && uv run --frozen --with pytest --with pytest-asyncio
python -m pytest test/unit/services/test_eia_limit_llm_classifier.py -q --noconftest
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

import pisuan.services.eia_limit_llm_classifier as cls_mod
from pisuan.services.eia_limit_extract_service import EiaLimitExtractService
from pisuan.services.eia_limit_llm_classifier import (
    EiaLimitLLMClassifier,
    GateStats,
    JudgeResult,
    LimitBlockVerdict,
)


# --------------------------------------------------------------- 桩
class FakeStructured:
    """with_structured_output() 返回对象的桩：ainvoke 出 verdict 或抛 exc。"""

    def __init__(self, verdict=None, exc=None, delay=0.0):
        self.verdict, self.exc, self.delay = verdict, exc, delay
        self.calls = 0
        self.prompt = None

    def with_structured_output(self, schema):
        self.calls += 1
        return self

    async def ainvoke(self, prompt):
        self.prompt = prompt
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.verdict


class FakeAdapter:
    """LangChainChatAdapter 表面桩：model_name / model.with_structured_output / call。"""

    def __init__(
        self,
        model_name="fake:flash",
        structured=None,
        prompt_content="",
        prompt_exc=None,
        prompt_delay=0.0,
    ):
        self.model_name = model_name
        self.model = structured
        self.prompt_content = prompt_content
        self.prompt_exc = prompt_exc
        self.prompt_delay = prompt_delay
        self.calls = 0
        self.last_prompt = None

    async def call(self, prompt):
        self.calls += 1
        self.last_prompt = prompt
        if self.prompt_delay:
            await asyncio.sleep(self.prompt_delay)
        if self.prompt_exc:
            raise self.prompt_exc
        return SimpleNamespace(content=self.prompt_content)


@pytest.fixture(autouse=True)
def _reset_probe_cache():
    """探测缓存是 ClassVar，测试间必须清场防串扰。"""
    EiaLimitLLMClassifier._structured_support.clear()
    yield
    EiaLimitLLMClassifier._structured_support.clear()


# --------------------------------------------------------------- 判别器
@pytest.mark.asyncio
async def test_structured_channel_passes_limit_statement():
    verdict = LimitBlockVerdict(
        is_limit_statement=True, pollutant="SO₂", grade="二级标准", limit_value=0.15, unit="mg/m³"
    )
    adapter = FakeAdapter(structured=FakeStructured(verdict=verdict))
    c = EiaLimitLLMClassifier(model=adapter)
    r = await c.judge("GB 3095-2012", "SO₂ 24小时平均 0.15 mg/m³", "gb3095_concentration_limits")
    assert r.passed and r.status == "passed" and r.error is None
    assert r.verdict["pollutant"] == "SO₂" and r.verdict["limit_value"] == 0.15
    assert (c.stats.blocks, c.stats.passed, c.stats.rejected, c.stats.failed) == (1, 1, 0, 0)


@pytest.mark.asyncio
async def test_structured_channel_rejects_monitoring_statement():
    verdict = LimitBlockVerdict(
        is_limit_statement=False, reason="实测噪声值，非标准限值", evidence_span="昼间实测 45 dB(A)"
    )
    adapter = FakeAdapter(structured=FakeStructured(verdict=verdict))
    c = EiaLimitLLMClassifier(model=adapter)
    r = await c.judge("GB 12348-2008", "厂界东侧昼间实测 45 dB(A)")
    assert not r.passed and r.status == "rejected" and c.stats.rejected == 1 and c.stats.failed == 0


@pytest.mark.asyncio
async def test_structured_channel_malformed_dict_fail_closed_without_blacklist():
    """provider 返回缺裁决位裸 dict：本块 fail-closed，但不拉黑探测缓存——下次仍尝试结构化通道。"""
    adapter = FakeAdapter(structured=FakeStructured(verdict={"pollutant": "SO₂"}))
    c = EiaLimitLLMClassifier(model=adapter)
    r1 = await c.judge("GB 3095-2012", "SO₂ 24小时平均 0.15 mg/m³")
    assert r1.status == "failed" and not r1.passed and c.stats.failed == 1
    assert EiaLimitLLMClassifier._structured_support == {}  # 输出校验失败不写探测缓存
    assert adapter.calls == 0  # 本块无效直接 fail-closed，不降级 prompt 通道
    r2 = await c.judge("GB 3095-2012", "SO₂ 24小时平均 0.15 mg/m³")
    assert adapter.model.calls == 2  # 探测缓存未拉黑，第二次仍尝试结构化通道
    assert r2.status == "failed"


@pytest.mark.asyncio
async def test_structured_failure_degrades_to_prompt_channel():
    payload = {
        "is_limit_statement": True,
        "pollutant": "氨氮",
        "grade": "III类",
        "limit_value": 1.0,
        "unit": "mg/L",
        "evidence_span": "氨氮 1.0 mg/L",
        "reason": "地表水 III 类标准限值陈述",
    }
    adapter = FakeAdapter(
        structured=FakeStructured(exc=RuntimeError("provider 不支持结构化输出")),
        prompt_content=json.dumps(payload, ensure_ascii=False),
    )
    c = EiaLimitLLMClassifier(model=adapter)
    r = await c.judge("GB3838-2002", "氨氮 1.0 mg/L", "gb3838_category_limits")
    assert r.passed and r.verdict["pollutant"] == "氨氮" and adapter.calls == 1
    assert EiaLimitLLMClassifier._structured_support == {"fake:flash": False}  # 探测缓存落定


@pytest.mark.asyncio
async def test_probe_cache_skips_structured_channel_on_next_judge():
    payload = json.dumps({"is_limit_statement": False, "reason": "监测陈述"})
    adapter = FakeAdapter(structured=FakeStructured(exc=RuntimeError("no support")), prompt_content=payload)
    c = EiaLimitLLMClassifier(model=adapter)
    await c.judge("GB3838-2002", "断面监测")
    await c.judge("GB3838-2002", "断面监测")
    assert adapter.model.calls == 1  # 第二次不再探测结构化通道
    assert adapter.calls == 2 and c.stats.rejected == 2


@pytest.mark.asyncio
async def test_prompt_channel_missing_verdict_field_fail_closed():
    """JSON 能解析但缺 is_limit_statement 布尔裁决位 = 无效判定，fail-closed 而非默认拒绝。"""
    adapter = FakeAdapter(
        structured=FakeStructured(exc=RuntimeError("x")),
        prompt_content=json.dumps({"reason": "看不出是不是限值"}, ensure_ascii=False),
    )
    c = EiaLimitLLMClassifier(model=adapter)
    r = await c.judge("GB3838-2002", "断面水质")
    assert r.status == "failed" and not r.passed and c.stats.failed == 1 and c.stats.rejected == 0


@pytest.mark.asyncio
async def test_prompt_channel_non_json_fail_closed():
    adapter = FakeAdapter(
        structured=FakeStructured(exc=RuntimeError("x")),
        prompt_content="这不是限值，因为它是监测数据。",
    )
    c = EiaLimitLLMClassifier(model=adapter)
    r = await c.judge("GB3096-2008", "噪声监测结果 45 dB(A)")
    assert r.status == "failed" and c.stats.failed == 1


@pytest.mark.asyncio
async def test_limit_value_string_forms_pass_prompt_channel():
    """limit_value 为辅助字段（正式值由 parse_block 重解析）：区间/符号/全角串原样保留，不因类型严格丢块。"""
    for raw in ("≤60", "60~80", "６０", "0.07"):
        payload = {"is_limit_statement": True, "pollutant": "昼间等效声级", "limit_value": raw}
        adapter = FakeAdapter(
            structured=FakeStructured(exc=RuntimeError("x")),
            prompt_content=json.dumps(payload, ensure_ascii=False),
        )
        c = EiaLimitLLMClassifier(model=adapter)
        r = await c.judge("GB12348-2008", "厂界昼间 60 dB(A)")
        assert r.passed and r.verdict["limit_value"] == raw, raw


@pytest.mark.asyncio
async def test_limit_value_string_form_passes_structured_channel():
    adapter = FakeAdapter(structured=FakeStructured(verdict={"is_limit_statement": True, "limit_value": "≤60"}))
    c = EiaLimitLLMClassifier(model=adapter)
    r = await c.judge("GB12348-2008", "厂界昼间 60 dB(A)")
    assert r.passed and r.verdict["limit_value"] == "≤60"


@pytest.mark.asyncio
async def test_judge_fail_closed_on_timeout():
    adapter = FakeAdapter(
        structured=FakeStructured(delay=5.0, verdict=LimitBlockVerdict(is_limit_statement=True)),
        prompt_content=json.dumps({"is_limit_statement": True}),
        prompt_delay=5.0,
    )
    c = EiaLimitLLMClassifier(model=adapter, timeout=0.05)
    r = await c.judge("GB3096-2008", "昼间 60 dB(A)")
    assert r.status == "failed" and not r.passed and c.stats.failed == 1


@pytest.mark.asyncio
async def test_judge_fail_closed_on_model_init_failure(monkeypatch):
    def broken_select(spec, **kwargs):
        raise RuntimeError("供应商不可达")

    monkeypatch.setattr(cls_mod, "select_model", broken_select)
    c = EiaLimitLLMClassifier(model_spec="deepseek:deepseek-flash")
    r = await c.judge("GB3095-2012", "SO₂ 0.15 mg/m³")
    assert r.status == "failed" and not r.passed and c.stats.failed == 1


@pytest.mark.asyncio
async def test_default_model_resolves_fast_model(monkeypatch):
    captured = {}

    def fake_select(spec, **kwargs):
        captured["spec"] = spec
        return FakeAdapter(structured=FakeStructured(verdict=LimitBlockVerdict(is_limit_statement=True)))

    async def fake_get():
        return {"fast_model": "prov:fast-m", "default_model": "prov:default-m"}

    monkeypatch.setattr(cls_mod, "select_model", fake_select)
    monkeypatch.setattr(cls_mod, "system_options", SimpleNamespace(get=fake_get))
    c = EiaLimitLLMClassifier()  # 未注入 model/model_spec：默认走系统配置「快速响应模型」
    r = await c.judge("GB3095-2012", "SO₂ 0.15 mg/m³")
    assert captured["spec"] == "prov:fast-m" and r.passed


@pytest.mark.asyncio
async def test_default_model_missing_config_fail_closed(monkeypatch):
    async def fake_get():
        return {"fast_model": "", "default_model": ""}

    monkeypatch.setattr(cls_mod, "system_options", SimpleNamespace(get=fake_get))
    c = EiaLimitLLMClassifier()
    r = await c.judge("GB3095-2012", "SO₂ 0.15 mg/m³")
    assert r.status == "failed" and c.stats.failed == 1


@pytest.mark.asyncio
async def test_prompt_carries_code_text_and_table_context():
    adapter = FakeAdapter(structured=FakeStructured(verdict=LimitBlockVerdict(is_limit_statement=False)))
    c = EiaLimitLLMClassifier(model=adapter)
    await c.judge("GB 12348-2008", "厂界东侧昼间 60 dB(A)", "gb12348_boundary_limits")
    prompt = adapter.model.prompt
    assert "GB 12348-2008" in prompt and "昼间 60 dB(A)" in prompt and "gb12348_boundary_limits" in prompt


# --------------------------------------------------------------- 服务层接线
class StubExtractRepo:
    """内存桩：与 test_eia_limit_extract_service.py 同形（测试桩不跨文件 import）。"""

    def __init__(self):
        self.rows, self.registry = [], []

    async def list_rows(self, table_key=None, status=None, confidence=None):
        out = self.rows
        for f, v in (("table_key", table_key), ("status", status), ("confidence", confidence)):
            if v:
                out = [r for r in out if getattr(r, f) == v]
        return out

    async def add_rows(self, rows):
        self.rows.extend(rows)
        return len(rows)

    async def get_row(self, row_id):
        return next((r for r in self.rows if r.id == row_id), None)

    async def save_row(self, row):
        return row

    async def list_registry(self):
        return self.registry

    async def get_registry(self, table_key):
        return next((r for r in self.registry if r.table_key == table_key), None)

    async def save_registry(self, row):
        self.registry.append(row)
        return row


class FakeGate:
    """服务接线用判别桩：按 status 放行/拒绝/失败，记录判别入参。"""

    def __init__(self, status="passed"):
        self.status = status
        self.stats = GateStats()
        self.judged = []

    async def judge(self, code, text, table_key=None):
        self.stats.blocks += 1
        self.judged.append((code, text, table_key))
        if self.status == "passed":
            self.stats.passed += 1
            return JudgeResult(True, "passed", {"is_limit_statement": True})
        if self.status == "rejected":
            self.stats.rejected += 1
            return JudgeResult(False, "rejected", {"is_limit_statement": False, "reason": "监测陈述"})
        self.stats.failed += 1
        return JudgeResult(False, "failed", {}, "通道全败")


_SLICE_MD = (
    "执行《环境空气质量标准》(GB3095-2012)二级标准：\n"
    "| 污染物 | 取值时间 | 浓度限值 | 单位 |\n| --- | --- | --- | --- |\n"
    "| SO2 | 24小时 | 0.15 | mg/m3 |\n"
)


@pytest.fixture
def svc_env(tmp_path):
    d = tmp_path / "planning_eia" / "slices" / "ch1"
    d.mkdir(parents=True)
    (d / "038-2024-7-9__1.md").write_text(_SLICE_MD, encoding="utf-8")
    return tmp_path, StubExtractRepo()


def _make_service(tmp_path, repo, gate, monkeypatch):
    s = EiaLimitExtractService(repo=repo, classifier=gate)
    monkeypatch.setattr(s, "_bank_dirs", lambda: [tmp_path])
    return s


@pytest.mark.asyncio
async def test_run_extraction_annotates_extractor_and_gate_report(svc_env, monkeypatch):
    tmp_path, repo = svc_env
    gate = FakeGate("passed")
    s = _make_service(tmp_path, repo, gate, monkeypatch)
    report = await s.run_extraction("admin")
    assert report["gate"] == {"blocks": 1, "passed": 1, "rejected": 0, "failed": 0}
    rows = await repo.list_rows()
    assert rows and all(r.row_json.get("extractor") == "llm" for r in rows)  # 行来源标注可读
    assert rows[0].row_json["limit_value"] == 0.15 and rows[0].confidence == "single"


@pytest.mark.asyncio
async def test_run_extraction_rejected_blocks_produce_no_rows(svc_env, monkeypatch):
    tmp_path, repo = svc_env
    gate = FakeGate("rejected")
    s = _make_service(tmp_path, repo, gate, monkeypatch)
    report = await s.run_extraction("admin")
    assert report["aggregated"] == 0 and report["inserted"] == 0
    assert report["gate"]["rejected"] == 1 and await repo.list_rows() == []


@pytest.mark.asyncio
async def test_run_extraction_classifier_failure_is_fail_closed(svc_env, monkeypatch):
    tmp_path, repo = svc_env
    gate = FakeGate("failed")
    s = _make_service(tmp_path, repo, gate, monkeypatch)
    report = await s.run_extraction("admin")
    assert report["inserted"] == 0 and report["gate"]["failed"] == 1
    assert await repo.list_rows() == []  # 不静默放行


@pytest.mark.asyncio
async def test_run_extraction_passes_code_and_table_context_to_gate(svc_env, monkeypatch):
    tmp_path, repo = svc_env
    gate = FakeGate("passed")
    s = _make_service(tmp_path, repo, gate, monkeypatch)
    await s.run_extraction("admin")
    code, text, table_key = gate.judged[0]
    assert code.startswith("GB") and table_key == "gb3095_concentration_limits"
    assert "SO2" in text and "GB3095-2012" in text  # 区块原文随判别入参下传


@pytest.mark.asyncio
async def test_gate_stats_reset_per_run(svc_env, monkeypatch):
    tmp_path, repo = svc_env
    gate = FakeGate("passed")
    s = _make_service(tmp_path, repo, gate, monkeypatch)
    await s.run_extraction("admin")
    report2 = await s.run_extraction("admin")
    assert report2["gate"]["blocks"] == 1  # 报告口径按单次试跑计，不跨次累计


@pytest.mark.asyncio
async def test_default_classifier_is_llm_gate():
    s = EiaLimitExtractService()
    assert isinstance(s._classifier, EiaLimitLLMClassifier)  # 默认必须走判别门，无旁路


# --------------------------------------------------------------- I3 试跑互斥 / I4 有界并发
class ControlledGate:
    """可控制时机的判别桩：judge 挂在 release 事件上，供重叠试跑串行化断言。"""

    def __init__(self):
        self.stats = GateStats()
        self.active = 0
        self.max_active = 0
        self._release = asyncio.Event()

    def release(self):
        self._release.set()

    async def judge(self, code, text, table_key=None):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await self._release.wait()
        finally:
            self.active -= 1
        self.stats.blocks += 1
        self.stats.passed += 1
        return JudgeResult(True, "passed", {"is_limit_statement": True})


class PeakGate:
    """并发峰值记录桩：judge 内挂一拍放大并发窗口，记录峰值与判别码集合。"""

    def __init__(self):
        self.stats = GateStats()
        self.active = 0
        self.max_active = 0
        self.judged = []

    async def judge(self, code, text, table_key=None):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.05)
        finally:
            self.active -= 1
        self.stats.blocks += 1
        self.stats.passed += 1
        self.judged.append(code)
        return JudgeResult(True, "passed", {"is_limit_statement": True})


_EIGHT_CODES = (
    "GB3095-2012",
    "GB3096-2008",
    "GB12348-2008",
    "GB3838-2002",
    "GB/T14848-2017",
    "GB20426-2006",
    "GB8978-1996",
    "GB13201-2011",
)


@pytest.fixture
def multi_env(tmp_path):
    """8 个标准号区块的切片（每行一号，locate 产出 8 块）。"""
    d = tmp_path / "planning_eia" / "slices" / "ch1"
    d.mkdir(parents=True)
    md = "\n".join(f"引用标准{i}：({code}) 污染物限值 PM10 0.07 mg/m³。" for i, code in enumerate(_EIGHT_CODES))
    (d / "038-2024-7-9__1.md").write_text(md + "\n", encoding="utf-8")
    return tmp_path, StubExtractRepo()


@pytest.mark.asyncio
async def test_overlapping_runs_serialized_and_counts_intact(svc_env, monkeypatch):
    """I3：重叠试跑以锁串行化——第二跑等第一跑完成，双方 gate 计数互不污染。"""
    tmp_path, repo = svc_env
    gate = ControlledGate()
    s = _make_service(tmp_path, repo, gate, monkeypatch)
    t1 = asyncio.create_task(s.run_extraction("admin"))
    await asyncio.sleep(0.05)  # t1 进入判别等待
    t2 = asyncio.create_task(s.run_extraction("admin"))
    await asyncio.sleep(0.05)
    assert gate.active == 1 and gate.max_active == 1  # t2 仍在锁外等待，未进入判别
    gate.release()
    report1, report2 = await asyncio.gather(t1, t2)
    assert gate.max_active == 1  # 全程判别无重叠
    assert report1["gate"]["blocks"] == 1 and report2["gate"]["blocks"] == 1  # 双方计数完整


@pytest.mark.asyncio
async def test_judge_bounded_concurrency(multi_env, monkeypatch):
    """I4：判别真并发且峰值 ≤6（保守防供应商限流）。"""
    tmp_path, repo = multi_env
    gate = PeakGate()
    s = _make_service(tmp_path, repo, gate, monkeypatch)
    report = await s.run_extraction("admin")
    assert 1 < gate.max_active <= 6
    assert report["gate"] == {"blocks": 8, "passed": 8, "rejected": 0, "failed": 0}  # 计数语义与串行版一致
    assert set(gate.judged) == set(_EIGHT_CODES)  # 判别集完整（无块丢失）


@pytest.mark.asyncio
async def test_concurrent_verdicts_produce_serial_identical_rows(multi_env, monkeypatch):
    """I4：全部放行桩下，并发判别的行产物与 gate 口径符合串行确定性不变量。"""
    tmp_path, repo = multi_env
    s = _make_service(tmp_path, repo, PeakGate(), monkeypatch)
    report = await s.run_extraction("admin")
    rows = await repo.list_rows()
    assert report["gate"]["blocks"] == 8 and report["inserted"] >= 1
    assert rows and all(r.row_json.get("extractor") == "llm" for r in rows)
    assert {r.code for r in rows} <= set(_EIGHT_CODES)


@pytest.mark.asyncio
async def test_single_block_exception_does_not_abort_batch(multi_env, monkeypatch):
    """I4 约束②：单块判别异常只影响该块（按 failed fail-closed），不炸整批。"""

    class HalfBrokenGate(PeakGate):
        async def judge(self, code, text, table_key=None):
            self.stats.blocks += 1  # 与真判别器同口径：blocks 在入口计数，失败路径计入 failed
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await asyncio.sleep(0.01)
                if code == "GB3096-2008":
                    self.stats.failed += 1
                    raise RuntimeError("单块炸")
            finally:
                self.active -= 1
            self.stats.passed += 1
            self.judged.append(code)
            return JudgeResult(True, "passed", {"is_limit_statement": True})

    tmp_path, repo = multi_env
    s = _make_service(tmp_path, repo, HalfBrokenGate(), monkeypatch)
    report = await s.run_extraction("admin")
    assert report["gate"] == {"blocks": 8, "passed": 7, "rejected": 0, "failed": 1}
    assert {r.code for r in await repo.list_rows()} != set()  # 其余 7 块照常产出
