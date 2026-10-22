"""ask_user_question 卡片反模式校验（bug-4011）单元测试。

页面实测发现模型把委托单位/编制单位等填写项做成单选题（选项=字段名、
选项值=「如：XX…」示例占位），用户只能选不能填。工具层必须拒收此类卡片
并以教学式报错引导模型改写成逐项自由文本问题。
"""

from __future__ import annotations

import pytest

from pisuan.agents.toolkits.buildin import tools


def _invoke(questions):
    """绕过 langchain tool 包装直接调实现；interrupt 打桩避免真实挂起。"""
    fn = tools.ask_user_question.func
    original = tools.interrupt
    tools.interrupt = lambda payload: {}
    try:
        return fn(questions=questions)
    finally:
        tools.interrupt = original


def test_fillin_slots_with_options_rejected():
    """编号填写槽 + options = 填写项做成选择题，必须拒绝。"""
    questions = [
        {
            "question": "请提供项目基础信息：\n1. 委托单位（全称）：\n2. 编制单位（全称）：\n3. 资质等级：",
            "options": [
                {"label": "委托单位", "value": "XX矿业开发有限公司"},
                {"label": "编制单位", "value": "XX环境影响评价院"},
            ],
        }
    ]
    with pytest.raises(ValueError, match="禁做成选择题"):
        _invoke(questions)


def test_placeholder_options_rejected():
    """选项值是示例占位（如：XX…）时必须拒绝，枚举卡也逃不过。"""
    questions = [
        {
            "question": "委托单位是哪家？",
            "options": [
                {"label": "示例一", "value": "如：XX矿业有限公司"},
                {"label": "示例二", "value": "如：XX能源集团"},
            ],
        }
    ]
    with pytest.raises(ValueError, match="示例占位"):
        _invoke(questions)


def test_legit_enum_options_pass():
    """真实枚举选项（资质等级甲级/乙级）不受影响。"""
    questions = [
        {
            "question": "编制单位资质等级？",
            "options": [
                {"label": "甲级", "value": "甲级"},
                {"label": "乙级", "value": "乙级"},
            ],
        }
    ]
    result = _invoke(questions)
    assert result["answer"] == {}


def test_fillin_slots_without_options_pass():
    """逐项填写说明 + 无 options = 正确的自由文本形态，放行。"""
    questions = [
        {
            "question": "请提供项目基础信息：\n1. 委托单位（全称）：\n2. 编制单位（全称）：",
        }
    ]
    result = _invoke(questions)
    assert result["answer"] == {}
