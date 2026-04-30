"""Test script to verify source_paragraphs table storage."""
import sys
import re
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/package")

from yuxi.services.domain_factory_service import DomainFactoryService

async def main():
    service = DomainFactoryService()

    # 使用一个已有任务的文件路径进行测试
    test_file = "/app/saves/domain_factory/coal/1b014cf4-4da1-4112-8f48-24fe39566854_1新疆伊宁矿区北区总体规划_修编_环境影响报告书_-3.docx"

    # 直接测试段落解析
    from yuxi.plugins.parser.unified import parse_source_to_markdown
    parse_result = await parse_source_to_markdown(test_file)

    markdown = parse_result.markdown
    html = parse_result.html

    print(f"Markdown 长度: {len(markdown)}")
    print(f"HTML 长度: {len(html) if html else 0}")

    # 测试段落解析
    paragraphs = service._parse_markdown_to_paragraphs(markdown, html_content=html)

    print(f"\n段落总数: {len(paragraphs)}")

    table_count = sum(1 for p in paragraphs if p.get('is_table'))
    html_table_count = sum(1 for p in paragraphs if p.get('is_table') and p.get('table_format') == 'html')
    markdown_table_count = sum(1 for p in paragraphs if p.get('is_table') and p.get('table_format') == 'markdown')

    print(f"表格段落数: {table_count}")
    print(f"  - HTML 格式: {html_table_count}")
    print(f"  - Markdown 格式: {markdown_table_count}")

    # 检查前几个表格段落
    tables = [p for p in paragraphs if p.get('is_table')][:3]
    for i, t in enumerate(tables):
        content = t.get('content', '')[:100]
        print(f"\n表格 {i+1}:")
        print(f"  格式: {t.get('table_format')}")
        print(f"  内容预览: {content}...")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
