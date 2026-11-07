"""知识库运行时单例。"""

import os

from pisuan.config import get_runtime_dir
from pisuan.knowledge.factory import KnowledgeBaseFactory
from pisuan.knowledge.implementations.dify import DifyKB
from pisuan.knowledge.implementations.milvus import MilvusKB
from pisuan.knowledge.implementations.notion import NotionKB
from pisuan.knowledge.manager import KnowledgeBaseManager

KnowledgeBaseFactory.register(MilvusKB)
KnowledgeBaseFactory.register(DifyKB)
KnowledgeBaseFactory.register(NotionKB)

knowledge_base = KnowledgeBaseManager(os.path.join(get_runtime_dir(), "knowledge_base_data"))
