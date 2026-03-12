"""
XiaoMengCore 记忆系统模块
"""

from .memory_manager import (
    MemoryManager,
    PersonaLoader,
    MarkdownMemoryStore,
    VectorStore,
    GraphStore
)
from .daily_memory import (
    DailyMemoryManager,
    DailyMemoryEntry
)
from .hybrid_search import (
    HybridMemorySearch,
    BM25Index,
    SearchResult,
    create_hybrid_search
)
from .semantic import (
    SemanticAnalyzer,
    IntentRecognizer,
    EmotionAnalyzer,
    EntityExtractor,
    ImportanceScorer,
    IntentType,
    EmotionType,
    SemanticAnalysis
)
from .deep_emotional import (
    DeepEmotionalMemory,
    DeepMemory,
    UserEmotionalProfile
)

from .graphiti import (
    GraphitiMemoryStore,
    GraphNode,
    GraphRelation,
    MemoryEpisode
)
from .multimodal import (
    MultimodalEmotionFusion,
    TextEmotionAnalyzer,
    VoiceEmotionAnalyzer,
    FaceEmotionAnalyzer,
    FusedEmotionResult,
    create_emotion_fusion
)
from .modality_plugin import (
    ModalityPluginSystem,
    ModalityPlugin,
    ModalityResult,
    FusedResult,
    FusionStrategy,
    WeightedFusionStrategy,
    AttentionFusionStrategy,
    VotingFusionStrategy,
    ModalityStatus,
    create_plugin_system
)
from .builtin_plugins import (
    TextModalityPlugin,
    VoiceModalityPlugin,
    FaceModalityPlugin,
    ImageModalityPlugin,
    SensorModalityPlugin,
    create_default_plugins
)

__all__ = [
    "MemoryManager",
    "PersonaLoader",
    "MarkdownMemoryStore",
    "VectorStore",
    "GraphStore",
    "DailyMemoryManager",
    "DailyMemoryEntry",
    "HybridMemorySearch",
    "BM25Index",
    "SearchResult",
    "create_hybrid_search",
    "SemanticAnalyzer",
    "IntentRecognizer",
    "EmotionAnalyzer",
    "EntityExtractor",
    "ImportanceScorer",
    "IntentType",
    "EmotionType",
    "SemanticAnalysis",
    "DeepEmotionalMemory",
    "DeepMemory",
    "UserEmotionalProfile",
    "GraphitiMemoryStore",
    "GraphNode",
    "GraphRelation",
    "MemoryEpisode",
    "MultimodalEmotionFusion",
    "TextEmotionAnalyzer",
    "VoiceEmotionAnalyzer",
    "FaceEmotionAnalyzer",
    "FusedEmotionResult",
    "create_emotion_fusion",
    "ModalityPluginSystem",
    "ModalityPlugin",
    "ModalityResult",
    "FusedResult",
    "FusionStrategy",
    "WeightedFusionStrategy",
    "AttentionFusionStrategy",
    "VotingFusionStrategy",
    "ModalityStatus",
    "create_plugin_system",
    "TextModalityPlugin",
    "VoiceModalityPlugin",
    "FaceModalityPlugin",
    "ImageModalityPlugin",
    "SensorModalityPlugin",
    "create_default_plugins"
]
