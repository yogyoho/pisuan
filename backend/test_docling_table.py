"""测试 Docling 表格导出为 HTML"""
import sys
import os

# 添加路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.path.join(backend_dir, 'package'))

# 创建一个测试 PDF 文件的表格导出
print("=" * 60)
print("测试 Docling 表格导出")
print("=" * 60)

# 尝试使用 Docling 的 API
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat

# 查看 DocumentConverter 的方法
print("\nDocumentConverter 方法:")
for attr in dir(DocumentConverter):
    if not attr.startswith('_'):
        print(f"  {attr}")

# 查看导出方法
print("\n尝试导出方法...")

# 创建文档转换器
converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            backend=PyPdfiumDocumentBackend,
        )
    }
)

# 查看 doc 的 tables 属性
print("\ndoc.tables 属性说明:")
print("  - doc.tables: 返回 TableContext 对象列表")
print("  - 每个 TableContext 包含表格数据")
print("  - 可以导出为 HTML 格式")

# 查看是否有 export_to_html 方法
from docling.document_converter import DocumentConverter
doc_converter = DocumentConverter()

# 查看 doc.document 的类型
print("\n需要实际文档才能测试...")
print("建议使用实际的 PDF 文件进行测试")
