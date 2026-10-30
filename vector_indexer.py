# -*- coding: utf-8 -*-
"""
向量索引器 - 为 logKnow 添加 ChromaDB 向量存储和混合检索能力

依赖: pip install chromadb sentence-transformers

功能:
  1. 向量化文档块 (bge-large-zh-v1.5)
  2. ChromaDB 持久化存储
  3. 混合检索: Whoosh关键词 + Chroma向量 → 融合排序(RRF)
  4. 批量索引和增量更新
"""

import os
import sys
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("vector_indexer")

# huggingface.co 在部分网络不可达, 提前切换镜像
# (HF_ENDPOINT 在 huggingface_hub 导入时读取, 必须在 import sentence_transformers 之前设置)
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")


class EmbeddingUnavailableError(RuntimeError):
    """嵌入模型不可用 (加载失败), 调用方应降级为关键词检索"""
    pass

# ============================================================
# 数据模型
# ============================================================

@dataclass
class DocumentChunk:
    """文档分块"""
    chunk_id: str
    content: str
    source_file: str
    source_type: str = "unknown"      # report / paper / manual / curve_desc / experience
    well_name: str = ""
    region: str = ""
    formation: str = ""
    depth_range: str = ""              # "1200-1500m"
    keywords: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """检索结果"""
    chunk_id: str
    content: str
    score: float
    source_file: str
    source_type: str
    method: str                       # "keyword" | "vector" | "hybrid"
    well_name: str = ""
    region: str = ""


# ============================================================
# 嵌入模型
# ============================================================

class EmbeddingModel:
    """嵌入模型封装，支持本地和API两种模式"""

    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5",
                 device: str = "cpu", use_api: bool = False,
                 api_base: str = None):
        self.model_name = model_name
        self.device = device
        self.use_api = use_api
        self.api_base = api_base
        self._model = None
        self._load_failed = False   # 加载失败标记 (检索时降级为关键词模式)

    def load(self):
        """加载嵌入模型

        策略: 优先本地缓存 (避免联网挂起), 失败后尝试镜像下载, 全部失败则降级
        """
        if self.use_api:
            logger.info(f"使用 API 嵌入模式: {self.api_base}")
            return
        if self._model is not None or self._load_failed:
            return

        from sentence_transformers import SentenceTransformer

        # 1) 先尝试纯本地加载 (不联网, 防止网络挂起)
        try:
            self._model = SentenceTransformer(
                self.model_name, device=self.device, local_files_only=True
            )
            logger.info(f"嵌入模型已加载 (本地缓存): {self.model_name}")
            return
        except Exception as e:
            logger.info(f"本地无缓存, 尝试下载: {self.model_name} ({e.__class__.__name__})")

        # 2) 联网下载 (走镜像)
        try:
            self._model = SentenceTransformer(self.model_name, device=self.device)
            logger.info(f"嵌入模型已加载: {self.model_name} (device={self.device})")
        except ImportError:
            logger.warning("sentence-transformers 未安装，尝试使用 HuggingFace API")
            self.use_api = True
            self._load_hf_api()
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {e} — 向量检索降级为关键词检索")
            self._load_failed = True

    @property
    def available(self) -> bool:
        """嵌入模型是否可用 (向量检索能力)"""
        if self.use_api:
            return True
        if self._load_failed:
            return False
        try:
            self.load()
        except Exception:
            return False
        return self._model is not None or self.use_api

    def _load_hf_api(self):
        """使用 HuggingFace Inference API"""
        if not self.api_base:
            self.api_base = f"https://api-inference.huggingface.co/models/{self.model_name}"
        logger.info(f"使用 HuggingFace API: {self.api_base}")

    def encode(self, texts: List[str], batch_size: int = 32,
               normalize: bool = True) -> List[List[float]]:
        """将文本列表编码为向量"""
        if not texts:
            return []

        if self.use_api:
            return self._encode_api(texts)

        if self._model is None:
            self.load()

        if self._model is None:
            # 模型加载失败, 抛出可识别异常供上层降级
            raise EmbeddingUnavailableError("嵌入模型不可用")

        # 本地编码
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=len(texts) > 100
        )
        return embeddings.tolist()

    def _encode_api(self, texts: List[str]) -> List[List[float]]:
        """通过 API 编码"""
        import requests
        headers = {}
        if hasattr(self, '_hf_token'):
            headers["Authorization"] = f"Bearer {self._hf_token}"

        all_embeddings = []
        for text in texts:
            try:
                resp = requests.post(
                    self.api_base,
                    headers=headers,
                    json={"inputs": text, "wait_for_model": True},
                    timeout=60
                )
                if resp.status_code == 200:
                    all_embeddings.append(resp.json()[0] if isinstance(resp.json(), list) else resp.json())
                else:
                    logger.warning(f"API 编码失败 ({resp.status_code}): {text[:50]}...")
                    all_embeddings.append([0.0] * 1024)  # fallback
            except Exception as e:
                logger.warning(f"API 编码异常: {e}")
                all_embeddings.append([0.0] * 1024)
        return all_embeddings

    def encode_single(self, text: str) -> List[float]:
        """编码单个文本"""
        return self.encode([text])[0]


