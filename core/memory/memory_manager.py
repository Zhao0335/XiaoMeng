"""
XiaoMengCore 记忆管理器
兼容 OpenClaw 人设记忆系统，支持 Graphiti + RAG
"""

from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path
import json
import re
import os

from models import User, UserLevel, MemoryEntry, PersonaConfig, Source
from config import XiaoMengConfig, ConfigManager


class PersonaLoader:
    """
    人设加载器 - 完全兼容 OpenClaw
    
    加载 OpenClaw 格式的核心文件（参考 workspace.ts loadWorkspaceBootstrapFiles）：
    - SOUL.md - 人格定义（核心人格、性格特点、说话风格）
    - AGENTS.md - 行为规范（如何与不同用户交互、操作流程）
    - IDENTITY.md - 身份信息（名字、背景、能力、emoji风格）
    - USER.md - 用户信息（主人的信息、如何称谓用户）
    - TOOLS.md - 工具环境（可用工具说明）
    - MEMORY.md - 长期记忆（重要记忆、持久事实）
    - HEARTBEAT.md - 心跳任务（定时任务、主动行为）
    - BOOTSTRAP.md - 引导文件（首次初始化引导，完成后可删除）
    
    OpenClaw 工作区默认位置：~/.openclaw/workspace/
    """
    
    DEFAULT_BOOTSTRAP_FILES = [
        "AGENTS.md",
        "SOUL.md",
        "TOOLS.md",
        "IDENTITY.md",
        "USER.md",
        "HEARTBEAT.md",
        "BOOTSTRAP.md",
        "MEMORY.md",
    ]
    
    def __init__(self, persona_dir: str):
        self.persona_dir = Path(persona_dir)
    
    def load_file(self, filename: str) -> str:
        """加载单个文件"""
        file_path = self.persona_dir / filename
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    
    def load_persona(self) -> PersonaConfig:
        """加载完整人设"""
        return PersonaConfig(
            soul=self.load_file("SOUL.md"),
            agents=self.load_file("AGENTS.md"),
            identity=self.load_file("IDENTITY.md"),
            user_info=self.load_file("USER.md"),
            tools=self.load_file("TOOLS.md"),
            memory=self.load_file("MEMORY.md"),
            heartbeat=self.load_file("HEARTBEAT.md"),
            bootstrap=self.load_file("BOOTSTRAP.md")
        )
    
    def load_bootstrap_files(self) -> Dict[str, str]:
        """
        加载所有引导文件
        
        参考 OpenClaw loadWorkspaceBootstrapFiles
        返回文件名到内容的映射
        """
        result = {}
        for filename in self.DEFAULT_BOOTSTRAP_FILES:
            content = self.load_file(filename)
            if content:
                result[filename] = content
        return result
    
    def save_file(self, filename: str, content: str):
        """保存单个文件"""
        self.persona_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.persona_dir / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def save_persona(self, persona: PersonaConfig):
        """保存完整人设"""
        if persona.soul:
            self.save_file("SOUL.md", persona.soul)
        if persona.agents:
            self.save_file("AGENTS.md", persona.agents)
        if persona.identity:
            self.save_file("IDENTITY.md", persona.identity)
        if persona.user_info:
            self.save_file("USER.md", persona.user_info)
        if persona.tools:
            self.save_file("TOOLS.md", persona.tools)
        if persona.memory:
            self.save_file("MEMORY.md", persona.memory)
        if persona.heartbeat:
            self.save_file("HEARTBEAT.md", persona.heartbeat)
        if persona.bootstrap:
            self.save_file("BOOTSTRAP.md", persona.bootstrap)
    
    def append_to_memory(self, content: str):
        """追加内容到 MEMORY.md"""
        memory_path = self.persona_dir / "MEMORY.md"
        
        existing = ""
        if memory_path.exists():
            with open(memory_path, 'r', encoding='utf-8') as f:
                existing = f.read()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_entry = f"\n- [{timestamp}] {content}"
        
        with open(memory_path, 'w', encoding='utf-8') as f:
            f.write(existing + new_entry)
    
    def append_to_daily_memory(self, content: str, tags: List[str] = None):
        """
        追加内容到每日记忆文件
        
        参考 OpenClaw memory/YYYY-MM-DD.md 格式
        """
        memory_dir = self.persona_dir / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = memory_dir / f"{today}.md"
        
        header = ""
        if not daily_file.exists():
            header = f"# 记忆 - {datetime.now().strftime('%Y年%m月%d日')}\n\n"
        
        timestamp = datetime.now().strftime("%H:%M")
        tags_str = " ".join([f"#{t}" for t in tags]) if tags else ""
        entry = f"- [{timestamp}] {content} {tags_str}".strip() + "\n"
        
        with open(daily_file, 'a', encoding='utf-8') as f:
            if header:
                f.write(header)
            f.write(entry)
    
    def complete_bootstrap(self):
        """
        完成引导流程
        
        参考 OpenClaw：BOOTSTRAP.md 完成后可以删除
        """
        bootstrap_path = self.persona_dir / "BOOTSTRAP.md"
        if bootstrap_path.exists():
            bootstrap_path.unlink()
    
    def is_onboarding_complete(self) -> bool:
        """
        检查引导是否完成
        
        参考 OpenClaw workspace.ts isWorkspaceOnboardingCompleted
        """
        bootstrap_path = self.persona_dir / "BOOTSTRAP.md"
        return not bootstrap_path.exists()
    
    def file_exists(self, filename: str) -> bool:
        """检查文件是否存在"""
        return (self.persona_dir / filename).exists()
    
    def get_missing_files(self) -> List[str]:
        """获取缺失的核心文件"""
        missing = []
        for filename in self.DEFAULT_BOOTSTRAP_FILES:
            if not self.file_exists(filename):
                missing.append(filename)
        return missing
    
    def ensure_workspace(self):
        """
        确保工作区存在
        
        参考 OpenClaw ensureAgentWorkspace
        """
        self.persona_dir.mkdir(parents=True, exist_ok=True)
        
        for filename in self.DEFAULT_BOOTSTRAP_FILES:
            file_path = self.persona_dir / filename
            if not file_path.exists():
                file_path.touch()
        
        memory_dir = self.persona_dir / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        sessions_dir = self.persona_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def init_git_repo(self) -> bool:
        """
        初始化 Git 仓库
        
        参考 OpenClaw ensureGitRepo
        """
        git_dir = self.persona_dir / ".git"
        if git_dir.exists():
            return True
        
        try:
            import subprocess
            result = subprocess.run(
                ["git", "init"],
                cwd=str(self.persona_dir),
                capture_output=True,
                timeout=10000
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def is_git_available(self) -> bool:
        """检查 Git 是否可用"""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                timeout=2000
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def has_git_repo(self) -> bool:
        """检查是否有 Git 仓库"""
        return (self.persona_dir / ".git").exists()


class MarkdownMemoryStore:
    """
    Markdown 记忆存储
    
    兼容 OpenClaw 的 memory/ 目录格式
    每日记忆存储为 YYYY-MM-DD.md 文件
    
    支持按用户分组存储：
    - memory/owner/ - 主人的记忆（默认）
    - memory/users/{user_id}/ - 其他用户的记忆
    """
    
    def __init__(self, memory_dir: str):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_user_memory_dir(self, user_id: str) -> Path:
        """获取用户记忆目录"""
        if user_id == "owner" or user_id.startswith("owner_"):
            user_dir = self.memory_dir / "owner"
        else:
            user_dir = self.memory_dir / "users" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def get_daily_file(self, user_id: str, date: Optional[datetime] = None) -> Path:
        """获取用户每日记忆文件"""
        date = date or datetime.now()
        user_dir = self._get_user_memory_dir(user_id)
        return user_dir / f"{date.strftime('%Y-%m-%d')}.md"
    
    def add_entry(
        self, 
        content: str, 
        user_id: str = "owner",
        tags: List[str] = None, 
        date: Optional[datetime] = None
    ):
        """添加记忆条目 - 按用户分组"""
        date = date or datetime.now()
        file_path = self.get_daily_file(user_id, date)
        
        header = ""
        if not file_path.exists():
            header = f"# 记忆 - {date.strftime('%Y年%m月%d日')}\n\n"
        
        timestamp = date.strftime("%Y-%m-%d %H:%M")
        tags_str = " ".join([f"#{t}" for t in tags]) if tags else ""
        entry = f"- [{timestamp}] {content} {tags_str}".strip() + "\n"
        
        with open(file_path, 'a', encoding='utf-8') as f:
            if header:
                f.write(header)
            f.write(entry)
    
    def get_entries(self, user_id: str = "owner", date: Optional[datetime] = None) -> List[MemoryEntry]:
        """获取用户指定日期的记忆条目"""
        date = date or datetime.now()
        file_path = self.get_daily_file(user_id, date)
        
        if not file_path.exists():
            return []
        
        entries = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith("- ["):
                    entry = MemoryEntry.from_markdown_line(line)
                    if entry:
                        entries.append(entry)
        
        return entries
    
    def get_recent_entries(self, user_id: str = "owner", days: int = 7) -> List[MemoryEntry]:
        """获取用户最近几天的记忆"""
        entries = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            entries.extend(self.get_entries(user_id, date))
        return entries
    
    def search_entries(self, keyword: str, user_id: str = "owner", days: int = 30) -> List[MemoryEntry]:
        """搜索用户记忆条目"""
        entries = self.get_recent_entries(user_id, days)
        return [e for e in entries if keyword.lower() in e.content.lower()]
    
    def list_users(self) -> List[str]:
        """列出所有有记忆的用户"""
        users = []
        
        owner_dir = self.memory_dir / "owner"
        if owner_dir.exists():
            users.append("owner")
        
        users_dir = self.memory_dir / "users"
        if users_dir.exists():
            for user_dir in users_dir.iterdir():
                if user_dir.is_dir():
                    users.append(user_dir.name)
        
        return users


class VectorStore:
    """
    向量存储接口
    
    用于 RAG 检索，支持 ChromaDB
    """
    
    def __init__(self, persist_dir: str, enabled: bool = True):
        self.persist_dir = persist_dir
        self.enabled = enabled
        self._collection = None
        
        if self.enabled:
            self._init_chroma()
    
    def _init_chroma(self):
        """初始化 ChromaDB"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_or_create_collection(
                name="xiaomeng_memories"
            )
        except ImportError:
            self.enabled = False
    
    def add_memory(self, entry: MemoryEntry, user_id: str):
        """添加记忆到向量库"""
        if not self.enabled or not self._collection:
            return
        
        self._collection.add(
            documents=[entry.content],
            metadatas=[{
                "user_id": user_id,
                "timestamp": entry.timestamp.isoformat(),
                "tags": ",".join(entry.tags)
            }],
            ids=[entry.entry_id]
        )
    
    def search_similar(self, query: str, user_id: str, n_results: int = 5) -> List[Dict]:
        """搜索相似记忆"""
        if not self.enabled or not self._collection:
            return []
        
        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id}
        )
        
        memories = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                memories.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0
                })
        
        return memories
    
    def delete_user_memories(self, user_id: str):
        """删除用户的所有向量记忆"""
        if not self.enabled or not self._collection:
            return
        
        results = self._collection.get(
            where={"user_id": user_id}
        )
        
        if results and results["ids"]:
            self._collection.delete(ids=results["ids"])


class GraphStore:
    """
    图谱存储接口
    
    用于 Graphiti 时序知识图谱
    """
    
    def __init__(self, uri: str, enabled: bool = False):
        self.uri = uri
        self.enabled = enabled
        self._driver = None
        
        if self.enabled:
            self._init_neo4j()
    
    def _init_neo4j(self):
        """初始化 Neo4j 连接"""
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(self.uri)
        except ImportError:
            self.enabled = False
    
    def close(self):
        """关闭连接"""
        if self._driver:
            self._driver.close()
    
    def add_fact(self, user_id: str, subject: str, relation: str, obj: str, timestamp: datetime):
        """添加事实到图谱"""
        if not self.enabled or not self._driver:
            return
        
        with self._driver.session() as session:
            session.run(
                """
                MERGE (u:User {id: $user_id})
                MERGE (s:Entity {name: $subject})
                MERGE (o:Entity {name: $obj})
                MERGE (s)-[r:RELATION {type: $relation, timestamp: $timestamp}]->(o)
                MERGE (u)-[:KNOWS]->(s)
                MERGE (u)-[:KNOWS]->(o)
                """,
                user_id=user_id,
                subject=subject,
                relation=relation,
                obj=obj,
                timestamp=timestamp.isoformat()
            )
    
    def query_facts(self, user_id: str, entity: str = None) -> List[Dict]:
        """查询事实"""
        if not self.enabled or not self._driver:
            return []
        
        with self._driver.session() as session:
            if entity:
                result = session.run(
                    """
                    MATCH (u:User {id: $user_id})-[:KNOWS]->(e:Entity {name: $entity})
                    MATCH (e)-[r:RELATION]->(o:Entity)
                    RETURN e.name as subject, r.type as relation, o.name as object, r.timestamp as timestamp
                    ORDER BY r.timestamp DESC
                    """,
                    user_id=user_id,
                    entity=entity
                )
            else:
                result = session.run(
                    """
                    MATCH (u:User {id: $user_id})-[:KNOWS]->(s:Entity)-[r:RELATION]->(o:Entity)
                    RETURN s.name as subject, r.type as relation, o.name as object, r.timestamp as timestamp
                    ORDER BY r.timestamp DESC
                    LIMIT 50
                    """,
                    user_id=user_id
                )
            
            facts = []
            for record in result:
                facts.append({
                    "subject": record["subject"],
                    "relation": record["relation"],
                    "object": record["object"],
                    "timestamp": record["timestamp"]
                })
            
            return facts


from datetime import timedelta


class MemoryManager:
    """
    记忆管理器
    
    统一管理所有类型的记忆：
    1. 人设记忆 - OpenClaw 核心文件
    2. 短期记忆 - 会话上下文
    3. 长期记忆 - Markdown 日记
    4. 向量记忆 - RAG 检索
    5. 图谱记忆 - 时序知识图谱
    """
    
    _instance: Optional["MemoryManager"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[XiaoMengConfig] = None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self._config = config or ConfigManager.get_instance().get()
        self._data_dir = Path(self._config.data_dir)
        
        self._persona_loader = PersonaLoader(str(self._data_dir))
        self._markdown_store = MarkdownMemoryStore(str(self._data_dir / "memory"))
        
        self._vector_store = VectorStore(
            self._config.memory.chroma_persist_dir,
            self._config.memory.vector_enabled
        )
        
        self._graph_store = GraphStore(
            self._config.memory.graphiti_uri,
            self._config.memory.graph_enabled
        )
        
        from .daily_memory import DailyMemoryManager
        from .hybrid_search import HybridMemorySearch
        from .semantic import SemanticAnalyzer
        from .graphiti import GraphitiMemoryStore
        from .multimodal import MultimodalEmotionFusion
        
        daily_memory_dir = str(self._data_dir / "memory" / "daily")
        self._daily_memory = DailyMemoryManager(daily_memory_dir)
        
        self._hybrid_search = HybridMemorySearch(
            memory_dir=str(self._data_dir / "memory"),
            vector_weight=0.7,
            bm25_weight=0.3
        )
        self._hybrid_search.index_persona_files(str(self._data_dir / "persona"))
        
        self._semantic_analyzer = SemanticAnalyzer(
            use_transformer=getattr(self._config.memory, 'use_transformer', False)
        )
        
        self._graphiti_store = GraphitiMemoryStore(
            local_path=str(self._data_dir / "graphiti"),
            use_neo4j=self._config.memory.graph_enabled,
            uri=self._config.memory.graphiti_uri
        )
        
        from .modality_plugin import ModalityPluginSystem, create_plugin_system
        from .builtin_plugins import create_default_plugins
        
        self._modality_system = create_plugin_system(
            default_fusion="attention",
            parallel=True
        )
        for plugin in create_default_plugins():
            self._modality_system.register_plugin(plugin)
        
        self._emotion_fusion = MultimodalEmotionFusion()
        
        self._user_memories: Dict[str, Dict] = {}
        self._initialized = True
    
    def load_persona(self) -> PersonaConfig:
        """加载人设"""
        return self._persona_loader.load_persona()
    
    def save_persona(self, persona: PersonaConfig):
        """保存人设"""
        self._persona_loader.save_persona(persona)
    
    def get_system_prompt(self, user: User, is_group: bool = False) -> str:
        """根据用户等级获取系统提示"""
        persona = self.load_persona()
        return persona.get_system_prompt(user.level, is_group=is_group)
    
    def add_memory(
        self, 
        user: User, 
        content: str, 
        tags: List[str] = None,
        importance: int = 1
    ):
        """添加记忆"""
        entry = MemoryEntry(
            entry_id=str(uuid.uuid4()),
            content=content,
            timestamp=datetime.now(),
            source=None,
            importance=importance,
            tags=tags or []
        )
        
        user_id = user.user_id if user.level == UserLevel.OWNER else f"user_{user.user_id}"
        
        self._markdown_store.add_entry(content, user_id, tags)
        
        if self._config.memory.vector_enabled:
            self._vector_store.add_memory(entry, user.user_id)
    
    def search_memories(self, user: User, query: str, limit: int = 5) -> List[Dict]:
        """搜索记忆 - 按用户分组"""
        results = []
        
        user_id = user.user_id if user.level == UserLevel.OWNER else f"user_{user.user_id}"
        
        if self._config.memory.vector_enabled:
            vector_results = self._vector_store.search_similar(
                query, user.user_id, limit
            )
            results.extend(vector_results)
        
        markdown_results = self._markdown_store.search_entries(query, user_id)
        for entry in markdown_results[:limit]:
            results.append({
                "content": entry.content,
                "metadata": {
                    "timestamp": entry.timestamp.isoformat(),
                    "tags": ",".join(entry.tags)
                }
            })
        
        return results[:limit]
    
    def get_recent_memories(self, user: User, days: int = 7) -> List[MemoryEntry]:
        """获取用户最近记忆"""
        user_id = user.user_id if user.level == UserLevel.OWNER else f"user_{user.user_id}"
        return self._markdown_store.get_recent_entries(user_id, days)
    
    def get_memory_context(
        self, 
        user: User, 
        current_message: str,
        is_group: bool = False
    ) -> str:
        """
        获取记忆上下文（不包含 persona，persona 在 processor 中单独加载）
        
        参考 OpenClaw 的记忆加载机制：
        1. MEMORY.md 已在 persona 中加载（仅私聊）
        2. 每日记忆通过混合检索按需召回
        3. 相关记忆通过 RAG 检索
        
        记忆按用户分组：
        - 主人的记忆：memory/owner/
        - 其他用户：memory/users/{user_id}/
        
        Args:
            user: 用户
            current_message: 当前消息
            is_group: 是否群聊
        
        Returns:
            记忆上下文字符串
        """
        if is_group:
            return ""
        
        parts = []
        
        user_id = user.user_id if user.level == UserLevel.OWNER else f"user_{user.user_id}"
        
        today_memories = self._markdown_store.get_entries(user_id)
        if today_memories:
            today_text = "\n".join([e.to_markdown() for e in today_memories[:5]])
            parts.append(f"# 今日记忆\n\n{today_text}")
        
        if self._config.memory.vector_enabled:
            hybrid_results = self._hybrid_search.hybrid_search(
                current_message, 
                limit=5
            )
            if hybrid_results:
                relevant_text = "\n".join([
                    f"- [{r.source}] {r.content[:200]}" 
                    for r in hybrid_results[:3]
                ])
                parts.append(f"# 相关记忆\n\n{relevant_text}")
        
        return "\n\n---\n\n".join(parts)
    
    def get_context_for_llm(self, user: User, current_message: str, is_group: bool = False) -> str:
        """
        获取用于 LLM 的记忆上下文
        
        注意：此方法已重构，persona 在 processor 中单独加载
        此方法仅返回记忆相关内容
        """
        return self.get_memory_context(user, current_message, is_group)
    
    def add_daily_memory(
        self, 
        content: str, 
        tags: List[str] = None,
        importance: int = 1
    ):
        """添加每日记忆"""
        return self._daily_memory.add_entry(content, tags, importance)
    
    def get_today_memories(self) -> List:
        """获取今日记忆"""
        return self._daily_memory.get_today_memories()
    
    def flush_memory(self, context_summary: str, key_points: List[str] = None):
        """
        记忆刷新 - 当上下文接近限制时自动提取关键信息
        
        参考 OpenClaw 的 memory flush 机制
        """
        self._daily_memory.flush_context_to_memory(context_summary, key_points)
    
    def analyze_semantic(self, text: str) -> Dict:
        """
        语义分析 - 意图识别 + 情感分析 + 实体提取
        
        返回完整的语义分析结果
        """
        analysis = self._semantic_analyzer.analyze(text)
        return analysis.to_dict()
    
    def quick_analyze(self, text: str) -> Dict:
        """快速语义分析 - 仅返回关键信息"""
        return self._semantic_analyzer.quick_analyze(text)
    
    def add_memory_with_analysis(
        self,
        user: User,
        content: str,
        auto_analyze: bool = True
    ) -> Dict:
        """
        添加记忆并自动进行语义分析
        
        整合流程：
        1. 语义分析（意图、情感、实体）
        2. 存储到每日记忆
        3. 存储到向量数据库
        4. 存储到知识图谱
        """
        analysis = None
        if auto_analyze:
            analysis = self._semantic_analyzer.analyze(content)
        
        self._markdown_store.add_entry(content)
        
        if self._config.memory.vector_enabled:
            entry = MemoryEntry(
                entry_id=str(uuid.uuid4()),
                content=content,
                timestamp=datetime.now(),
                importance=analysis.importance if analysis else 0.5
            )
            self._vector_store.add_memory(entry, user.user_id)
        
        if analysis and self._config.memory.graph_enabled:
            self._graphiti_store.add_episode(
                content=content,
                emotion=analysis.emotion.primary.value if analysis.emotion else None,
                intent=analysis.intent.intent.value if analysis.intent else None,
                importance=analysis.importance,
                entities=[e.to_dict() for e in analysis.entities],
                relations=analysis.relations
            )
        
        return {
            "content": content,
            "analysis": analysis.to_dict() if analysis else None
        }
    
    def search_with_graph(
        self,
        query: str,
        user: User,
        include_graph: bool = True,
        limit: int = 5
    ) -> Dict:
        """
        混合检索 + 知识图谱查询
        
        返回：
        - 向量检索结果
        - BM25 检索结果
        - 知识图谱相关实体
        """
        hybrid_results = self._hybrid_search.hybrid_search(query, limit=limit)
        
        graph_results = []
        if include_graph and self._config.memory.graph_enabled:
            analysis = self._semantic_analyzer.quick_analyze(query)
            entities = self._semantic_analyzer.entity_extractor.extract(query)
            
            for entity in entities[:3]:
                timeline = self._graphiti_store.get_entity_timeline(entity.text)
                relations = self._graphiti_store.get_entity_relations(entity.text)
                
                if timeline or relations:
                    graph_results.append({
                        "entity": entity.text,
                        "timeline": timeline[:3],
                        "relations": relations[:5]
                    })
        
        return {
            "memories": [r.to_dict() for r in hybrid_results],
            "graph": graph_results
        }
    
    def analyze_multimodal_emotion(
        self,
        text: str = None,
        audio_path: str = None,
        image_path: str = None
    ) -> Dict:
        """
        多模态情感分析
        
        支持文本、语音、图像的综合情感识别
        """
        result = self._emotion_fusion.analyze(
            text=text,
            audio_path=audio_path,
            image_path=image_path
        )
        return result.to_dict()
    
    def get_entity_memory(self, entity_name: str) -> Dict:
        """
        获取实体的完整记忆
        
        包括：
        - 时间线
        - 关系网络
        - 相关记忆片段
        """
        timeline = self._graphiti_store.get_entity_timeline(entity_name)
        relations = self._graphiti_store.get_entity_relations(entity_name)
        episodes = self._graphiti_store.search_episodes(entity_name=entity_name, limit=10)
        
        return {
            "entity": entity_name,
            "timeline": timeline,
            "relations": relations,
            "episodes": [e.to_dict() for e in episodes]
        }
    
    def apply_memory_decay(self, decay_factor: float = 0.95):
        """
        应用记忆衰减
        
        旧记忆的权重会逐渐降低
        """
        self._graphiti_store.apply_memory_decay(decay_factor)
    
    def get_memory_stats(self) -> Dict:
        """获取记忆系统统计信息"""
        return {
            "daily_memory": self._daily_memory.get_memory_stats(),
            "graph": self._graphiti_store.get_stats(),
            "vector_enabled": self._config.memory.vector_enabled,
            "graph_enabled": self._config.memory.graph_enabled,
            "modality_plugins": self._modality_system.get_plugin_info()
        }
    
    def register_modality(self, plugin, weight: float = None) -> bool:
        """
        注册新的模态插件
        
        Args:
            plugin: ModalityPlugin 实例
            weight: 权重（可选）
        
        Returns:
            是否注册成功
        """
        return self._modality_system.register_plugin(plugin, weight)
    
    def unregister_modality(self, modality_id: str) -> bool:
        """
        注销模态插件
        
        Args:
            modality_id: 模态ID
        
        Returns:
            是否注销成功
        """
        return self._modality_system.unregister_plugin(modality_id)
    
    def set_modality_weight(self, modality_id: str, weight: float):
        """设置模态权重"""
        self._modality_system.set_weight(modality_id, weight)
    
    def get_modality_info(self, modality_id: str = None) -> Dict:
        """获取模态信息"""
        return self._modality_system.get_plugin_info(modality_id)
    
    async def analyze_multimodal(
        self,
        input_data: Dict[str, Any],
        modalities: List[str] = None,
        fusion_strategy: str = None
    ):
        """
        多模态分析（异步版本）
        
        Args:
            input_data: 输入数据（可包含 text, audio_path, image_path 等）
            modalities: 指定使用的模态
            fusion_strategy: 融合策略
        
        Returns:
            FusedResult 融合结果
        """
        return await self._modality_system.analyze(input_data, modalities, fusion_strategy)
    
    def analyze_multimodal_sync(
        self,
        input_data: Dict[str, Any],
        modalities: List[str] = None,
        fusion_strategy: str = None
    ) -> Dict:
        """
        多模态分析（同步版本）
        
        Args:
            input_data: 输入数据
            modalities: 指定使用的模态
            fusion_strategy: 融合策略
        
        Returns:
            融合结果字典
        """
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._modality_system.analyze(input_data, modalities, fusion_strategy)
                    )
                    result = future.result(timeout=5)
            else:
                result = loop.run_until_complete(
                    self._modality_system.analyze(input_data, modalities, fusion_strategy)
                )
            return result.to_dict()
        except Exception as e:
            return {
                "error": str(e),
                "primary_data": {},
                "modality_results": []
            }
    
    def add_fact_to_graph(self, user: User, subject: str, relation: str, obj: str):
        """添加事实到知识图谱"""
        if self._config.memory.graph_enabled:
            self._graph_store.add_fact(
                user.user_id, subject, relation, obj, datetime.now()
            )
    
    def query_facts_from_graph(self, user: User, entity: str = None) -> List[Dict]:
        """从知识图谱查询事实"""
        if self._config.memory.graph_enabled:
            return self._graph_store.query_facts(user.user_id, entity)
        return []
    
    def migrate_from_openclaw(self, openclaw_dir: str):
        """
        从 OpenClaw 迁移人设
        
        支持迁移所有 OpenClaw 核心文件：
        - SOUL.md, AGENTS.md, IDENTITY.md, USER.md
        - TOOLS.md, MEMORY.md, HEARTBEAT.md, BOOTSTRAP.md
        - memory/ 目录下的每日记忆文件
        """
        openclaw_path = Path(openclaw_dir)
        
        files_to_migrate = [
            "SOUL.md",
            "AGENTS.md", 
            "IDENTITY.md",
            "USER.md",
            "TOOLS.md",
            "MEMORY.md",
            "HEARTBEAT.md",
            "BOOTSTRAP.md"
        ]
        
        for filename in files_to_migrate:
            src = openclaw_path / filename
            if src.exists():
                content = src.read_text(encoding='utf-8')
                self._persona_loader.save_file(filename, content)
        
        memory_dir = openclaw_path / "memory"
        if memory_dir.exists():
            for md_file in memory_dir.glob("*.md"):
                dest = Path(self._config.memory.markdown_dir) / md_file.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(md_file.read_text(encoding='utf-8'), encoding='utf-8')
        
        sessions_dir = openclaw_path / "sessions"
        if sessions_dir.exists():
            dest_sessions = Path(self._config.data_dir) / "sessions"
            dest_sessions.mkdir(parents=True, exist_ok=True)
            for session_file in sessions_dir.glob("*.md"):
                dest = dest_sessions / session_file.name
                dest.write_text(session_file.read_text(encoding='utf-8'), encoding='utf-8')
    
    def close(self):
        """关闭资源"""
        self._graph_store.close()
        if hasattr(self, '_graphiti_store'):
            self._graphiti_store.close()
    
    @classmethod
    def get_instance(cls) -> "MemoryManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


import uuid
