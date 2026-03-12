"""
Graphiti 时序知识图谱集成
完全按照完整实现指南实现

特性：
1. 时序记忆 - 带时间戳的关系记忆
2. 关系演化追踪 - 追踪实体关系的变化
3. 记忆衰减 - 旧记忆权重降低
4. 上下文感知检索

参考：完整实现指南/进阶阶段/阶段02_高级记忆系统.md
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json
import asyncio
import math


@dataclass
class GraphNode:
    """图谱节点"""
    id: str
    name: str
    type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class GraphRelation:
    """图谱关系"""
    id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    weight: float = 1.0
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "properties": self.properties,
            "timestamp": self.timestamp.isoformat(),
            "weight": self.weight
        }


@dataclass
class MemoryEpisode:
    """记忆片段 - 时序记忆的基本单元"""
    id: str
    content: str
    timestamp: datetime
    emotion: Optional[str] = None
    intent: Optional[str] = None
    importance: float = 0.5
    entities: List[str] = field(default_factory=list)
    relations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "emotion": self.emotion,
            "intent": self.intent,
            "importance": self.importance,
            "entities": self.entities,
            "relations": self.relations,
            "metadata": self.metadata
        }


class GraphitiMemoryStore:
    """
    Graphiti 时序知识图谱存储
    
    支持两种后端：
    1. Neo4j（生产环境推荐）
    2. 本地 JSON 存储（开发/测试）
    """
    
    def __init__(
        self,
        uri: str = None,
        user: str = "neo4j",
        password: str = None,
        local_path: str = None,
        use_neo4j: bool = False
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.use_neo4j = use_neo4j
        self._driver = None
        
        if local_path:
            self._local_path = Path(local_path)
        else:
            self._local_path = Path.home() / ".xiaomeng" / "graph"
        
        self._local_path.mkdir(parents=True, exist_ok=True)
        
        self._nodes: Dict[str, GraphNode] = {}
        self._relations: Dict[str, GraphRelation] = {}
        self._episodes: Dict[str, MemoryEpisode] = {}
        
        self._load_local()
        
        if use_neo4j and uri:
            self._init_neo4j()
    
    def _init_neo4j(self):
        """初始化 Neo4j 连接"""
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
        except ImportError:
            self.use_neo4j = False
    
    def _load_local(self):
        """加载本地存储"""
        nodes_file = self._local_path / "nodes.json"
        relations_file = self._local_path / "relations.json"
        episodes_file = self._local_path / "episodes.json"
        
        if nodes_file.exists():
            try:
                data = json.loads(nodes_file.read_text(encoding='utf-8'))
                for item in data:
                    node = GraphNode(
                        id=item["id"],
                        name=item["name"],
                        type=item["type"],
                        properties=item.get("properties", {}),
                        created_at=datetime.fromisoformat(item["created_at"]),
                        updated_at=datetime.fromisoformat(item["updated_at"])
                    )
                    self._nodes[node.id] = node
            except Exception:
                pass
        
        if relations_file.exists():
            try:
                data = json.loads(relations_file.read_text(encoding='utf-8'))
                for item in data:
                    relation = GraphRelation(
                        id=item["id"],
                        source_id=item["source_id"],
                        target_id=item["target_id"],
                        relation_type=item["relation_type"],
                        properties=item.get("properties", {}),
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                        weight=item.get("weight", 1.0)
                    )
                    self._relations[relation.id] = relation
            except Exception:
                pass
        
        if episodes_file.exists():
            try:
                data = json.loads(episodes_file.read_text(encoding='utf-8'))
                for item in data:
                    episode = MemoryEpisode(
                        id=item["id"],
                        content=item["content"],
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                        emotion=item.get("emotion"),
                        intent=item.get("intent"),
                        importance=item.get("importance", 0.5),
                        entities=item.get("entities", []),
                        relations=item.get("relations", []),
                        metadata=item.get("metadata", {})
                    )
                    self._episodes[episode.id] = episode
            except Exception:
                pass
    
    def _save_local(self):
        """保存到本地"""
        nodes_file = self._local_path / "nodes.json"
        relations_file = self._local_path / "relations.json"
        episodes_file = self._local_path / "episodes.json"
        
        nodes_file.write_text(
            json.dumps([n.to_dict() for n in self._nodes.values()], ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        
        relations_file.write_text(
            json.dumps([r.to_dict() for r in self._relations.values()], ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        
        episodes_file.write_text(
            json.dumps([e.to_dict() for e in self._episodes.values()], ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
    
    def add_node(
        self,
        name: str,
        node_type: str,
        properties: Dict = None
    ) -> GraphNode:
        """添加节点"""
        import uuid
        
        node_id = f"{node_type}_{name}_{uuid.uuid4().hex[:8]}"
        
        if node_id in self._nodes:
            node = self._nodes[node_id]
            node.updated_at = datetime.now()
            if properties:
                node.properties.update(properties)
            return node
        
        node = GraphNode(
            id=node_id,
            name=name,
            type=node_type,
            properties=properties or {}
        )
        
        self._nodes[node_id] = node
        self._save_local()
        
        if self.use_neo4j and self._driver:
            self._add_node_to_neo4j(node)
        
        return node
    
    def add_relation(
        self,
        source_name: str,
        relation_type: str,
        target_name: str,
        properties: Dict = None
    ) -> GraphRelation:
        """添加关系"""
        import uuid
        
        source_node = self.add_node(source_name, "entity")
        target_node = self.add_node(target_name, "entity")
        
        relation_id = f"rel_{uuid.uuid4().hex[:8]}"
        
        relation = GraphRelation(
            id=relation_id,
            source_id=source_node.id,
            target_id=target_node.id,
            relation_type=relation_type,
            properties=properties or {}
        )
        
        self._relations[relation_id] = relation
        self._save_local()
        
        if self.use_neo4j and self._driver:
            self._add_relation_to_neo4j(relation)
        
        return relation
    
    def add_episode(
        self,
        content: str,
        emotion: str = None,
        intent: str = None,
        importance: float = 0.5,
        entities: List[Dict] = None,
        relations: List[Dict] = None,
        timestamp: datetime = None
    ) -> MemoryEpisode:
        """添加记忆片段"""
        import uuid
        
        episode_id = f"ep_{uuid.uuid4().hex[:8]}"
        timestamp = timestamp or datetime.now()
        
        entity_ids = []
        if entities:
            for entity in entities:
                node = self.add_node(
                    name=entity["text"],
                    node_type=entity["type"]
                )
                entity_ids.append(node.id)
        
        relation_ids = []
        if relations:
            for rel in relations:
                relation = self.add_relation(
                    source_name=rel["subject"],
                    relation_type=rel["relation"],
                    target_name=rel["object"]
                )
                relation_ids.append(relation.id)
        
        episode = MemoryEpisode(
            id=episode_id,
            content=content,
            timestamp=timestamp,
            emotion=emotion,
            intent=intent,
            importance=importance,
            entities=entity_ids,
            relations=relation_ids
        )
        
        self._episodes[episode_id] = episode
        self._save_local()
        
        return episode
    
    def search_episodes(
        self,
        query: str = None,
        entity_name: str = None,
        emotion: str = None,
        time_range: Tuple[datetime, datetime] = None,
        limit: int = 10
    ) -> List[MemoryEpisode]:
        """搜索记忆片段"""
        results = list(self._episodes.values())
        
        if query:
            query_lower = query.lower()
            results = [e for e in results if query_lower in e.content.lower()]
        
        if entity_name:
            entity_ids = [
                n.id for n in self._nodes.values()
                if entity_name.lower() in n.name.lower()
            ]
            results = [e for e in results if any(eid in e.entities for eid in entity_ids)]
        
        if emotion:
            results = [e for e in results if e.emotion == emotion]
        
        if time_range:
            start, end = time_range
            results = [e for e in results if start <= e.timestamp <= end]
        
        results.sort(key=lambda e: (e.importance, e.timestamp), reverse=True)
        
        return results[:limit]
    
    def get_entity_timeline(self, entity_name: str) -> List[Dict]:
        """获取实体的时间线"""
        entity_ids = [
            n.id for n in self._nodes.values()
            if entity_name.lower() in n.name.lower()
        ]
        
        episodes = [
            e for e in self._episodes.values()
            if any(eid in e.entities for eid in entity_ids)
        ]
        
        episodes.sort(key=lambda e: e.timestamp)
        
        return [
            {
                "content": e.content,
                "timestamp": e.timestamp.isoformat(),
                "emotion": e.emotion,
                "importance": e.importance
            }
            for e in episodes
        ]
    
    def get_entity_relations(self, entity_name: str) -> List[Dict]:
        """获取实体的所有关系"""
        entity_ids = [
            n.id for n in self._nodes.values()
            if entity_name.lower() in n.name.lower()
        ]
        
        relations = []
        for rel in self._relations.values():
            if rel.source_id in entity_ids or rel.target_id in entity_ids:
                source_node = self._nodes.get(rel.source_id)
                target_node = self._nodes.get(rel.target_id)
                
                if source_node and target_node:
                    relations.append({
                        "subject": source_node.name,
                        "relation": rel.relation_type,
                        "object": target_node.name,
                        "timestamp": rel.timestamp.isoformat(),
                        "weight": rel.weight
                    })
        
        return relations
    
    def apply_memory_decay(self, decay_factor: float = 0.95):
        """
        应用记忆衰减
        
        旧记忆的权重会逐渐降低
        """
        now = datetime.now()
        
        for episode in self._episodes.values():
            age_days = (now - episode.timestamp).days
            decay = math.pow(decay_factor, age_days)
            episode.importance *= decay
        
        for relation in self._relations.values():
            age_days = (now - relation.timestamp).days
            decay = math.pow(decay_factor, age_days)
            relation.weight *= decay
        
        self._save_local()
    
    def get_important_entities(self, threshold: float = 0.5) -> List[Dict]:
        """获取重要实体"""
        entity_importance = {}
        
        for episode in self._episodes.values():
            for entity_id in episode.entities:
                if entity_id not in entity_importance:
                    entity_importance[entity_id] = 0
                entity_importance[entity_id] += episode.importance
        
        important = []
        for entity_id, importance in entity_importance.items():
            if importance >= threshold:
                node = self._nodes.get(entity_id)
                if node:
                    important.append({
                        "name": node.name,
                        "type": node.type,
                        "importance": importance
                    })
        
        important.sort(key=lambda x: x["importance"], reverse=True)
        return important
    
    def _add_node_to_neo4j(self, node: GraphNode):
        """添加节点到 Neo4j"""
        if not self._driver:
            return
        
        with self._driver.session() as session:
            session.run(
                f"""
                MERGE (n:{node.type.upper()} {{id: $id}})
                SET n.name = $name,
                    n.properties = $properties,
                    n.updated_at = $updated_at
                """,
                id=node.id,
                name=node.name,
                properties=node.properties,
                updated_at=node.updated_at.isoformat()
            )
    
    def _add_relation_to_neo4j(self, relation: GraphRelation):
        """添加关系到 Neo4j"""
        if not self._driver:
            return
        
        with self._driver.session() as session:
            session.run(
                f"""
                MATCH (s {{id: $source_id}})
                MATCH (t {{id: $target_id}})
                MERGE (s)-[r:{relation.relation_type.upper()}]->(t)
                SET r.timestamp = $timestamp,
                    r.weight = $weight,
                    r.properties = $properties
                """,
                source_id=relation.source_id,
                target_id=relation.target_id,
                timestamp=relation.timestamp.isoformat(),
                weight=relation.weight,
                properties=relation.properties
            )
    
    def close(self):
        """关闭连接"""
        if self._driver:
            self._driver.close()
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_nodes": len(self._nodes),
            "total_relations": len(self._relations),
            "total_episodes": len(self._episodes),
            "node_types": list(set(n.type for n in self._nodes.values())),
            "relation_types": list(set(r.relation_type for r in self._relations.values()))
        }
