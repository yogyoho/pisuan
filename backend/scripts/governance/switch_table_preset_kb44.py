# 批量切换：kb_yn2req38m2（环评引用标准规范库）表格占比 ≥30% 的文件
# → chunk_preset_id=table + 重新入库（重分片+重嵌入写 Milvus）。
# 目标清单由扫描结果（表格占比 ≥0.30）硬编码；--pilot 只跑 21010 一个验证。
#
# 用法（api 容器内）：
#   python -m scripts.governance.switch_table_preset_kb44 --pilot
#   python -m scripts.governance.switch_table_preset_kb44
from __future__ import annotations

import asyncio
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KB_ID = "kb_yn2req38m2"
PILOT_FILE_ID = "file_3504fd"  # 《土地利用现状分类》

TARGETS = [
    "file_3504fd",  # 土地利用现状分类 GBT21010-2017（83%）
    "file_ababa8",  # 土壤环境质量 建设用地 GB36600-2018（87%）
    "file_ccdb26",  # 地下水质量标准 GBT 14848-2017（86%）
    "file_248892",  # 地表水环境质量标准 GB 3838-2002（85%）
    "file_f07c9f",  # 大气污染物综合排放标准 GB 16297-1996（81%）
    "file_a95d08",  # 建设项目环境风险评价技术导则 HJ 169-2018（77%）
    "file_7cfd0b",  # 地下水环境监测技术规范 HJ 164-2020（65%）
    "file_2583cf",  # 污水综合排放标准 GB 8978-1996（66%）
    "file_0e55a2",  # 清洁生产标准 煤炭采选业 HJ 446-2008（59%）
    "file_bafcaa",  # 环评技术导则 总纲 HJ 2.2-2018（34%）
    "file_772a20",  # 环评技术导则 土壤环境 HJ 964-2018（45%）
    "file_1f550c",  # 环评技术导则 地下水环境 HJ 610-2016（41%）
    "file_23b29e",  # 煤炭工业污染物排放标准 GB 20426-2006（46%）
    "file_04fd88",  # 环境空气质量标准 GB 3095-2026（53%）
    "file_8ab4d4",  # 生态环境状况评价技术规范 HJ 192-2015（33%）
    "file_db98d8",  # 环评技术导则 声环境 HJ 2.4-2021（37%）
    "file_2b293c",  # 环评技术导则 地表水环境 HJ 2.3-2018（17%→34% 表格行数46，仍入选）
    "file_59faf5",  # 环评技术导则 生态影响 HJ 19-2022（26%→表格块9，入选）
]


async def main(pilot: bool) -> None:
    from sqlalchemy import text

    from yuxi.knowledge.runtime import knowledge_base
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()
    targets = [PILOT_FILE_ID] if pilot else TARGETS
    # 可续跑：跳过已完成（preset 已是 table）的文件——中断重跑不重复嵌入
    async with pg_manager.get_async_session_context() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT file_id, processing_params->>'chunk_preset_id' AS preset "
                    "FROM knowledge_files WHERE kb_id = :kb"
                ),
                {"kb": KB_ID},
            )
        ).all()
    done = {rid for rid, preset in rows if preset == "table"}
    targets = [t for t in targets if t not in done]
    print(f"目标 {len(targets)} 个文件（KB {KB_ID}，engine milvus；已完成跳过 {len(done)} 个）")

    ok, fail = 0, 0
    for i, file_id in enumerate(targets, 1):
        try:
            await knowledge_base.update_file_params(KB_ID, file_id, {"chunk_preset_id": "table"})
            result = await knowledge_base.index_file(KB_ID, file_id)
            stats = result.get("stats") or {} if isinstance(result, dict) else {}
            print(f"[{i}/{len(targets)}] {file_id} OK  chunks={stats.get('total_chunks', '?')}")
            ok += 1
        except Exception as e:  # noqa: BLE001 — 单文件失败不阻断批次
            print(f"[{i}/{len(targets)}] {file_id} FAIL: {str(e)[:160]}")
            fail += 1
    print(f"\n完成：成功 {ok} / 失败 {fail}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    asyncio.run(main(parser.parse_args().pilot))
