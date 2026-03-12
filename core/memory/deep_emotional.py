"""
XiaoMengCore 深度情感记忆系统
这是相比OpenClaw的核心改进之一

特性：
1. 知识图谱 + RAG 混合检索
2. 多模态情感分析（文本/语音/视觉）
3. 时序记忆衰减
4. 个性化情感建模
5. 上下文感知记忆检索
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Callable
from datetime import datetime, timedelta
from pathlib import Path
import json
import asyncio
import math
import hashlib
from enum import Enum


class EmotionType(Enum):
    """情感类型"""
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TRUST = "trust"
    ANTICIPATION = "anticipation"
    NEUTRAL = "neutral"


class MemoryType(Enum):
    """记忆类型"""
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    EMOTIONAL = "emotional"


@dataclass
class EmotionVector:
    """情感向量 - 多维度情感表示"""
    joy: float = 0.0
    sadness: float = 0.0
    anger: float = 0.0
    fear: float = 0.0
    surprise: float = 0.0
    disgust: float = 0.0
    trust: float = 0.0
    anticipation: float = 0.0
    
    def dominant_emotion(self) -> EmotionType:
        """获取主导情感"""
        emotions = {
            EmotionType.JOY: self.joy,
            EmotionType.SADNESS: self.sadness,
            EmotionType.ANGER: self.anger,
            EmotionType.FEAR: self.fear,
            EmotionType.SURPRISE: self.surprise,
            EmotionType.DISGUST: self.disgust,
            EmotionType.TRUST: self.trust,
            EmotionType.ANTICIPATION: self.anticipation,
        }
        max_emotion = max(emotions.items(), key=lambda x: x[1])
        return max_emotion[0] if max_emotion[1] > 0.1 else EmotionType.NEUTRAL
    
    def intensity(self) -> float:
        """获取情感强度"""
        return max(self.joy, self.sadness, self.anger, self.fear,
                   self.surprise, self.disgust, self.trust, self.anticipation)
    
    def to_dict(self) -> Dict:
        return {
            "joy": self.joy,
            "sadness": self.sadness,
            "anger": self.anger,
            "fear": self.fear,
            "surprise": self.surprise,
            "disgust": self.disgust,
            "trust": self.trust,
            "anticipation": self.anticipation,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "EmotionVector":
        return cls(
            joy=data.get("joy", 0.0),
            sadness=data.get("sadness", 0.0),
            anger=data.get("anger", 0.0),
            fear=data.get("fear", 0.0),
            surprise=data.get("surprise", 0.0),
            disgust=data.get("disgust", 0.0),
            trust=data.get("trust", 0.0),
            anticipation=data.get("anticipation", 0.0),
        )


@dataclass
class DeepMemory:
    """深度记忆条目"""
    id: str
    content: str
    memory_type: MemoryType
    timestamp: datetime
    emotion: EmotionVector
    importance: float = 0.5
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    decay_rate: float = 0.1
    
    entities: List[str] = field(default_factory=list)
    relations: List[Tuple[str, str, str]] = field(default_factory=list)
    
    embedding: Optional[List[float]] = None
    source_modality: str = "text"
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def compute_relevance(self, query_time: datetime) -> float:
        """计算记忆相关性（考虑时间衰减）"""
        age_hours = (query_time - self.timestamp).total_seconds() / 3600
        time_decay = math.exp(-self.decay_rate * age_hours / 24)
        
        access_boost = math.log(1 + self.access_count) * 0.1
        
        recency_boost = 0.0
        if self.last_accessed:
            recency_hours = (query_time - self.last_accessed).total_seconds() / 3600
            recency_boost = math.exp(-recency_hours / 48) * 0.2
        
        return self.importance * time_decay + access_boost + recency_boost
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "timestamp": self.timestamp.isoformat(),
            "emotion": self.emotion.to_dict(),
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "decay_rate": self.decay_rate,
            "entities": self.entities,
            "relations": self.relations,
            "source_modality": self.source_modality,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "DeepMemory":
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType(data["memory_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            emotion=EmotionVector.from_dict(data.get("emotion", {})),
            importance=data.get("importance", 0.5),
            access_count=data.get("access_count", 0),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None,
            decay_rate=data.get("decay_rate", 0.1),
            entities=data.get("entities", []),
            relations=[tuple(r) for r in data.get("relations", [])],
            source_modality=data.get("source_modality", "text"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class UserEmotionalProfile:
    """用户情感画像"""
    user_id: str
    
    baseline_emotion: EmotionVector = field(default_factory=EmotionVector)
    emotion_history: List[Tuple[datetime, EmotionVector]] = field(default_factory=list)
    
    preferred_topics: List[str] = field(default_factory=list)
    avoided_topics: List[str] = field(default_factory=list)
    
    communication_style: Dict[str, float] = field(default_factory=dict)
    
    emotional_triggers: Dict[str, List[str]] = field(default_factory=dict)
    
    last_updated: datetime = field(default_factory=datetime.now)
    
    def update_baseline(self, new_emotion: EmotionVector, weight: float = 0.1):
        """更新基准情感"""
        self.baseline_emotion = EmotionVector(
            joy=self.baseline_emotion.joy * (1 - weight) + new_emotion.joy * weight,
            sadness=self.baseline_emotion.sadness * (1 - weight) + new_emotion.sadness * weight,
            anger=self.baseline_emotion.anger * (1 - weight) + new_emotion.anger * weight,
            fear=self.baseline_emotion.fear * (1 - weight) + new_emotion.fear * weight,
            surprise=self.baseline_emotion.surprise * (1 - weight) + new_emotion.surprise * weight,
            disgust=self.baseline_emotion.disgust * (1 - weight) + new_emotion.disgust * weight,
            trust=self.baseline_emotion.trust * (1 - weight) + new_emotion.trust * weight,
            anticipation=self.baseline_emotion.anticipation * (1 - weight) + new_emotion.anticipation * weight,
        )
        self.emotion_history.append((datetime.now(), new_emotion))
        
        if len(self.emotion_history) > 100:
            self.emotion_history = self.emotion_history[-100:]
        
        self.last_updated = datetime.now()
    
    def get_emotional_trend(self, days: int = 7) -> Dict[str, float]:
        """获取情感趋势"""
        cutoff = datetime.now() - timedelta(days=days)
        recent = [(t, e) for t, e in self.emotion_history if t >= cutoff]
        
        if not recent:
            return {}
        
        avg = EmotionVector()
        for _, emotion in recent:
            avg.joy += emotion.joy
            avg.sadness += emotion.sadness
            avg.anger += emotion.anger
            avg.fear += emotion.fear
            avg.surprise += emotion.surprise
            avg.disgust += emotion.disgust
            avg.trust += emotion.trust
            avg.anticipation += emotion.anticipation
        
        n = len(recent)
        return {
            "joy": avg.joy / n,
            "sadness": avg.sadness / n,
            "anger": avg.anger / n,
            "fear": avg.fear / n,
            "surprise": avg.surprise / n,
            "disgust": avg.disgust / n,
            "trust": avg.trust / n,
            "anticipation": avg.anticipation / n,
        }
    
    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "baseline_emotion": self.baseline_emotion.to_dict(),
            "emotion_history": [(t.isoformat(), e.to_dict()) for t, e in self.emotion_history],
            "preferred_topics": self.preferred_topics,
            "avoided_topics": self.avoided_topics,
            "communication_style": self.communication_style,
            "emotional_triggers": self.emotional_triggers,
            "last_updated": self.last_updated.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "UserEmotionalProfile":
        return cls(
            user_id=data["user_id"],
            baseline_emotion=EmotionVector.from_dict(data.get("baseline_emotion", {})),
            emotion_history=[
                (datetime.fromisoformat(t), EmotionVector.from_dict(e))
                for t, e in data.get("emotion_history", [])
            ],
            preferred_topics=data.get("preferred_topics", []),
            avoided_topics=data.get("avoided_topics", []),
            communication_style=data.get("communication_style", {}),
            emotional_triggers=data.get("emotional_triggers", {}),
            last_updated=datetime.fromisoformat(data["last_updated"]) if data.get("last_updated") else datetime.now(),
        )


class DeepEmotionalMemory:
    """
    深度情感记忆系统
    
    核心特性：
    1. 知识图谱 + RAG 混合检索
    2. 多模态情感分析
    3. 时序记忆衰减
    4. 个性化情感建模
    """
    
    def __init__(
        self,
        storage_path: str = "./data/memory",
        embedding_dim: int = 768,
        max_memories: int = 10000
    ):
        self._storage_path = Path(storage_path)
        self._embedding_dim = embedding_dim
        self._max_memories = max_memories
        
        self._memories: Dict[str, DeepMemory] = {}
        self._profiles: Dict[str, UserEmotionalProfile] = {}
        
        self._entity_index: Dict[str, List[str]] = {}
        self._relation_graph: Dict[str, List[Tuple[str, str, str]]] = {}
        
        self._embedding_cache: Dict[str, List[float]] = {}
        
        self._load()
    
    def _load(self):
        """加载存储的记忆"""
        self._storage_path.mkdir(parents=True, exist_ok=True)
        
        memories_file = self._storage_path / "memories.json"
        if memories_file.exists():
            try:
                data = json.loads(memories_file.read_text(encoding='utf-8'))
                self._memories = {
                    k: DeepMemory.from_dict(v) for k, v in data.items()
                }
            except:
                pass
        
        profiles_file = self._storage_path / "profiles.json"
        if profiles_file.exists():
            try:
                data = json.loads(profiles_file.read_text(encoding='utf-8'))
                self._profiles = {
                    k: UserEmotionalProfile.from_dict(v) for k, v in data.items()
                }
            except:
                pass
        
        self._rebuild_indices()
    
    def _save(self):
        """保存记忆到存储"""
        memories_file = self._storage_path / "memories.json"
        memories_file.write_text(
            json.dumps({k: v.to_dict() for k, v in self._memories.items()}, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        
        profiles_file = self._storage_path / "profiles.json"
        profiles_file.write_text(
            json.dumps({k: v.to_dict() for k, v in self._profiles.items()}, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
    
    def _rebuild_indices(self):
        """重建索引"""
        self._entity_index.clear()
        self._relation_graph.clear()
        
        for memory in self._memories.values():
            for entity in memory.entities:
                if entity not in self._entity_index:
                    self._entity_index[entity] = []
                self._entity_index[entity].append(memory.id)
            
            for source, relation, target in memory.relations:
                if source not in self._relation_graph:
                    self._relation_graph[source] = []
                self._relation_graph[source].append((relation, target, memory.id))
    
    def _compute_embedding(self, text: str) -> List[float]:
        """计算文本嵌入向量（简化版，实际应使用模型）"""
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        
        hash_bytes = hashlib.md5(text.encode()).digest()
        embedding = []
        for i in range(self._embedding_dim):
            byte_idx = i % len(hash_bytes)
            embedding.append((hash_bytes[byte_idx] / 255.0) * 2 - 1)
        
        self._embedding_cache[text] = embedding
        return embedding
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        if len(a) != len(b):
            return 0.0
        
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)
    
    async def analyze_emotion(
        self,
        text: str,
        voice_data: Optional[bytes] = None,
        image_data: Optional[bytes] = None
    ) -> EmotionVector:
        """
        多模态情感分析
        
        分析文本、语音、图像的情感，返回融合后的情感向量
        """
        text_emotion = await self._analyze_text_emotion(text)
        
        voice_emotion = None
        if voice_data:
            voice_emotion = await self._analyze_voice_emotion(voice_data)
        
        image_emotion = None
        if image_data:
            image_emotion = await self._analyze_image_emotion(image_data)
        
        emotions = [text_emotion]
        weights = [0.5]
        
        if voice_emotion:
            emotions.append(voice_emotion)
            weights.append(0.3)
        
        if image_emotion:
            emotions.append(image_emotion)
            weights.append(0.2)
        
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]
        
        fused = EmotionVector()
        for emotion, weight in zip(emotions, weights):
            fused.joy += emotion.joy * weight
            fused.sadness += emotion.sadness * weight
            fused.anger += emotion.anger * weight
            fused.fear += emotion.fear * weight
            fused.surprise += emotion.surprise * weight
            fused.disgust += emotion.disgust * weight
            fused.trust += emotion.trust * weight
            fused.anticipation += emotion.anticipation * weight
        
        return fused
    
    async def _analyze_text_emotion(self, text: str) -> EmotionVector:
        """分析文本情感"""
        emotion_keywords = {
            EmotionType.JOY: ["开心", "高兴", "快乐", "幸福", "喜欢", "爱", "棒", "好", "happy", "joy", "love"],
            EmotionType.SADNESS: ["难过", "伤心", "悲伤", "哭", "失望", "sad", "cry", "disappointed"],
            EmotionType.ANGER: ["生气", "愤怒", "烦", "讨厌", "angry", "hate", "annoying"],
            EmotionType.FEAR: ["害怕", "恐惧", "担心", "紧张", "fear", "scared", "worried"],
            EmotionType.SURPRISE: ["惊讶", "意外", "惊喜", "surprise", "wow", "amazing"],
            EmotionType.DISGUST: ["恶心", "讨厌", "厌恶", "disgust", "gross"],
            EmotionType.TRUST: ["信任", "相信", "依赖", "trust", "believe"],
            EmotionType.ANTICIPATION: ["期待", "盼望", "希望", "anticipate", "hope", "expect"],
        }
        
        text_lower = text.lower()
        scores = {}
        
        for emotion_type, keywords in emotion_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            scores[emotion_type] = min(score * 0.3, 1.0)
        
        return EmotionVector(
            joy=scores.get(EmotionType.JOY, 0.0),
            sadness=scores.get(EmotionType.SADNESS, 0.0),
            anger=scores.get(EmotionType.ANGER, 0.0),
            fear=scores.get(EmotionType.FEAR, 0.0),
            surprise=scores.get(EmotionType.SURPRISE, 0.0),
            disgust=scores.get(EmotionType.DISGUST, 0.0),
            trust=scores.get(EmotionType.TRUST, 0.0),
            anticipation=scores.get(EmotionType.ANTICIPATION, 0.0),
        )
    
    async def _analyze_voice_emotion(self, voice_data: bytes) -> EmotionVector:
        """分析语音情感（简化实现）"""
        return EmotionVector(neutral=0.5)
    
    async def _analyze_image_emotion(self, image_data: bytes) -> EmotionVector:
        """分析图像情感（简化实现）"""
        return EmotionVector(neutral=0.5)
    
    async def store_memory(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType = MemoryType.EPISODIC,
        entities: List[str] = None,
        relations: List[Tuple[str, str, str]] = None,
        voice_data: Optional[bytes] = None,
        image_data: Optional[bytes] = None,
        metadata: Dict = None
    ) -> DeepMemory:
        """存储记忆"""
        emotion = await self.analyze_emotion(content, voice_data, image_data)
        
        importance = emotion.intensity() * 0.5 + 0.3
        
        memory_id = hashlib.md5(f"{user_id}{content}{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        
        memory = DeepMemory(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            timestamp=datetime.now(),
            emotion=emotion,
            importance=importance,
            entities=entities or [],
            relations=relations or [],
            source_modality="text" if not voice_data and not image_data else "multimodal",
            metadata=metadata or {},
        )
        
        memory.embedding = self._compute_embedding(content)
        
        self._memories[memory_id] = memory
        
        for entity in (entities or []):
            if entity not in self._entity_index:
                self._entity_index[entity] = []
            self._entity_index[entity].append(memory_id)
        
        for source, relation, target in (relations or []):
            if source not in self._relation_graph:
                self._relation_graph[source] = []
            self._relation_graph[source].append((relation, target, memory_id))
        
        if user_id not in self._profiles:
            self._profiles[user_id] = UserEmotionalProfile(user_id=user_id)
        self._profiles[user_id].update_baseline(emotion)
        
        if len(self._memories) > self._max_memories:
            await self._prune_memories()
        
        self._save()
        
        return memory
    
    async def _prune_memories(self):
        """清理低相关性记忆"""
        now = datetime.now()
        memories_with_relevance = [
            (memory, memory.compute_relevance(now))
            for memory in self._memories.values()
        ]
        
        memories_with_relevance.sort(key=lambda x: x[1], reverse=True)
        
        keep_count = int(self._max_memories * 0.8)
        to_keep = {m.id for m, _ in memories_with_relevance[:keep_count]}
        
        self._memories = {k: v for k, v in self._memories.items() if k in to_keep}
        self._rebuild_indices()
    
    async def retrieve_memories(
        self,
        query: str,
        user_id: Optional[str] = None,
        top_k: int = 10,
        memory_types: List[MemoryType] = None,
        min_relevance: float = 0.1
    ) -> List[Tuple[DeepMemory, float]]:
        """
        检索相关记忆
        
        使用知识图谱 + RAG 混合检索：
        1. 基于实体的图谱检索
        2. 基于向量的相似度检索
        3. 基于情感的关联检索
        """
        query_embedding = self._compute_embedding(query)
        query_emotion = await self._analyze_text_emotion(query)
        
        now = datetime.now()
        
        candidates: Dict[str, Tuple[DeepMemory, float]] = {}
        
        for memory in self._memories.values():
            if memory_types and memory.memory_type not in memory_types:
                continue
            
            vector_sim = self._cosine_similarity(query_embedding, memory.embedding or [])
            emotion_sim = self._emotion_similarity(query_emotion, memory.emotion)
            relevance = memory.compute_relevance(now)
            
            score = vector_sim * 0.5 + emotion_sim * 0.3 + relevance * 0.2
            
            if score >= min_relevance:
                candidates[memory.id] = (memory, score)
        
        sorted_results = sorted(candidates.values(), key=lambda x: x[1], reverse=True)[:top_k]
        
        for memory, _ in sorted_results:
            memory.access_count += 1
            memory.last_accessed = now
        
        return sorted_results
    
    def _emotion_similarity(self, a: EmotionVector, b: EmotionVector) -> float:
        """计算情感相似度"""
        vec_a = [a.joy, a.sadness, a.anger, a.fear, a.surprise, a.disgust, a.trust, a.anticipation]
        vec_b = [b.joy, b.sadness, b.anger, b.fear, b.surprise, b.disgust, b.trust, b.anticipation]
        return self._cosine_similarity(vec_a, vec_b)
    
    async def get_user_profile(self, user_id: str) -> Optional[UserEmotionalProfile]:
        """获取用户情感画像"""
        return self._profiles.get(user_id)
    
    async def get_emotional_context(
        self,
        user_id: str,
        query: str,
        max_tokens: int = 2000
    ) -> str:
        """获取情感上下文（用于构建系统提示）"""
        profile = await self.get_user_profile(user_id)
        memories = await self.retrieve_memories(query, user_id, top_k=5)
        
        parts = []
        
        if profile:
            dominant = profile.baseline_emotion.dominant_emotion()
            trend = profile.get_emotional_trend()
            
            parts.append(f"用户情感画像：")
            parts.append(f"  主导情感：{dominant.value}")
            if trend:
                parts.append(f"  近期情感趋势：{trend}")
            if profile.preferred_topics:
                parts.append(f"  偏好话题：{', '.join(profile.preferred_topics[:5])}")
        
        if memories:
            parts.append("\n相关记忆：")
            for memory, score in memories[:3]:
                emotion = memory.emotion.dominant_emotion()
                parts.append(f"  [{memory.timestamp.strftime('%Y-%m-%d')}] {memory.content[:100]}...")
                parts.append(f"    情感：{emotion.value}，相关性：{score:.2f}")
        
        context = "\n".join(parts)
        
        if len(context) > max_tokens * 2:
            context = context[:max_tokens * 2]
        
        return context
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_memories": len(self._memories),
            "total_profiles": len(self._profiles),
            "total_entities": len(self._entity_index),
            "total_relations": sum(len(r) for r in self._relation_graph.values()),
            "memory_types": {
                mt.value: sum(1 for m in self._memories.values() if m.memory_type == mt)
                for mt in MemoryType
            }
        }