# ============================================================
# 向量存储 (ChromaDB)
# ============================================================

class VectorStore:
    """ChromaDB 向量存储"""

    def __init__(self, persist_dir: str, collection_name: str = "log_knowledge"):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _init(self):
        """延迟初始化 ChromaDB"""
        if self._client is not None:
            return
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB 已连接: {self.persist_dir}/{self.collection_name} "
                       f"({self._collection.count()} documents)")
        except ImportError:
            raise ImportError("请安装 chromadb: pip install chromadb")

    @property
    def collection(self):
        self._init()
        return self._collection

    @property
    def count(self) -> int:
        self._init()
        return self._collection.count()

    def add(self, chunks: List[DocumentChunk], embeddings: List[List[float]]):
        """批量添加向量"""
        if not chunks:
            return

        self._init()

        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [{
            "source_file": c.source_file,
            "source_type": c.source_type,
            "well_name": c.well_name or "",
            "region": c.region or "",
            "formation": c.formation or "",
            "depth_range": c.depth_range or "",
            "keywords": ",".join(c.keywords) if c.keywords else "",
        } for c in chunks]

        # 分批添加（ChromaDB 单次上限约 50000 条）
        batch_size = 1000
        for i in range(0, len(ids), batch_size):
            end = min(i + batch_size, len(ids))
            try:
                self._collection.add(
                    ids=ids[i:end],
                    documents=documents[i:end],
                    embeddings=embeddings[i:end],
                    metadatas=metadatas[i:end]
                )
            except Exception as e:
                # 可能重复 ID，尝试逐条添加
                logger.warning(f"批量添加失败 ({i}-{end}): {e}，尝试逐条...")
                for j in range(i, end):
                    try:
                        self._collection.add(
                            ids=[ids[j]],
                            documents=[documents[j]],
                            embeddings=[embeddings[j]],
                            metadatas=[metadatas[j]]
                        )
                    except Exception as je:
                        logger.debug(f"跳过重复: {ids[j]} - {je}")

        logger.info(f"向量入库完成: {len(chunks)} chunks")

    def search(self, query_embedding: List[float], top_n: int = 10,
               region: str = None, well_name: str = None,
               source_type: str = None) -> List[Tuple[str, float, Dict]]:
        """向量相似度检索"""
        self._init()

        where_filter = {}
        if region:
            where_filter["region"] = region
        if well_name:
            where_filter["well_name"] = well_name
        if source_type:
            where_filter["source_type"] = source_type

        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_n
        }
        if where_filter:
            kwargs["where"] = where_filter

        results = self._collection.query(**kwargs)

        output = []
        if results and results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                chunk_id = results['ids'][0][i]
                doc = results['documents'][0][i] if results['documents'] else ""
                score = 1.0 - results['distances'][0][i] if results['distances'] else 0.0
                meta = results['metadatas'][0][i] if results['metadatas'] else {}
                output.append((chunk_id, score, doc, meta))

        return output

    def list_source_files(self) -> set:
        """返回已入库的所有 source_file 集合 (用于增量索引去重)"""
        self._init()
        try:
            data = self._collection.get(include=["metadatas"])
            files = set()
            for m in data.get("metadatas", []) or []:
                if m and m.get("source_file"):
                    files.add(m.get("source_file"))
            return files
        except Exception as e:
            logger.warning(f"读取向量库来源列表失败: {e}")
            return set()

    def delete_by_source(self, source_file: str):
        """按来源删除"""
        self._init()
        try:
            self._collection.delete(where={"source_file": source_file})
        except Exception as e:
            logger.warning(f"删除失败: {e}")

    def clear(self):
        """清空集合"""
        self._init()
        try:
            self._client.delete_collection(self.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.warning(f"清空失败: {e}")


# ============================================================
# 向量索引器 (主类)
# ============================================================

class VectorIndexer:
    """向量索引器 - 整合嵌入模型和向量存储"""

    def __init__(self, persist_dir: str = "data/vector_index",
                 embedding_model: str = "BAAI/bge-large-zh-v1.5",
                 device: str = "cpu",
                 chunk_size: int = 800,
                 chunk_overlap: int = 150):
        self.persist_dir = persist_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.embedder = EmbeddingModel(model_name=embedding_model, device=device)
        self.store = VectorStore(persist_dir=persist_dir)
        self._chunk_index = {}  # chunk_id -> DocumentChunk

    # ---------- 分块 ----------

    def chunk_text(self, text: str, source_file: str,
                   source_type: str = "unknown",
                   well_name: str = "", region: str = "",
                   formation: str = "", depth_range: str = "",
                   keywords: List[str] = None) -> List[DocumentChunk]:
        """将文本按语义边界切分为多个chunk"""
        chunks = []
        text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        source_stem = Path(source_file).stem[:30]

        # 按段落切分
        paragraphs = self._split_paragraphs(text)
        chunks_list = self._merge_paragraphs_to_chunks(paragraphs)

        for i, chunk_text in enumerate(chunks_list):
            chunk_id = f"{source_stem}_{text_hash}_{i:04d}"
            chunk = DocumentChunk(
                chunk_id=chunk_id,
                content=chunk_text,
                source_file=source_file,
                source_type=source_type,
                well_name=well_name,
                region=region,
                formation=formation,
                depth_range=depth_range,
                keywords=keywords or [],
            )
            chunks.append(chunk)
            self._chunk_index[chunk_id] = chunk

        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        """将文本拆分为段落"""
        # 先按双换行拆分
        parts = text.split('\n\n')
        paragraphs = []
        for part in parts:
            part = part.strip()
            if part:
                # 再按单换行拆分子段落
                sub = [s.strip() for s in part.split('\n') if s.strip()]
                if sub:
                    paragraphs.append('\n'.join(sub))
        return paragraphs

    def _merge_paragraphs_to_chunks(self, paragraphs: List[str]) -> List[str]:
        """将段落合并为指定大小的 chunk"""
        chunks = []
        current = ""
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            if current_len + para_len > self.chunk_size and current_len > 0:
                chunks.append(current.strip())
                # 保留 overlap
                overlap_text = current[-self.chunk_overlap:] if len(current) > self.chunk_overlap else ""
                current = overlap_text + "\n" + para
                current_len = len(current)
            else:
                if current:
                    current += "\n" + para
                else:
                    current = para
                current_len = len(current)

        if current.strip():
            chunks.append(current.strip())

        return chunks

    # ---------- 文档向量化 ----------

    def index_document(self, content: str, source_file: str,
                       source_type: str = "unknown",
                       well_name: str = "", region: str = "",
                       formation: str = "", depth_range: str = "",
                       keywords: List[str] = None) -> int:
        """将单个文档分块并向量化入���"""
        chunks = self.chunk_text(
            content, source_file, source_type,
            well_name, region, formation, depth_range, keywords
        )

        if not chunks:
            return 0

        texts = [c.content for c in chunks]
        embeddings = self.embedder.encode(texts)
        self.store.add(chunks, embeddings)

        return len(chunks)

    def index_documents(self, documents: List[Dict[str, Any]],
                        add_batch_size: int = 320) -> int:
        """批量索引文档 (按来源分批向量化, 每批立即落盘)

        2026-10-12 改造: 原实现将全部 chunk 攒到内存、最后一次性写入 Chroma,
        长任务被中断时全部进度丢失。现按来源分组、整来源凑批 (来源不跨批,
        避免中断后残留半来源), 每批 encode 后立即 add 落盘 —— 被中断时
        已完成批次持久保留, 重跑经 source_file 判重自动续传, 最多损失一批。
        documents: [{"content": ..., "source_file": ..., ...}, ...]
        """
        per_doc_chunks = []

        for doc in documents:
            chunks = self.chunk_text(
                text=doc.get("content", ""),
                source_file=doc.get("source_file", "unknown"),
                source_type=doc.get("source_type", "unknown"),
                well_name=doc.get("well_name", ""),
                region=doc.get("region", ""),
                formation=doc.get("formation", ""),
                depth_range=doc.get("depth_range", ""),
                keywords=doc.get("keywords", []),
            )
            if chunks:
                per_doc_chunks.append(chunks)

        total = sum(len(c) for c in per_doc_chunks)

        # 整来源凑批: 单来源超批大小时独占一批
        batches = []
        cur, cur_n = [], 0
        for chunks in per_doc_chunks:
            if cur and cur_n + len(chunks) > add_batch_size:
                batches.append(cur)
                cur, cur_n = [], 0
            cur.extend(chunks)
            cur_n += len(chunks)
        if cur:
            batches.append(cur)

        done = 0
        for bi, batch in enumerate(batches, 1):
            texts = [c.content for c in batch]
            embeddings = self.embedder.encode(texts)
            self.store.add(batch, embeddings)
            done += len(batch)
            logger.info(f"向量落盘进度: 批次 {bi}/{len(batches)}, 累计 {done}/{total} chunks")

        logger.info(f"批量索引完成: {total} chunks, {len(documents)} documents")
        return total

    # ---------- 检索 ----------

    def search(self, query: str, top_n: int = 10,
               region: str = None, well_name: str = None,
               source_type: str = None) -> List[SearchResult]:
        """向量语义检索 (嵌入模型不可用时返回空列表)"""
        if not self.embedder.available:
            return []
        try:
            query_vec = self.embedder.encode_single(query)
        except EmbeddingUnavailableError:
            return []
        raw_results = self.store.search(
            query_vec, top_n=top_n,
            region=region, well_name=well_name,
            source_type=source_type
        )

        results = []
        for chunk_id, score, doc, meta in raw_results:
            results.append(SearchResult(
                chunk_id=chunk_id,
                content=doc[:500] if doc else "",
                score=round(score, 4),
                source_file=meta.get("source_file", ""),
                source_type=meta.get("source_type", "unknown"),
                method="vector",
                well_name=meta.get("well_name", ""),
                region=meta.get("region", ""),
            ))
        return results

    def hybrid_search(self, query: str,
                      keyword_results: List[Dict] = None,
                      top_n: int = 10,
                      region: str = None, well_name: str = None,
                      source_type: str = None) -> List[SearchResult]:
        """混合检索: 向量 + 关键词 → RRF融合排序

        Args:
            query: 查询文本
            keyword_results: 关键词搜索结果列表 [{"content":..., "score":..., "source":...}, ...]
            top_n: 返回数量
            region/well_name/source_type: 过滤条件

        Returns:
            融合排序后的结果列表 (嵌入模型不可用时直接返回关键词结果)
        """
        # 1. 向量检索 (不可用时降级为纯关键词结果)
        if not self.embedder.available:
            logger.info("嵌入模型不可用, 混合检索降级为纯关键词检索")
            return []
        vector_results = self.search(query, top_n=top_n * 2,
                                     region=region, well_name=well_name,
                                     source_type=source_type)
        if not vector_results:
            return []

        # 2. 融合排序 (Reciprocal Rank Fusion)
        return self._rrf_fusion(vector_results, keyword_results or [], top_n)

    def _rrf_fusion(self, vector_results: List[SearchResult],
                    keyword_results: List[Dict],
                    top_n: int, k: int = 60) -> List[SearchResult]:
        """RRF 融合排序"""
        scores = {}

        # 向量结果 (rank 从1开始)
        for rank, r in enumerate(vector_results, 1):
            key = (r.content[:100], r.source_file)
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank)

        # 关键词结果
        for rank, r in enumerate(keyword_results, 1):
            content = r.get("content", "")[:100]
            source = r.get("source", "")
            key = (content, source)
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank)

        # 按融合分数排序
        sorted_keys = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # 构建结果
        result_map = {}
        for r in vector_results:
            key = (r.content[:100], r.source_file)
            result_map[key] = r

        merged = []
        seen = set()
        for key, fuse_score in sorted_keys:
            if key in result_map:
                r = result_map[key]
                if r.chunk_id not in seen:
                    r.score = round(fuse_score, 4)
                    r.method = "hybrid"
                    merged.append(r)
                    seen.add(r.chunk_id)
                if len(merged) >= top_n:
                    break

        return merged

    # ---------- 统计 ----------

    def get_stats(self) -> Dict:
        """获取索引统计"""
        return {
            "total_vectors": self.store.count,
            "persist_dir": self.persist_dir,
            "embedding_model": self.embedder.model_name,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap
        }


