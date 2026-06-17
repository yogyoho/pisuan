import asyncio
import os
import traceback
from functools import partial
from typing import Any

from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from neo4j import GraphDatabase
from pymilvus import connections, utility

from yuxi import config
from yuxi.knowledge.base import FileStatus, KnowledgeBase
from yuxi.knowledge.chunking.ragflow_like.dispatcher import chunk_markdown
from yuxi.knowledge.chunking.ragflow_like.presets import resolve_chunk_processing_params
from yuxi.models.embed import get_embedding_model_info_by_id
from yuxi.plugins.parser.unified import Parser
from yuxi.utils import hashstr, logger
from yuxi.utils.datetime_utils import utc_isoformat


class LightRagKB(KnowledgeBase):
    """基于 LightRAG 的知识库实现"""

    def __init__(self, work_dir: str, **kwargs):
        """
        初始化 LightRAG 知识库

        Args:
            work_dir: 工作目录
            **kwargs: 其他配置参数
        """
        super().__init__(work_dir)

        # 存储 LightRAG 实例映射 {db_id: LightRAG}
        self.instances: dict[str, LightRAG] = {}
        self._db_write_locks: dict[str, asyncio.Lock] = {}
        self._db_instance_locks: dict[str, asyncio.Lock] = {}
        self._lock_guard = asyncio.Lock()

        logger.info("LightRagKB initialized")

    @property
    def kb_type(self) -> str:
        """知识库类型标识"""
        return "lightrag"

    @staticmethod
    def _prepare_lightrag_insert_payload(chunks: list[dict]) -> tuple[str, str | None, bool]:
        if not chunks:
            return "", None, False

        if len(chunks) == 1:
            return chunks[0]["content"], None, False

        delimiter = "\n<|YUXI_CHUNK_DELIM|>\n"
        payload = delimiter.join(chunk["content"] for chunk in chunks if chunk.get("content"))
        return payload, delimiter, False  # 允许 LightRAG 基于进行二次切分，避免超限

    def delete_database(self, db_id: str) -> dict:
        """删除数据库，同时清除Milvus和Neo4j中的数据"""
        # Drop Milvus collection
        try:
            milvus_uri = os.getenv("MILVUS_URI") or "http://localhost:19530"
            milvus_token = os.getenv("MILVUS_TOKEN") or ""
            connection_alias = f"lightrag_{hashstr(db_id, 6)}"

            connections.connect(alias=connection_alias, uri=milvus_uri, token=milvus_token)

            # 删除 LightRAG 创建的三个集合
            collection_names = [f"{db_id}_chunks", f"{db_id}_relationships", f"{db_id}_entities"]
            for collection_name in collection_names:
                if utility.has_collection(collection_name, using=connection_alias):
                    utility.drop_collection(collection_name, using=connection_alias)
                    logger.info(f"Dropped Milvus collection {collection_name}")
                else:
                    logger.info(f"Milvus collection {collection_name} does not exist, skipping")

            connections.disconnect(connection_alias)
        except Exception as e:
            logger.error(f"Failed to drop Milvus collection {db_id}: {e}")

        # Delete Neo4j data
        neo4j_uri = os.getenv("NEO4J_URI") or "bolt://localhost:7687"
        neo4j_username = os.getenv("NEO4J_USERNAME") or "neo4j"
        neo4j_password = os.getenv("NEO4J_PASSWORD") or "0123456789"

        try:
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
            with driver.session() as session:
                # 删除带有特定 db_id 标签的节点和关系
                session.run(
                    """
                    MATCH (n:`"""
                    + db_id
                    + """`)
                    DETACH DELETE n
                """
                )

                logger.info(f"Deleted Neo4j nodes and relationships for workspace {db_id}")
        except Exception as e:
            logger.error(f"Failed to delete Neo4j data for {db_id}: {e}")
        finally:
            if "driver" in locals():
                driver.close()

        # Delete local files and metadata
        return super().delete_database(db_id)

    def update_database(self, db_id: str, name: str, description: str, llm_info: dict = None) -> dict:
        """
        更新数据库配置

        当 llm_info 改变时，清除缓存的 LightRAG 实例，确保下次使用时使用新模型创建实例
        """
        if db_id not in self.databases_meta:
            raise ValueError(f"数据库 {db_id} 不存在")

        # 检查 llm_info 是否发生变化
        old_llm_info = self.databases_meta[db_id].get("llm_info", {})
        llm_info_changed = llm_info is not None and llm_info != old_llm_info
        logger.warning(f"old_llm_info: {old_llm_info}, new_llm_info: {llm_info}, llm_info_changed: {llm_info_changed}")

        # 调用父类方法更新基本信息
        result = super().update_database(db_id, name, description, llm_info)

        # 如果 llm_info 发生变化，清除缓存的实例，确保下次使用新模型
        if llm_info_changed and db_id in self.instances:
            logger.info(f"LLM model changed, invalidating cached LightRAG instance for {db_id}")
            del self.instances[db_id]

        return result

    async def _create_kb_instance(self, db_id: str, kb_config: dict) -> LightRAG:
        """创建 LightRAG 实例"""
        logger.info(f"Creating LightRAG instance for {db_id}")

        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        llm_info = self.databases_meta[db_id].get("llm_info", {})
        embed_info = self.databases_meta[db_id].get("embed_info", {})
        # 读取在创建数据库时透传的附加参数（包括语言）
        metadata = self.databases_meta[db_id].get("metadata", {}) or {}
        addon_params = {}
        if isinstance(metadata.get("addon_params"), dict):
            addon_params.update(metadata.get("addon_params", {}))
        # 兼容直接放在 metadata 下的 language
        if isinstance(metadata.get("language"), str) and metadata.get("language"):
            addon_params.setdefault("language", metadata.get("language"))
        # 默认语言从环境变量读取，默认 English
        addon_params.setdefault("language", os.getenv("SUMMARY_LANGUAGE") or "English")

        # 创建工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        # 创建 LightRAG 实例
        rag = LightRAG(
            working_dir=working_dir,
            workspace=db_id,
            llm_model_func=self._get_llm_func(llm_info),
            embedding_func=self._get_embedding_func(embed_info),
            vector_storage="MilvusVectorDBStorage",
            kv_storage="JsonKVStorage",
            graph_storage="Neo4JStorage",
            doc_status_storage="JsonDocStatusStorage",
            log_file_path=os.path.join(working_dir, "lightrag.log"),
            addon_params=addon_params,
        )

        return rag

    async def _initialize_kb_instance(self, instance: LightRAG) -> None:
        """初始化 LightRAG 实例"""
        logger.info(f"Initializing LightRAG instance for {instance.working_dir}")
        await instance.initialize_storages()
        await initialize_pipeline_status()

    @staticmethod
    async def _ensure_doc_processed(rag: LightRAG, file_id: str) -> None:
        """确保 LightRAG 文档处理成功，否则抛出异常。"""
        status_doc = await rag.doc_status.get_by_id(file_id)
        if not status_doc:
            raise ValueError(f"LightRAG 文档状态缺失: {file_id}")

        status = status_doc.get("status")
        status_value = status.value if hasattr(status, "value") else status
        if status_value not in {"processed", "preprocessed"}:
            error_msg = status_doc.get("error_msg") or "unknown error"
            raise ValueError(f"LightRAG 实体关系抽取失败: file_id={file_id}, status={status_value}, error={error_msg}")

    async def _get_lightrag_instance(self, db_id: str) -> LightRAG | None:
        """获取或创建 LightRAG 实例"""
        if db_id in self.instances:
            logger.info(f"Using cached LightRAG instance for {db_id}")
            return self.instances[db_id]

        if db_id not in self.databases_meta:
            return None

        instance_lock = await self._get_db_instance_lock(db_id)
        async with instance_lock:
            if db_id in self.instances:
                logger.info(f"Using cached LightRAG instance for {db_id}")
                return self.instances[db_id]

            try:
                # 创建实例
                rag = await self._create_kb_instance(db_id, {})

                # 异步初始化存储
                await self._initialize_kb_instance(rag)

                self.instances[db_id] = rag
                return rag

            except Exception as e:
                logger.error(f"Failed to create LightRAG instance for {db_id}: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None

    async def _get_db_write_lock(self, db_id: str) -> asyncio.Lock:
        async with self._lock_guard:
            return self._db_write_locks.setdefault(db_id, asyncio.Lock())

    async def _get_db_instance_lock(self, db_id: str) -> asyncio.Lock:
        async with self._lock_guard:
            return self._db_instance_locks.setdefault(db_id, asyncio.Lock())

    def _get_llm_func(self, llm_info: dict):
        """获取 LLM 函数"""
        from yuxi.models import select_model

        # 如果用户选择了LLM，使用用户选择的；否则使用环境变量默认值
        if llm_info and llm_info.get("model_spec"):
            model_spec = llm_info["model_spec"]
            logger.info(f"Using user-selected LLM spec: {model_spec}")
        elif llm_info and llm_info.get("provider") and llm_info.get("model_name"):
            model_spec = f"{llm_info['provider']}/{llm_info['model_name']}"
            logger.info(f"Using user-selected LLM: {model_spec}")
        else:
            model_spec = config.default_model
            logger.info(f"Using default LLM from environment: {model_spec}")

        model = select_model(model_spec=model_spec)

        async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return await openai_complete_if_cache(
                model=model.model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=model.api_key,
                base_url=model.base_url,
                **kwargs,
            )

        return llm_model_func

    def _get_embedding_func(self, embed_info: dict):
        """获取 embedding 函数"""
        config_dict = get_embedding_model_info_by_id(embed_info["model_id"])
        logger.debug(f"Embedding config dict: {config_dict}")

        if config_dict.get("model_id") and config_dict["model_id"].startswith("ollama"):
            from lightrag.llm.ollama import ollama_embed

            from yuxi.utils import get_docker_safe_url

            host = get_docker_safe_url(config_dict["base_url"].replace("/api/embed", ""))
            logger.debug(f"Ollama host: {host}")
            return EmbeddingFunc(
                embedding_dim=config_dict["dimension"],
                max_token_size=8192,
                func=lambda texts: ollama_embed(
                    texts=texts,
                    embed_model=config_dict["name"],
                    api_key=config_dict["api_key"],
                    host=host,
                ),
            )

        # 尝试获取模型名称，支持多种键名以保持兼容性
        if "name" in config_dict and config_dict["name"]:
            model_name = config_dict["name"]
        elif "model" in config_dict and config_dict["model"]:
            model_name = config_dict["model"]
        else:
            raise ValueError(f"Neither 'name' nor 'model' found in config_dict or both are empty: {config_dict}")
        return EmbeddingFunc(
            embedding_dim=config_dict["dimension"],
            max_token_size=8192,
            model_name=model_name,
            func=partial(
                openai_embed.func,
                model=model_name,
                api_key=config_dict["api_key"],
                base_url=config_dict["base_url"].replace("/embeddings", ""),
            ),
        )

    async def index_file(
        self, db_id: str, file_id: str, operator_id: str | None = None, params: dict | None = None
    ) -> dict:
        """
        Index parsed file (Status: INDEXING -> INDEXED/ERROR_INDEXING)

        Args:
            db_id: Database ID
            file_id: File ID
            operator_id: ID of the user performing the operation
            params: Override processing params to apply during indexing (merged on top of stored params)

        Returns:
            Updated file metadata
        """
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        db_write_lock = await self._get_db_write_lock(db_id)
        async with db_write_lock:
            rag = await self._get_lightrag_instance(db_id)
            if not rag:
                raise ValueError(f"Failed to get LightRAG instance for {db_id}")

            # Get file meta
            if file_id not in self.files_meta:
                raise ValueError(f"File {file_id} not found")
            file_meta = self.files_meta[file_id]

            # Validate current status - only allow indexing from these states
            current_status = file_meta.get("status")
            allowed_statuses = {
                FileStatus.PARSED,
                FileStatus.ERROR_INDEXING,
                FileStatus.INDEXED,  # For re-indexing
                "done",  # Legacy status
            }

            if current_status not in allowed_statuses:
                raise ValueError(
                    f"Cannot index file with status '{current_status}'. "
                    f"File must be parsed first (status should be one of: {', '.join(allowed_statuses)})"
                )

            # Check markdown file exists
            if not file_meta.get("markdown_file"):
                await self._mark_file_unparsed(file_id, operator_id)
                raise ValueError("File has not been parsed yet (no markdown_file)")

            # Clear previous error if any
            if "error" in file_meta:
                self.files_meta[file_id].pop("error", None)

            # Update status and add to processing queue
            self.files_meta[file_id]["status"] = FileStatus.INDEXING
            self.files_meta[file_id]["updated_at"] = utc_isoformat()
            if operator_id:
                self.files_meta[file_id]["updated_by"] = operator_id
            await self._persist_file(file_id)

            # Add to processing queue
            self._add_to_processing_queue(file_id)

            try:
                # Read markdown
                markdown_content = await self._read_markdown_from_minio(file_meta["markdown_file"])
                file_path = file_meta.get("path")
                filename = file_meta.get("filename") or file_id
                params = resolve_chunk_processing_params(
                    kb_additional_params=self.databases_meta.get(db_id, {}).get("metadata"),
                    file_processing_params=file_meta.get("processing_params"),
                    request_params=params,
                )
                self.files_meta[file_id]["processing_params"] = params
                await self._save_metadata()

                chunks = chunk_markdown(markdown_content, file_id, filename, params)
                chunk_input, split_by_character, split_by_character_only = self._prepare_lightrag_insert_payload(chunks)
                if not chunk_input:
                    chunk_input = markdown_content

                # Clean up existing chunks if any (for re-indexing)
                await self.delete_file_chunks_only(db_id, file_id)

                # Insert
                await rag.ainsert(
                    input=chunk_input,
                    ids=file_id,
                    file_paths=file_path,
                    split_by_character=split_by_character,
                    split_by_character_only=split_by_character_only,
                )
                await self._ensure_doc_processed(rag, file_id)

                logger.info(
                    f"Indexed file {file_id} into LightRAG with {len(chunks)} chunks, "
                    f"chunk_preset_id={params.get('chunk_preset_id')}"
                )

                # Update status
                self.files_meta[file_id]["status"] = FileStatus.INDEXED
                self.files_meta[file_id]["updated_at"] = utc_isoformat()
                if operator_id:
                    self.files_meta[file_id]["updated_by"] = operator_id
                await self._persist_file(file_id)

                return self.files_meta[file_id]

            except Exception as e:
                logger.error(f"Indexing failed for {file_id}: {e}")
                self.files_meta[file_id]["status"] = FileStatus.ERROR_INDEXING
                self.files_meta[file_id]["error"] = str(e)
                self.files_meta[file_id]["updated_at"] = utc_isoformat()
                if operator_id:
                    self.files_meta[file_id]["updated_by"] = operator_id
                await self._persist_file(file_id)
                raise

            finally:
                # Remove from processing queue
                self._remove_from_processing_queue(file_id)

    async def _ingest_structured_document(
        self,
        rag: LightRAG,
        db_id: str,
        file_id: str,
        file_path: str,
        structured_doc,
    ) -> None:
        """将结构化文档写入 LightRAG，三重存储：正文 + 模板 + 插槽

        1. 正文 Chunk：去噪+上下文重组后的段落原文
        2. Template_Collection：泛化模板的自然语言描述（可按模板语义检索）
        3. Slot_Collection：每个插槽的独立描述（可按插槽属性检索）
        """
        from yuxi.services.domain_factory_service import build_embedding_text

        # 确保 storage 已初始化
        try:
            await rag.initialize_storages()
        except Exception as e:
            logger.warning(f"initialize_storages 失败（可能已存在）: {e}")

        industry = structured_doc.industry
        report_type = structured_doc.report_type

        # 清理已有的 chunks（支持重新入库）
        await self.delete_file_chunks_only(db_id, file_id)

        # 构建 section_id -> section 映射
        section_map: dict[str, dict[str, Any]] = {}
        for section in structured_doc.sections:
            sid = section.get("section_id", "")
            if sid:
                section_map[sid] = section

        # 收集模板和插槽（去重）
        templates_to_store: dict[str, dict[str, Any]] = {}
        slots_to_store: dict[str, dict[str, Any]] = {}

        chunk_count = 0

        # ========== 第一步：逐 chunk 写入正文 ==========
        for chunk in structured_doc.chunks:
            content = chunk.get("content", "")
            if not content:
                continue

            section_id = chunk.get("section_id", "")
            section_info = section_map.get(section_id, {})
            section_title = section_info.get("title", "") or chunk.get("section_title", "")
            parent_title = chunk.get("parent_section_title", "")

            embedding_text = build_embedding_text(
                industry=industry,
                report_type=report_type,
                parent_section_title=parent_title,
                current_section_title=section_title,
                content=content,
            )

            chunk_id = chunk.get("id", f"{file_id}_chunk_{chunk_count}")
            chunk_id_short = f"c_{hashstr(chunk_id, 8)}"

            try:
                await rag.ainsert(
                    input=embedding_text,
                    ids=chunk_id_short,
                    file_paths=file_path,
                )
                chunk_count += 1
            except Exception as e:
                logger.warning(f"正文 chunk 写入失败: {chunk_id_short}, {e}")

            # 收集模板和插槽
            template_data = chunk.get("template")
            if template_data and isinstance(template_data, dict):
                template_id = template_data.get("template_id") or template_data.get("generalized", "")[:30]
                if template_id and template_id not in templates_to_store:
                    templates_to_store[template_id] = template_data

                for slot in template_data.get("slots", []):
                    slot_name = slot.get("name", "")
                    if slot_name:
                        slot_id = f"SLOT_{slot_name.upper().replace(' ', '_')}"
                        if slot_id not in slots_to_store:
                            slots_to_store[slot_id] = {
                                "slot_id": slot_id,
                                "slot_name": slot_name,
                                "template_id": template_id or "",
                                **slot,
                            }

        # ========== 第二步：写入 Template_Collection ==========
        template_count = 0
        for tpl_id, tpl_data in templates_to_store.items():
            description = self._generate_template_description(tpl_data)
            payload = self._render_collection_payload(
                tag="[TEMPLATE]",
                identifier=tpl_id,
                description=description,
                extra={
                    "standard_code": (tpl_data.get("semantic_routing") or {}).get("standard_code", ""),
                    "category": (tpl_data.get("semantic_routing") or {}).get("category", ""),
                },
            )
            storage_id = f"t_{hashstr(f'{tpl_id}_{file_id}', 12)}"
            try:
                await rag.ainsert(input=payload, ids=storage_id, file_paths=file_path)
                template_count += 1
            except Exception as e:
                logger.warning(f"模板写入失败: {tpl_id}, {e}")

        # ========== 第三步：写入 Section_Collection ==========
        section_count = 0
        for section in structured_doc.sections:
            section_meta = {
                **section,
                "node_type": "section",
            }
            display_text = self._render_section_payload(section_meta)
            sid = section.get("section_id", "").replace(".", "_")
            storage_id = f"sec_{hashstr(f'{sid}_{file_id}', 12)}"
            try:
                await rag.ainsert(input=display_text, ids=storage_id, file_paths=file_path)
                section_count += 1
            except Exception as e:
                logger.warning(f"章节写入失败: {sid}, {e}")

        # ========== 第四步：写入 Slot_Collection ==========
        slot_count = 0
        for slot_id, slot_data in slots_to_store.items():
            description = self._generate_slot_description(slot_data)
            slot_extra = {
                "type": slot_data.get("type", "string"),
                "template_id": slot_data.get("template_id", ""),
            }
            if slot_data.get("is_anchor"):
                slot_extra["anchor"] = "true"
            if slot_data.get("required"):
                slot_extra["required"] = "true"
            payload = self._render_collection_payload(
                tag="[SLOT]",
                identifier=slot_data.get("slot_name", ""),
                description=description,
                extra=slot_extra,
            )
            storage_id = f"s_{hashstr(f'{slot_id}_{file_id}', 12)}"
            try:
                await rag.ainsert(input=payload, ids=storage_id, file_paths=file_path)
                slot_count += 1
            except Exception as e:
                logger.warning(f"插槽写入失败: {slot_id}, {e}")

        await self._ensure_doc_processed(rag, file_id)

        logger.info(
            "结构化入库完成: file_id=%s, chunks=%d, templates=%d, "
            "sections=%d, slots=%d, industry=%s, report_type=%s",
            file_id, chunk_count, template_count,
            section_count, slot_count, industry, report_type,
        )

    # ========== 模板/插槽描述生成 ==========

    def _generate_template_description(self, template_data: dict[str, Any]) -> str:
        """生成模板的自然语言描述，用于 Template_Collection 语义检索"""
        parts = []

        semantic_routing = template_data.get("semantic_routing") or {}
        category = semantic_routing.get("category", "")
        standard_code = semantic_routing.get("standard_code", "")

        if category:
            parts.append(f"适用于{category}类别的写作模板")
        if standard_code:
            parts.append(f"标准代码：{standard_code}")

        slots = template_data.get("slots") or []
        if slots:
            slot_descs = []
            for s in slots[:5]:
                name = s.get("name", "")
                desc = s.get("description", "")
                if name and desc:
                    slot_descs.append(f"{name}（{desc}）")
                elif name:
                    slot_descs.append(name)
            if slot_descs:
                parts.append(f"包含插槽：{', '.join(slot_descs)}")

        generalized = template_data.get("generalized", "")
        if generalized:
            pattern_text = generalized.replace("{{", "").replace("}}", "")
            if len(pattern_text) > 100:
                pattern_text = pattern_text[:100] + "..."
            parts.append(f"模板格式：{pattern_text}")

        return "。".join(parts) if parts else "写作模板"

    def _generate_slot_description(self, slot_data: dict[str, Any]) -> str:
        """生成插槽的自然语言描述，用于 Slot_Collection 语义检索"""
        parts = []

        description = slot_data.get("description", "")
        if description:
            parts.append(description)
        else:
            parts.append(f"插槽 {slot_data.get('slot_name', '')}")

        slot_type = slot_data.get("type", "string")
        parts.append(f"数据类型：{slot_type}")

        required = slot_data.get("required", False)
        parts.append(f"是否必填：{'是' if required else '否'}")

        is_anchor = slot_data.get("is_anchor", False)
        if is_anchor:
            parts.append("这是一个锚点插槽，用于模板匹配的关键字段。")

        constraints = slot_data.get("constraints", [])
        if constraints:
            if isinstance(constraints, list):
                constraint_text = "、".join(f'"{c}"' for c in constraints)
                parts.append(f"约束条件：必须包含 {constraint_text} 等关键词。")
            else:
                parts.append(f"约束条件：{constraints}")

        default_value = slot_data.get("default_value")
        if default_value:
            parts.append(f"默认值：{default_value}")

        value = slot_data.get("value")
        if value:
            parts.append(f"示例值：{value}")

        data_source = slot_data.get("data_source") or slot_data.get("suggested_source", "")
        if data_source:
            parts.append(f"数据来源：{data_source}")

        entity_ref = slot_data.get("entity_ref", "")
        if entity_ref:
            parts.append(f"关联实体：{entity_ref}")

        return "\n".join(parts)

    def _render_collection_payload(
        self,
        tag: str,
        identifier: str,
        description: str,
        extra: dict[str, str] | None = None,
    ) -> str:
        """渲染集合条目的 payload 文本"""
        header_parts = [f"{tag} {identifier}"]
        for key, value in (extra or {}).items():
            if value:
                header_parts.append(f"[{key.upper()}] {value}")
        header = " | ".join(header_parts)
        return f"{header}\n{description}" if header else description

    def _render_section_payload(self, section_meta: dict[str, Any]) -> str:
        """渲染章节的 payload 文本，用于 Section_Collection 语义检索"""
        section_id = section_meta.get("section_id", "")
        title = section_meta.get("title", "")
        summary = section_meta.get("summary", "")

        info = f"[SECTION] {section_id} {title}".strip()

        count = len(section_meta.get("chunk_indexes", []))
        if count:
            info += f" ({count} 段落)"

        if summary:
            return f"{info}\n{summary}"
        return info

    # ========== Outline Collection（章节大纲进化） ==========

    async def ingest_outline_collection(
        self,
        db_id: str,
        domain: str,
        report_type: str,
        outline_sections: list[dict[str, Any]],
    ) -> int:
        """将领域报告大纲写入 Outline_Collection（全量替换策略）

        每个 section 节点（含 writing_guidance 和 entity_bindings）作为独立向量条目，
        供 Skill 运行时通过 query_kb 查询 [OUTLINE] 标记的条目获取最新大纲。

        Args:
            db_id: 知识库 ID
            domain: 领域代码（如 coal）
            report_type: 报告类型（如 eia）
            outline_sections: 扁平化的章节列表，每个含 title/level/writing_guidance/entity_bindings

        Returns:
            写入的条目数量
        """
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Failed to get LightRAG instance for {db_id}")

        try:
            await rag.initialize_storages()
        except Exception as e:
            logger.warning(f"initialize_storages 失败: {e}")

        # 大纲条目使用稳定的 storage_id（基于 domain+report_type+section_path），
        # 相同 section_path 重写入会覆盖更新；已移除的章节旧条目会被自然稀释
        outline_file_path = f"outline/{domain}_{report_type}.md"

        count = 0
        for section in outline_sections:
            section_path = section.get("section_path", "")
            title = section.get("title", "")
            level = section.get("level", 1)

            description = self._generate_outline_description(section)
            storage_id = f"ol_{hashstr(f'{domain}_{report_type}_{section_path}', 10)}"

            payload = self._render_collection_payload(
                tag="[OUTLINE]",
                identifier=f"{section_path} {title}".strip(),
                description=description,
                extra={
                    "domain": domain,
                    "report_type": report_type,
                    "level": str(level),
                    "section_path": section_path,
                },
            )

            try:
                await rag.ainsert(
                    input=payload,
                    ids=storage_id,
                    file_paths=outline_file_path,
                )
                count += 1
            except Exception as e:
                logger.warning(f"大纲条目写入失败: {section_path} {title}, {e}")

        logger.info(
            "Outline_Collection 入库完成: domain=%s, report_type=%s, entries=%d",
            domain, report_type, count,
        )
        return count

    def _generate_outline_description(self, section: dict[str, Any]) -> str:
        """生成章节大纲条目的自然语言描述"""
        parts = []
        title = section.get("title", "")
        if title:
            parts.append(f"章节：{title}")

        wg = section.get("writing_guidance")
        if isinstance(wg, dict):
            overview = wg.get("overview", "")
            if overview:
                parts.append(f"概要：{overview}")

            key_points = wg.get("key_points", [])
            if key_points:
                pts = "\n".join(f"  - {p}" for p in key_points[:8])
                parts.append(f"编写要点：\n{pts}")

            content_reqs = wg.get("content_requirements", [])
            if content_reqs:
                reqs = "；".join(content_reqs[:6])
                parts.append(f"内容要求：{reqs}")

            regulations = wg.get("regulations", [])
            if regulations:
                regs = "、".join(
                    r.get("name", str(r)) if isinstance(r, dict) else str(r)
                    for r in regulations[:5]
                )
                parts.append(f"相关法规：{regs}")

        bindings = section.get("entity_bindings")
        if isinstance(bindings, list) and bindings:
            names = [b.get("entity_name", "") for b in bindings[:8] if b.get("entity_name")]
            if names:
                parts.append(f"关联实体：{', '.join(names)}")

        return "\n".join(parts)

    async def update_content(self, db_id: str, file_ids: list[str], params: dict | None = None) -> list[dict]:
        """更新内容 - 根据file_ids重新解析文件并更新向量库"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        db_write_lock = await self._get_db_write_lock(db_id)
        async with db_write_lock:
            rag = await self._get_lightrag_instance(db_id)
            if not rag:
                raise ValueError(f"Failed to get LightRAG instance for {db_id}")

            # 处理默认参数
            if params is None:
                params = {}
            processed_items_info = []

            for file_id in file_ids:
                # 从元数据中获取文件信息
                if file_id not in self.files_meta:
                    logger.warning(f"File {file_id} not found in metadata, skipping")
                    continue

                file_meta = self.files_meta[file_id]
                file_path = file_meta.get("path")

                if not file_path:
                    logger.warning(f"File path not found for {file_id}, skipping")
                    continue

                # 添加到处理队列
                self._add_to_processing_queue(file_id)

                try:
                    # 更新状态为处理中
                    resolved_params = resolve_chunk_processing_params(
                        kb_additional_params=self.databases_meta.get(db_id, {}).get("metadata"),
                        file_processing_params=self.files_meta[file_id].get("processing_params"),
                        request_params=params,
                    )
                    self.files_meta[file_id]["processing_params"] = resolved_params
                    self.files_meta[file_id]["status"] = "processing"
                    await self._persist_file(file_id)

                    # 重新解析文件为 markdown
                    params["image_bucket"] = "public"
                    params["image_prefix"] = f"{db_id}/kb-images"
                    markdown_content = await Parser.aparse(source=file_path, params=params)
                    markdown_content_lines = markdown_content[:100].replace("\n", " ")
                    logger.info(f"Markdown content: {markdown_content_lines}...")
                    filename = file_meta.get("filename") or file_id
                    chunks = chunk_markdown(markdown_content, file_id, filename, resolved_params)
                    chunk_input, split_by_character, split_by_character_only = self._prepare_lightrag_insert_payload(
                        chunks
                    )
                    if not chunk_input:
                        chunk_input = markdown_content

                    # 先删除现有的 LightRAG 数据（仅删除chunks，保留元数据）
                    await self.delete_file_chunks_only(db_id, file_id)

                    # 使用 LightRAG 重新插入内容
                    await rag.ainsert(
                        input=chunk_input,
                        ids=file_id,
                        file_paths=file_path,
                        split_by_character=split_by_character,
                        split_by_character_only=split_by_character_only,
                    )
                    await self._ensure_doc_processed(rag, file_id)

                    logger.info(f"Updated file {file_path} in LightRAG. Done.")

                    # 更新元数据状态
                    self.files_meta[file_id]["status"] = "done"
                    await self._persist_file(file_id)

                    # 从处理队列中移除
                    self._remove_from_processing_queue(file_id)

                    # 返回更新后的文件信息
                    updated_file_meta = file_meta.copy()
                    updated_file_meta["status"] = "done"
                    updated_file_meta["file_id"] = file_id
                    processed_items_info.append(updated_file_meta)

                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"更新file {file_path} 失败: {error_msg}, {traceback.format_exc()}")
                    self.files_meta[file_id]["status"] = "failed"
                    self.files_meta[file_id]["error"] = error_msg
                    await self._persist_file(file_id)

                    # 从处理队列中移除
                    self._remove_from_processing_queue(file_id)

                    # 返回失败的文件信息
                    failed_file_meta = file_meta.copy()
                    failed_file_meta["status"] = "failed"
                    failed_file_meta["file_id"] = file_id
                    failed_file_meta["error"] = error_msg
                    processed_items_info.append(failed_file_meta)

            return processed_items_info

    async def aquery(self, query_text: str, db_id: str, agent_call: bool = False, **kwargs) -> str:
        """异步查询知识库"""
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Database {db_id} not found")

        try:
            # QueryParam 支持的参数列表
            valid_params = {
                "mode",
                "only_need_context",
                "only_need_prompt",
                "response_type",
                "stream",
                "top_k",
                "chunk_top_k",
                "max_entity_tokens",
                "max_relation_tokens",
                "max_total_tokens",
                "hl_keywords",
                "ll_keywords",
                "conversation_history",
                "history_turns",
                "model_func",
                "user_prompt",
                "enable_rerank",
                "include_references",
            }

            # 过滤 kwargs，只保留 QueryParam 支持的参数
            query_params = self._get_query_params(db_id)
            query_params = query_params | kwargs
            filtered_kwargs = {k: v for k, v in query_params.items() if k in valid_params}

            # 设置查询参数
            params_dict = {
                "mode": "mix",
                "only_need_context": True,
                "top_k": 10,
            } | filtered_kwargs
            param = QueryParam(**params_dict)

            # 执行查询
            response = await rag.aquery_data(query_text, param)
            logger.debug(f"Query response: {str(response)[:1000]}...")

            if agent_call:
                scope = query_params.get("retrieval_content_scope", "chunks")
                data = response.get("data", {}) or {}

                if scope == "chunks":
                    return data.get("chunks", [])

                result = {}
                if scope in ["graph", "all"]:
                    # 过滤掉无关信息，保留实体和关系的核心内容
                    exclude_keys = {"source_id", "file_path", "created_at"}

                    ents = data.get("entities", [])
                    rels = data.get("relationships", [])

                    result["entities"] = [{k: v for k, v in e.items() if k not in exclude_keys} for e in ents]
                    result["relationships"] = [{k: v for k, v in r.items() if k not in exclude_keys} for r in rels]
                    result["references"] = data.get("references", [])

                if scope == "all":
                    result["chunks"] = data.get("chunks", [])

                return result

            return response

        except Exception as e:
            logger.error(f"Query error: {e}, {traceback.format_exc()}")
            return ""

    async def delete_file_chunks_only(self, db_id: str, file_id: str) -> None:
        """仅删除文件的chunks数据，保留元数据（用于更新操作）"""
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 使用 LightRAG 删除文档
                await rag.adelete_by_doc_id(file_id)
                logger.info(f"Deleted chunks for file {file_id} from LightRAG")
            except Exception as e:
                logger.error(f"Error deleting file {file_id} from LightRAG: {e}")
        # 注意：这里不删除 files_meta[file_id]，保留元数据用于后续操作

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件（包括元数据）"""
        # 先删除 LightRAG 中的 chunks 数据
        await self.delete_file_chunks_only(db_id, file_id)

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            from yuxi.repositories.knowledge_file_repository import KnowledgeFileRepository

            await KnowledgeFileRepository().delete(file_id)

    async def get_file_basic_info(self, db_id: str, file_id: str) -> dict:
        """获取文件基本信息（仅元数据）"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        return {"meta": self.files_meta[file_id]}

    async def get_file_content(self, db_id: str, file_id: str) -> dict:
        """获取文件内容信息（chunks和lines）"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 LightRAG 获取 chunks
        content_info = {"lines": []}
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 获取文档的所有 chunks
                # LightRAG v1.4+ 使用 JsonKVStorage，通过 _data 属性访问所有数据
                if hasattr(rag.text_chunks, "_data"):
                    all_chunks = dict(rag.text_chunks._data)
                else:
                    logger.warning("text_chunks does not have _data attribute, cannot get file content")
                    return content_info

                # 筛选属于该文档的 chunks
                doc_chunks = []
                for chunk_id, chunk_data in all_chunks.items():
                    if isinstance(chunk_data, dict) and chunk_data.get("full_doc_id") == file_id:
                        chunk_data["id"] = chunk_id
                        chunk_data["content_vector"] = []
                        doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                content_info["lines"] = doc_chunks

            except Exception as e:
                logger.error(f"Failed to get file content from LightRAG: {e}")
                content_info["lines"] = []

        # Try to read markdown content if available
        file_meta = self.files_meta[file_id]
        if file_meta.get("markdown_file"):
            try:
                content = await self._read_markdown_from_minio(file_meta["markdown_file"])
                content_info["content"] = content
            except Exception as e:
                logger.error(f"Failed to read markdown file for {file_id}: {e}")

        return content_info

    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """获取文件完整信息（基本信息+内容信息）- 保持向后兼容"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 合并基本信息和内容信息
        basic_info = await self.get_file_basic_info(db_id, file_id)
        content_info = await self.get_file_content(db_id, file_id)

        return {**basic_info, **content_info}

    def get_query_params_config(self, db_id: str, **kwargs) -> dict:
        """获取 LightRAG 知识库的查询参数配置"""
        options = [
            {
                "key": "mode",
                "label": "检索模式",
                "type": "select",
                "default": "mix",
                "options": [
                    {"value": "local", "label": "Local", "description": "上下文相关信息"},
                    {"value": "global", "label": "Global", "description": "全局知识"},
                    {"value": "hybrid", "label": "Hybrid", "description": "本地和全局混合"},
                    {"value": "naive", "label": "Naive", "description": "基本搜索"},
                    {"value": "mix", "label": "Mix", "description": "知识图谱和向量检索混合"},
                ],
            },
            {
                "key": "only_need_context",
                "label": "只使用上下文",
                "type": "boolean",
                "default": True,
                "description": "只返回上下文，不生成回答",
            },
            {
                "key": "only_need_prompt",
                "label": "只使用提示",
                "type": "boolean",
                "default": False,
                "description": "只返回提示，不进行检索",
            },
            {
                "key": "top_k",
                "label": "TopK",
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 100,
                "description": "返回的最大结果数量",
            },
            {
                "key": "retrieval_content_scope",
                "label": "传递给 LLM 的内容",
                "type": "select",
                "default": "chunks",
                "options": [
                    {"value": "chunks", "label": "仅 Chunks", "description": "仅返回文档片段"},
                    {"value": "graph", "label": "仅 Entity/Relation", "description": "仅返回知识图谱信息"},
                    {"value": "all", "label": "全部", "description": "返回文档片段和知识图谱信息"},
                ],
            },
        ]

        return {"type": "lightrag", "options": options}

    async def export_data(self, db_id: str, format: str = "csv", **kwargs) -> str:
        """
        使用 LightRAG 原生功能导出知识库数据。
        [注意] 此功能当前已禁用。
        """
        # TODO: 修复 LightRAG 库与 Milvus 后端不兼容的问题
        # 当前调用 aexport_data 会导致 "'MilvusVectorDBStorage' object has no attribute 'client_storage'" 错误。
        # 在 lightrag 库修复此问题前，暂时禁用此功能。
        raise NotImplementedError("由于 LightRAG 库与 Milvus 后端不兼容，原生导出功能暂不可用。等待上游库修复。")

        # --- 以下为待修复后启用的代码 ---
        # logger.info(f"Exporting data for db_id {db_id} in format {format} with options {kwargs}")

        # rag = await self._get_lightrag_instance(db_id)
        # if not rag:
        #     raise ValueError(f"Failed to get LightRAG instance for {db_id}")

        # export_dir = os.path.join(self.work_dir, db_id, "exports")
        # os.makedirs(export_dir, exist_ok=True)

        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # output_filename = f"export_{db_id}_{timestamp}.{format}"
        # output_filepath = os.path.join(export_dir, output_filename)

        # include_vectors = kwargs.get('include_vectors', False)

        # # 直接调用 lightrag 的异步导出功能
        # # 之前的测试表明 aexport_data 确实存在，并且 to_thread 会导致 loop 问题
        # await rag.aexport_data(
        #     output_path=output_filepath,
        #     file_format=format,
        #     include_vector_data=include_vectors
        # )

        # logger.info(f"Successfully created export file: {output_filepath}")
        # return output_filepath
