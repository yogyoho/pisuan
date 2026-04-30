"""Test script to upload and process a domain factory task."""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/package")

from yuxi.services.domain_factory_service import DomainFactoryService
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository


async def main():
    # 测试文件路径 - 使用已有的文件
    test_file = "/app/saves/domain_factory/coal/1b014cf4-4da1-4112-8f48-24fe39566854_1新疆伊宁矿区北区总体规划_修编_环境影响报告书_-3.docx"

    if not os.path.exists(test_file):
        print(f"文件不存在: {test_file}")
        return

    print(f"文件大小: {os.path.getsize(test_file)} bytes")

    # 读取文件
    with open(test_file, "rb") as f:
        file_content = f.read()

    print("创建服务...")
    service = DomainFactoryService()

    # 保存文件并创建任务
    print("保存上传文件...")
    task_id, storage_path = await service.save_uploaded_file(
        file_content,
        os.path.basename(test_file),
        "coal"  # 领域代码
    )
    print(f"文件已保存: {storage_path}")
    print(f"任务 ID: {task_id}")

    # 创建任务
    print("创建任务...")
    task = await service.create_task(
        domain_code="coal",
        file_name=os.path.basename(test_file),
        file_path=storage_path,
        uploaded_by="test_user",
        document_type="环境影响报告",
    )
    print(f"任务已创建: {task.id}")
    print(f"任务状态: {task.status}")

    # 启动 ETL Pipeline
    print("启动 ETL Pipeline...")
    result = await service.run_etl_pipeline(task.id)
    print(f"ETL Pipeline 结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())
