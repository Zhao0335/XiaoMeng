"""
混合记忆检索 - 完全兼容 OpenClaw 混合搜索机制

OpenClaw 混合搜索：
- 向量搜索 (70%): 语义相似度，理解意图
- BM25 搜索 (30%): 关键词精确匹配，擅长代码/ID
- 结果融合：加权合并，去重排序

参考：
- OpenClaw memory-search.ts
- OpenClaw sqlite-vec 实现
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path
import re
import math
import json
from collections import defaultdict


@dataclass
class SearchResult:
    """搜索结果"""
    content: str
    score: float
    source: str  # "vector", "bm25", "hybrid"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "score": self.score,
            "source": self.source,
            "metadata": self.metadata
        }


class BM25Index:
    """
    BM25 关键词索引
    
    实现简单的 BM25 算法用于关键词搜索
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        
        self._documents: List[Dict[str, Any]] = []
        self._doc_lengths: List[int] = []
        self._term_freqs: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        self._doc_freqs: Dict[str, int] = defaultdict(int)
        self._avg_doc_length: float = 0
    
    def _tokenize(self, text: str) -> List[str]:
        """分词"""
        text = text.lower()
        tokens = re.findall(r'\w+', text)
        return tokens
    
    def add_document(self, doc_id: str, content: str, metadata: Dict = None):
        """添加文档到索引"""
        tokens = self._tokenize(content)
        doc_length = len(tokens)
        
        doc_idx = len(self._documents)
        self._documents.append({
            "id": doc_id,
            "content": content,
            "metadata": metadata or {}
        })
        self._doc_lengths.append(doc_length)
        
        term_counts = defaultdict(int)
        for token in tokens:
            term_counts[token] += 1
        
        for term, count in term_counts.items():
            self._term_freqs[term].append((doc_idx, count))
        
        for term in term_counts:
            self._doc_freqs[term] += 1
        
        total_length = sum(self._doc_lengths)
        self._avg_doc_length = total_length / len(self._doc_lengths) if self._doc_lengths else 0
    
    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """BM25 搜索"""
        if not self._documents:
            return []
        
        query_tokens = self._tokenize(query)
        N = len(self._documents)
        
        scores = defaultdict(float)
        
        for token in query_tokens:
            if token not in self._doc_freqs:
                continue
            
            df = self._doc_freqs[token]
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            
            for doc_idx, tf in self._term_freqs.get(token, []):
                doc_length = self._doc_lengths[doc_idx]
                
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / self._avg_doc_length)
                
                scores[doc_idx] += idf * numerator / denominator
        
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for doc_idx, score in sorted_results[:limit]:
            doc = self._documents[doc_idx]
            results.append(SearchResult(
                content=doc["content"],
                score=score,
                source="bm25",
                metadata=doc["metadata"]
            ))
        
        return results
    
    def clear(self):
        """清空索引"""
        self._documents.clear()
        self._doc_lengths.clear()
        self._term_freqs.clear()
        self._doc_freqs.clear()
        self._avg_doc_length = 0