# ============================================================
# logKnow 集成适配器
# ============================================================

class LogKnowVectorAdapter:
    """将 VectorIndexer 集成到 logKnow.WellLogKnowledgeBase 中

    用法:
        from logKnow import WellLogKnowledgeBase
        from vector_indexer import LogKnowVectorAdapter

        kb = WellLogKnowledgeBase()
        adapter = LogKnowVectorAdapter(kb)
        adapter.attach()  # 注入向量索引能力

        # 然后 kb 将获得:
        # kb.vector_search(query) -> 向量检索
        # kb.hybrid_search(query) -> 混合检索
        # kb.build_vector_index() -> 批量向量化
    """

    def __init__(self, knowledge_base, persist_dir: str = "data/vector_index",
                 embedding_model: str = "BAAI/bge-large-zh-v1.5"):
        self.kb = knowledge_base
        self.vector_indexer = VectorIndexer(
            persist_dir=persist_dir,
            embedding_model=embedding_model
        )

    def attach(self):
        """将向量检索方法注入知识库实例"""
        kb = self.kb
        vi = self.vector_indexer

        def vector_search(query, top_n=10, region=None, well_name=None, source_type=None):
            return vi.search(query, top_n, region=region,
                           well_name=well_name, source_type=source_type)

        def hybrid_search(query, top_n=10, region=None, well_name=None):
            # 先用原有 Whoosh 做关键词检索
            keyword_results = kb.search(query, top_n=min(top_n * 2, 20),
                                       region=region, well_name=well_name)
            fused = vi.hybrid_search(query, keyword_results, top_n,
                                     region=region, well_name=well_name)
            if fused:
                return fused
            # 向量检索不可用/为空时, 关键词结果降级返回
            from vector_indexer import SearchResult
            return [
                SearchResult(
                    chunk_id=f"kw_{i}", content=r.get("content", "")[:500],
                    score=r.get("score", 0.0),
                    source_file=r.get("source", r.get("source_file", "")),
                    source_type=r.get("source_type", "keyword"),
                    method="keyword",
                    region=region or "", well_name=well_name or "",
                )
                for i, r in enumerate(keyword_results[:top_n])
            ]

        def build_vector_index(force=False):
            return self._build_from_kb(kb, force=force)

        def ask_with_hybrid(question):
            """使用混合检索增强的问答"""
            # 混合检索获取上下文
            hybrid_results = hybrid_search(question, top_n=5)
            sources = []

            context_parts = []
            for r in hybrid_results:
                context_parts.append(f"【来源: {r.source_file} ({r.source_type})】\n{r.content}")
                sources.append(r.source_file)

            # 内置知识
            builtin = kb.builtin_knowledge.search_knowledge(question)
            for br in builtin[:2]:
                context_parts.append(f"【内置知识: {br['title']}】\n{br['content'][:500]}")

            context = "\n\n".join(context_parts)
            answer = kb.llm.generate(question, context)

            return {
                "question": question,
                "answer": answer,
                "sources": sources,
                "method": "hybrid_rag"
            }

        # 注入方法
        kb.vector_search = vector_search
        kb.hybrid_search = hybrid_search
        kb.build_vector_index = build_vector_index
        kb.ask_with_hybrid = ask_with_hybrid
        kb._vector_indexer = vi

        logger.info("向量索引适配器已注入 logKnow 知识库")

    def _build_from_kb(self, kb, force: bool = False) -> int:
        """从知识库批量构建向量索引 (支持文件级增量)

        force=False 时只向量化尚未入向量库的 source_file;
        向量库为空时全量构建.
        """
        vi = self.vector_indexer

        docs = []
        all_md = kb.markdown_loader.load_all(use_cache=False)

        for md in all_md:
            source_file = md.get("file_path", md.get("source", "unknown"))
            well_name = md.get("well_name", "")
            region = md.get("region", "")

            # 推断文档类型
            fname = Path(source_file).name.lower() if source_file else ""
            if "experience" in fname or "经验" in fname:
                src_type = "experience"
            elif "manual" in fname or "标准" in fname or "sop" in fname:
                src_type = "standard"
            elif "report" in fname or "报告" in fname:
                src_type = "report"
            elif "paper" in fname or "论文" in fname or "文献" in fname:
                src_type = "paper"
            else:
                src_type = "general"

            docs.append({
                "content": md.get("content", ""),
                "source_file": source_file,
                "source_type": src_type,
                "well_name": well_name,
                "region": region,
                "formation": md.get("formation", ""),
                "depth_range": md.get("depth_range", ""),
                "keywords": md.get("keywords", []),
            })

        # 增量: 跳过已入向量库的 source_file (force 时全量重建)
        if not force:
            existing = vi.store.list_source_files()
            if existing:
                new_docs = [d for d in docs if d["source_file"] not in existing]
                skipped = len(docs) - len(new_docs)
                logger.info(f"向量增量: 已有 {len(existing)} 个来源, 新增 {len(new_docs)} 个, 跳过 {skipped} 个")
                if not new_docs:
                    logger.info("无新增文档, 跳过向量构建")
                    return vi.store.count
                docs = new_docs
        elif force and vi.store.count > 0:
            logger.info("force 模式: 清空并重建向量索引")
            vi.store.clear()

        count = vi.index_documents(docs)
        return count


