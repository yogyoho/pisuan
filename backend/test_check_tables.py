"""检查任务详情中的表格数据"""
import asyncio
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/package')

async def main():
    from yuxi.services.domain_factory_service import get_domain_factory_service
    service = get_domain_factory_service()
    task_id = '9475e881-d239-4bd6-ab1c-f5e7a553a790'
    detail = await service.get_task_detail(task_id)
    
    if detail:
        print('=' * 60)
        print('Task ID:', detail.get('id'))
        print('Status:', detail.get('status'))
        print('File name:', detail.get('file_name'))
        print('=' * 60)
        
        # 检查 structured_blocks
        blocks = detail.get('structured_blocks', [])
        print(f'\nStructured blocks count: {len(blocks)}')
        
        table_blocks = [b for b in blocks if b.get('type') == 'table']
        print(f'Table blocks count: {len(table_blocks)}')
        
        for i, block in enumerate(table_blocks):
            print(f'\n  Block {i+1}:')
            print(f'    ID: {block.get("id")}')
            print(f'    Headers: {block.get("headers", [])[:3]}')
            print(f'    Rows: {len(block.get("rows", []))}')
            print(f'    Has html_content: {"html_content" in block}')
            
            html_content = block.get('html_content')
            if html_content:
                print(f'    html_content length: {len(html_content)}')
                print(f'    html_content preview: {html_content[:150]}...')
            else:
                print(f'    html_content: None')
        
        # 检查 raw_html
        raw_html = detail.get('raw_html')
        print(f'\n{"=" * 60}')
        print(f'Has raw_html: {raw_html is not None}')
        if raw_html:
            print(f'raw_html length: {len(raw_html)}')
            table_count = raw_html.count('<table') if raw_html else 0
            print(f'Tables in raw_html: {table_count}')
        else:
            print('raw_html is None')
        
        # 检查 source_paragraphs
        paragraphs = detail.get('source_paragraphs', [])
        table_paragraphs = [p for p in paragraphs if p.get('is_table')]
        print(f'\nsource_paragraphs count: {len(paragraphs)}')
        print(f'Table paragraphs count: {len(table_paragraphs)}')
    else:
        print('Task not found')

asyncio.run(main())