class HybridMemorySearch:
    """
    混合记忆检索
    
    参考 OpenClaw 的混合搜索实现：
    - 向量搜索权重: 0.7 (默认)
    - BM25 搜索权重: 0.3 (默认)
    - 结果融合: 加权合并
    """
    
    def __init__(
        self,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        memory_dir: str = None
    ):
        self._vector_weight = vector_weight
        self._bm25_weight = bm25_weight
        self._bm25_index = BM25Index()
        
        self._memory_dir = Path(memory_dir) if memory_dir else None
        self._vector_client = None
    
    def set_vector_client(self, client):
        """设置向量客户端 (ChromaDB)"""
        self._vector_client = client
    
    def index_memory_files(self, memory_dir: str = None):
        """索引记忆文件"""
        target_dir = Path(memory_dir) if memory_dir else self._memory_dir
        if not target_dir:
            return
        
        self._bm25_index.clear()
        
        md_files = list(target_dir.glob("**/*.md"))
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                doc_id = str(md_file.relative_to(target_dir))
                self._bm25_index.add_document(
                    doc_id=doc_id,
                    content=content,
                    metadata={
                        "file_path": str(md_file),
                        "file_name": md_file.name
                    }
                )
            except Exception:
                continue
    
    def index_persona_files(self, persona_dir: str):
        """索引人设文件"""
        persona_path = Path(persona_dir)
        if not persona_path.exists():
            return
        
        persona_files = [
            "SOUL.md", "AGENTS.md", "IDENTITY.md", 
            "USER.md", "TOOLS.md", "MEMORY.md"
        ]
        
        for filename in persona_files:
            file_path = persona_path / filename
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding='utf-8')
                    self._bm25_index.add_document(
                        doc_id=f"persona/{filename}",
                        content=content,
                        metadata={
                            "file_path": str(file_path),
                            "type": "persona"
                        }
                    )
                except Exception:
                    continue
    
    def _normalize_scores(self, results: List[SearchResult]) -> List[SearchResult]:
        """归一化分数"""
        if not results:
            return results
        
        max_score = max(r.score for r in results)
        min_score = min(r.score for r in results)
        score_range = max_score - min_score
        
        if score_range == 0:
            return [SearchResult(
                content=r.content,
                score=1.0,
                source=r.source,
                metadata=r.metadata
            ) for r in results]
        
        return [SearchResult(
            content=r.content,
            score=(r.score - min_score) / score_range,
            source=r.source,
            metadata=r.metadata
        ) for r in results]
    
    async def vector_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """向量搜索"""
        if not self._vector_client:
            return []
        
        try:
            results = self._vector_client.search_similar(query, limit=limit)
            return [SearchResult(
                content=r.get("content", ""),
                score=r.get("distance", 0),
                source="vector",
                metadata=r.get("metadata", {})
            ) for r in results]
        except Exception:
            return []
    
    def bm25_search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """BM25 搜索"""
        return self._bm25_index.search(query, limit)
    
    def hybrid_search(
        self, 
        query: str, 
        limit: int = 10,
        vector_results: List[SearchResult] = None
    ) -> List[SearchResult]:
        """
        混合搜索
        
        Args:
            query: 查询文本
            limit: 返回结果数量
            vector_results: 预计算的向量搜索结果（可选）
        
        Returns:
            融合后的搜索结果
        """
        bm25_results = self.bm25_search(query, limit=limit * 2)
        
        if vector_results is None:
            vector_results = []
        
        bm25_results = self._normalize_scores(bm25_results)
        vector_results = self._normalize_scores(vector_results)
        
        merged = {}
        
        for r in vector_results:
            key = r.content[:100]
            if key not in merged:
                merged[key] = {"content": r.content, "score": 0, "sources": [], "metadata": r.metadata}
            merged[key]["score"] += r.score * self._vector_weight
            merged[key]["sources"].append("vector")
        
        for r in bm25_results:
            key = r.content[:100]
            if key not in merged:
                merged[key] = {"content": r.content, "score": 0, "sources": [], "metadata": r.metadata}
            merged[key]["score"] += r.score * self._bm25_weight
            merged[key]["sources"].append("bm25")
        
        sorted_results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        
        return [SearchResult(
            content=r["content"],
            score=r["score"],
            source="hybrid",
            metadata={**r["metadata"], "matched_by": r["sources"]}
        ) for r in sorted_results[:limit]]
    
    def search(
        self, 
        query: str, 
        limit: int = 10,
        use_vector: bool = True,
        use_bm25: bool = True
    ) -> List[SearchResult]:
        """
        统一搜索接口
        
        Args:
            query: 查询文本
            limit: 返回结果数量
            use_vector: 是否使用向量搜索
            use_bm25: 是否使用 BM25 搜索
        
        Returns:
            搜索结果
        """
        if use_vector and use_bm25:
            return self.hybrid_search(query, limit)
        elif use_vector:
            return self.bm25_search(query, limit)
        elif use_bm25:
            return self.bm25_search(query, limit)
        else:
            return []


def create_hybrid_search(
    memory_dir: str = None,
    persona_dir: str = None,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3
) -> HybridMemorySearch:
    """
    创建混合搜索实例
    
    Args:
        memory_dir: 记忆文件目录
        persona_dir: 人设文件目录
        vector_weight: 向量搜索权重
        bm25_weight: BM25 搜索权重
    
    Returns:
        配置好的混合搜索实例
    """
    search = HybridMemorySearch(
        vector_weight=vector_weight,
        bm25_weight=bm25_weight,
        memory_dir=memory_dir
    )
    
    if memory_dir:
        search.index_memory_files(memory_dir)
    
    if persona_dir:
        search.index_persona_files(persona_dir)
    
    return search