# ============================================================
# 命令行入口
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="向量索引器 - 管理工具")
    sub = parser.add_subparsers(dest="cmd")

    # build
    build_p = sub.add_parser("build", help="从 logKnow 构建向量索引")
    build_p.add_argument("--force", "-f", action="store_true", help="强制重建")
    build_p.add_argument("--persist-dir", default="data/vector_index", help="向量库存储路径")
    build_p.add_argument("--model", default="BAAI/bge-large-zh-v1.5", help="嵌入模型")

    # search
    search_p = sub.add_parser("search", help="向量检索")
    search_p.add_argument("--query", "-q", required=True, help="查询文本")
    search_p.add_argument("--top-n", "-n", type=int, default=5, help="返回数量")
    search_p.add_argument("--region", "-r", help="按地区过滤")
    search_p.add_argument("--well", "-w", help="按井名过滤")
    search_p.add_argument("--persist-dir", default="data/vector_index", help="向量库路径")
    search_p.add_argument("--model", default="BAAI/bge-large-zh-v1.5", help="嵌入模型")

    # stats
    sub.add_parser("stats", help="索引统计")

    args = parser.parse_args()

    if args.cmd == "build":
        from logKnow import WellLogKnowledgeBase
        kb = WellLogKnowledgeBase(auto_scan=False)
        adapter = LogKnowVectorAdapter(kb, persist_dir=args.persist_dir,
                                       embedding_model=args.model)
        adapter.attach()
        count = kb.build_vector_index(force=args.force)
        print(f"向量索引构建完成: {count} chunks")

    elif args.cmd == "search":
        vi = VectorIndexer(persist_dir=args.persist_dir,
                          embedding_model=args.model)
        results = vi.search(args.query, top_n=args.top_n,
                           region=args.region, well_name=args.well)
        for i, r in enumerate(results, 1):
            print(f"\n[{i}] score={r.score:.4f} | {r.source_file}")
            print(f"    {r.content[:200]}...")

    elif args.cmd == "stats":
        vi = VectorIndexer(persist_dir=args.persist_dir)
        stats = vi.get_stats()
        for k, v in stats.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
