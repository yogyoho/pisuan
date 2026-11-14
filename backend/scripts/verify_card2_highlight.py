"""服务端驱动 template-recommender 四卡流跑到卡2，验证推荐高亮标记与说明行。

以应用服务层（submit_agent_request / create_resume_run_view）创建真实 run，
由 arq worker 真实执行，等价于一次 Web 会话但无需 HTTP 凭据。

用法（api 容器内）：
    python /app/scripts/verify_card2_highlight.py start            # 新建对话并自动推进
    python /app/scripts/verify_card2_highlight.py drive <thread_id>   # 继续自动推进
    python /app/scripts/verify_card2_highlight.py resume <thread_id> '{"q-1":"答案"}'  # 手动作答后继续

退出码：0=到达卡2并输出验证结论；4=run 非中断终止；5=中断但无提问载荷；2/3=异常。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.services.agent_request_service import (
    AgentRequestInput,
    RunOrigin,
    submit_agent_request,
)
from yuxi.services.agent_run_service import create_resume_run_view
from yuxi.services.input_message_service import build_chat_input_message
from yuxi.storage.postgres.models_business import (
    AgentRun,
    Conversation,
    Message,
    ToolCall,
    User,
)

AGENT_SLUG = "default-chatbot"
ADMIN_UID = "admin"
# agnes-2.5-flash 今晨与今晚均 500 限流失败；agnes-3.0-flash 今晨连续三轮成功，显式指定。
MODEL_SPEC = "openai2:agnes-3.0-flash"
TRIGGER_QUERY = "逐节引导写作：加载模板推荐技能，继续写大同煤矿环境影响评价报告"
POLL_INTERVAL = 5
POLL_TIMEOUT = 900  # 开局定位含章节树+知识库检索，单轮模型轮次可超 10 分钟
MAX_ROUNDS = 6
RECOMMEND_MARKS = ("（推荐）", "(推荐)", "(Recommended)")
# 卡2 常设末位「都不用，按常规写法」；含该标记的提问即视为卡2。
CARD2_MARKERS = ("都不用",)

engine = create_async_engine(os.environ["POSTGRES_URL"], pool_size=5)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def get_admin(session) -> User:
    return (await session.execute(select(User).where(User.uid == ADMIN_UID))).scalar_one()


async def latest_run(session, thread_id: str) -> AgentRun | None:
    return (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.conversation_thread_id == thread_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def poll_run(session, thread_id: str) -> AgentRun | None:
    waited = 0
    while True:
        session.expire_all()
        run = await latest_run(session, thread_id)
        if run is None or run.status in {"interrupted", "completed", "failed", "cancelled"}:
            return run
        if waited >= POLL_TIMEOUT:
            return run
        await asyncio.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL


async def latest_question_payload(session, thread_id: str) -> dict | None:
    row = (
        await session.execute(
            select(ToolCall.tool_input)
            .join(Message, ToolCall.message_id == Message.id)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.thread_id == thread_id, ToolCall.tool_name == "ask_user_question")
            .order_by(ToolCall.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        return None
    # 模型可能把 questions 数组字符串化传入（前端 normalizeQuestions 兼容此形态），驱动同样兜底。
    if isinstance(row.get("questions"), str):
        try:
            row["questions"] = json.loads(row["questions"])
        except json.JSONDecodeError:
            return None
    return row


def is_card2(questions: list[dict]) -> bool:
    for q in questions:
        for opt in q.get("options", []):
            if any(marker in str(opt.get("label", "")) for marker in CARD2_MARKERS):
                return True
    return False


def pick_label(questions: list[dict]) -> str:
    labels = [str(o.get("label", "")) for o in questions[0].get("options", [])]
    for label in labels:  # 开局恢复卡：继续下一节
        if "继续" in label:
            return label
    for key in ("3.1.2", "气候", "气象"):  # 卡1：推荐节
        for label in labels:
            if key in label:
                return label
    for label in labels:  # 兜底：第一个非停车选项
        if "停" not in label:
            return label
    return labels[0]


def dump_question(questions: list[dict]) -> list[dict]:
    out = []
    for q in questions:
        options = []
        for i, o in enumerate(q.get("options", [])):
            label = str(o.get("label", ""))
            options.append(
                {
                    "index": i,
                    "label": label,
                    "description": o.get("description"),
                    "recommended_marked": any(m in label for m in RECOMMEND_MARKS),
                }
            )
        out.append(
            {
                "question_id": q.get("question_id"),
                "question": q.get("question"),
                "allow_other": q.get("allow_other"),
                "options": options,
                "recommendation_first": bool(options) and options[0]["recommended_marked"],
                # 常设末位（「都不用…」）按设计无说明行，只考察候选选项。
                "candidates_have_description": all(
                    o["description"] for o in options if not any(m in o["label"] for m in CARD2_MARKERS)
                ),
            }
        )
    return out


def print_card(tag: str, questions: list[dict]) -> None:
    print(f"{tag}:", json.dumps(dump_question(questions), ensure_ascii=False, indent=1), flush=True)


async def resume_run(session, thread_id: str, payload: dict, created_by_run_id: str) -> None:
    await create_resume_run_view(
        agent_slug=AGENT_SLUG,
        thread_id=thread_id,
        meta={},
        current_uid=ADMIN_UID,
        db=session,
        resume=payload,
        created_by_run_id=created_by_run_id,
    )
    await session.commit()


async def drive(thread_id: str) -> int:
    async with Session() as session:
        for round_no in range(1, MAX_ROUNDS + 1):
            run = await poll_run(session, thread_id)
            if run is None:
                print(f"[round {round_no}] no run found for thread {thread_id}", flush=True)
                return 2
            print(
                f"[round {round_no}] run={run.id} status={run.status}"
                + (f" error={run.error_message}" if run.error_message else ""),
                flush=True,
            )
            if run.status != "interrupted":
                return 0 if run.status == "completed" else 4
            payload = await latest_question_payload(session, thread_id)
            if not payload:
                print("[round %d] interrupted but no ask_user_question payload" % round_no, flush=True)
                return 5
            questions = payload.get("questions", [])
            print_card(f"[round {round_no}] CARD", questions)
            if is_card2(questions):
                verdict = dump_question(questions)
                ok = all(q["recommendation_first"] and q["candidates_have_description"] for q in verdict)
                print("VERDICT:", "PASS" if ok else "FAIL", json.dumps(verdict, ensure_ascii=False), flush=True)
                return 0
            answer = pick_label(questions)
            question_id = questions[0].get("question_id", "q-1")
            print(f"[round {round_no}] auto-answer {question_id} <- {answer}", flush=True)
            await resume_run(session, thread_id, {question_id: answer}, run.id)
    print("max rounds reached without reaching card 2", flush=True)
    return 3


async def start() -> str:
    thread_id = str(uuid.uuid4())
    async with Session() as session:
        admin = await get_admin(session)
        response = await submit_agent_request(
            request_input=AgentRequestInput(
                agent_slug=AGENT_SLUG,
                thread_id=thread_id,
                request_id=str(uuid.uuid4()),
                input_message=build_chat_input_message(TRIGGER_QUERY),
                origin=RunOrigin(source="chat", channel="web"),
                request_metadata={"tool_approval_mode": "always_trust"},
                model_spec=MODEL_SPEC,
                tool_approval_mode="always_trust",
                queue_policy="enqueue",
                create_conversation=True,
                conversation_title="卡2推荐高亮自动验证",
            ),
            current_user=admin,
            db=session,
        )
        print("thread_id:", thread_id, flush=True)
        print("run response:", json.dumps(response, ensure_ascii=False, default=str), flush=True)
    return thread_id


async def start_and_drive() -> int:
    # start 与 drive 必须共用同一事件循环：模块级 engine/pool 绑定首个 loop，
    # 跨 asyncio.run() 复用会报 "Future attached to a different loop"。
    thread_id = await start()
    return await drive(thread_id)


async def manual_resume(thread_id: str, payload: dict) -> int:
    async with Session() as session:
        run = await poll_run(session, thread_id)
        if run is None or run.status != "interrupted":
            print(f"latest run status={getattr(run, 'status', None)}, not interruptible", flush=True)
            return 4
        await resume_run(session, thread_id, payload, run.id)
        print(f"resumed run={run.id} with {payload}", flush=True)
    return await drive(thread_id)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    if cmd == "start":
        code = asyncio.run(start_and_drive())
    elif cmd == "drive":
        code = asyncio.run(drive(sys.argv[2]))
    elif cmd == "resume":
        code = asyncio.run(manual_resume(sys.argv[2], json.loads(sys.argv[3])))
    else:
        print(__doc__)
        code = 1
    sys.exit(code or 0)


if __name__ == "__main__":
    main()
