"""
多模态插件系统 - 可插拔、并行、低延迟

设计原则：
1. 插件化 - 每个模态是独立的插件，可随时添加/移除
2. 并行处理 - 使用 asyncio 并行执行多个模态分析
3. 统一接口 - 所有模态遵循相同的接口规范
4. 动态注册 - 运行时注册/注销模态
5. 可配置融合 - 支持多种融合策略

架构：
┌─────────────────────────────────────────────────────────────┐
│                    ModalityPluginSystem                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ TextMod │ │VoiceMod │ │FaceMod  │ │ ...Mod  │  插件层  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘          │
│       │           │           │           │                │
│       └───────────┴─────┬─────┴───────────┘                │
│                         │                                   │
│                         ▼                                   │
│              ┌─────────────────────┐                       │
│              │   ParallelExecutor  │  并行执行层           │
│              │   (asyncio.gather)  │                       │
│              └──────────┬──────────┘                       │
│                         │                                   │
│                         ▼                                   │
│              ┌─────────────────────┐                       │
│              │   FusionStrategy    │  融合策略层           │
│              │   (weighted/attention│                       │
│              │   /voting/custom)   │                       │
│              └──────────┬──────────┘                       │
│                         │                                   │
│                         ▼                                   │
│              ┌─────────────────────┐                       │
│              │   FusedResult       │  输出                 │
│              └─────────────────────┘                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Type, Awaitable
from datetime import datetime
from enum import Enum
import asyncio
import time
import uuid


class ModalityStatus(Enum):
    """模态状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    LOADING = "loading"


@dataclass
class ModalityResult:
    """模态分析结果"""
    modality_id: str
    modality_name: str
    success: bool
    data: Dict[str, Any]
    confidence: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "modality_id": self.modality_id,
            "modality_name": self.modality_name,
            "success": self.success,
            "data": self.data,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class FusedResult:
    """融合结果"""
    result_id: str
    primary_data: Dict[str, Any]
    modality_results: List[ModalityResult]
    fusion_strategy: str
    total_latency_ms: float
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "result_id": self.result_id,
            "primary_data": self.primary_data,
            "modality_results": [r.to_dict() for r in self.modality_results],
            "fusion_strategy": self.fusion_strategy,
            "total_latency_ms": self.total_latency_ms,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


class ModalityPlugin(ABC):
    """
    模态插件基类
    
    所有模态分析器必须继承此类并实现抽象方法
    """
    
    @property
    @abstractmethod
    def modality_id(self) -> str:
        """模态唯一标识"""
        pass
    
    @property
    @abstractmethod
    def modality_name(self) -> str:
        """模态名称"""
        pass
    
    @property
    def version(self) -> str:
        """版本号"""
        return "1.0.0"
    
    @property
    def description(self) -> str:
        """描述"""
        return ""
    
    @property
    def input_types(self) -> List[str]:
        """支持的输入类型"""
        return ["text"]
    
    @property
    def default_weight(self) -> float:
        """默认权重"""
        return 1.0
    
    @property
    def dependencies(self) -> List[str]:
        """依赖的其他模态"""
        return []
    
    @abstractmethod
    async def analyze(self, input_data: Dict[str, Any]) -> ModalityResult:
        """
        分析输入数据
        
        Args:
            input_data: 输入数据，可能包含 text, audio, image 等
        
        Returns:
            ModalityResult 分析结果
        """
        pass
    
    async def initialize(self) -> bool:
        """初始化插件（加载模型等）"""
        return True
    
    async def shutdown(self) -> bool:
        """关闭插件（释放资源）"""
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "modality_id": self.modality_id,
            "status": "healthy",
            "version": self.version
        }


class FusionStrategy(ABC):
    """融合策略基类"""
    
    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """策略名称"""
        pass
    
    @abstractmethod
    def fuse(self, results: List[ModalityResult], weights: Dict[str, float]) -> FusedResult:
        """
        融合多个模态的结果
        
        Args:
            results: 各模态的分析结果
            weights: 各模态的权重
        
        Returns:
            FusedResult 融合后的结果
        """
        pass


class WeightedFusionStrategy(FusionStrategy):
    """加权融合策略"""
    
    @property
    def strategy_name(self) -> str:
        return "weighted"
    
    def fuse(self, results: List[ModalityResult], weights: Dict[str, float]) -> FusedResult:
        if not results:
            return FusedResult(
                result_id=str(uuid.uuid4()),
                primary_data={},
                modality_results=[],
                fusion_strategy=self.strategy_name,
                total_latency_ms=0,
                confidence=0
            )
        
        total_weight = 0
        weighted_data = {}
        
        for result in results:
            if not result.success:
                continue
            
            weight = weights.get(result.modality_id, 1.0) * result.confidence
            total_weight += weight
            
            for key, value in result.data.items():
                if key not in weighted_data:
                    weighted_data[key] = {"value": 0, "weight": 0}
                
                if isinstance(value, (int, float)):
                    weighted_data[key]["value"] += value * weight
                    weighted_data[key]["weight"] += weight
                elif isinstance(value, str):
                    if weighted_data[key]["weight"] < weight:
                        weighted_data[key]["value"] = value
                        weighted_data[key]["weight"] = weight
                elif isinstance(value, dict):
                    if weighted_data[key]["weight"] < weight:
                        weighted_data[key]["value"] = value
                        weighted_data[key]["weight"] = weight
        
        fused_data = {}
        for key, data in weighted_data.items():
            if data["weight"] > 0:
                if isinstance(data["value"], (int, float)):
                    fused_data[key] = data["value"] / data["weight"]
                else:
                    fused_data[key] = data["value"]
        
        total_latency = sum(r.latency_ms for r in results)
        avg_confidence = sum(r.confidence for r in results if r.success) / len([r for r in results if r.success]) if results else 0
        
        return FusedResult(
            result_id=str(uuid.uuid4()),
            primary_data=fused_data,
            modality_results=results,
            fusion_strategy=self.strategy_name,
            total_latency_ms=total_latency,
            confidence=avg_confidence,
            metadata={"total_weight": total_weight}
        )


class AttentionFusionStrategy(FusionStrategy):
    """注意力融合策略"""
    
    @property
    def strategy_name(self) -> str:
        return "attention"
    
    def fuse(self, results: List[ModalityResult], weights: Dict[str, float]) -> FusedResult:
        if not results:
            return FusedResult(
                result_id=str(uuid.uuid4()),
                primary_data={},
                modality_results=[],
                fusion_strategy=self.strategy_name,
                total_latency_ms=0,
                confidence=0
            )
        
        successful_results = [r for r in results if r.success]
        if not successful_results:
            return FusedResult(
                result_id=str(uuid.uuid4()),
                primary_data={},
                modality_results=results,
                fusion_strategy=self.strategy_name,
                total_latency_ms=sum(r.latency_ms for r in results),
                confidence=0
            )
        
        attention_scores = {}
        total_attention = 0
        
        for result in successful_results:
            base_weight = weights.get(result.modality_id, 1.0)
            attention = base_weight * result.confidence
            attention_scores[result.modality_id] = attention
            total_attention += attention
        
        if total_attention > 0:
            for modality_id in attention_scores:
                attention_scores[modality_id] /= total_attention
        
        fused_data = {}
        for result in successful_results:
            attention = attention_scores[result.modality_id]
            for key, value in result.data.items():
                if key not in fused_data:
                    fused_data[key] = {"values": [], "attentions": []}
                fused_data[key]["values"].append(value)
                fused_data[key]["attentions"].append(attention)
        
        final_data = {}
        for key, data in fused_data.items():
            values = data["values"]
            attentions = data["attentions"]
            
            if all(isinstance(v, (int, float)) for v in values):
                final_data[key] = sum(v * a for v, a in zip(values, attentions))
            else:
                max_idx = attentions.index(max(attentions))
                final_data[key] = values[max_idx]
        
        total_latency = sum(r.latency_ms for r in results)
        avg_confidence = sum(r.confidence for r in successful_results) / len(successful_results)
        
        return FusedResult(
            result_id=str(uuid.uuid4()),
            primary_data=final_data,
            modality_results=results,
            fusion_strategy=self.strategy_name,
            total_latency_ms=total_latency,
            confidence=avg_confidence,
            metadata={"attention_scores": attention_scores}
        )


class VotingFusionStrategy(FusionStrategy):
    """投票融合策略"""
    
    @property
    def strategy_name(self) -> str:
        return "voting"
    
    def fuse(self, results: List[ModalityResult], weights: Dict[str, float]) -> FusedResult:
        if not results:
            return FusedResult(
                result_id=str(uuid.uuid4()),
                primary_data={},
                modality_results=[],
                fusion_strategy=self.strategy_name,
                total_latency_ms=0,
                confidence=0
            )
        
        successful_results = [r for r in results if r.success]
        if not successful_results:
            return FusedResult(
                result_id=str(uuid.uuid4()),
                primary_data={},
                modality_results=results,
                fusion_strategy=self.strategy_name,
                total_latency_ms=sum(r.latency_ms for r in results),
                confidence=0
            )
        
        votes = {}
        for result in successful_results:
            for key, value in result.data.items():
                if key not in votes:
                    votes[key] = {}
                value_key = str(value)
                if value_key not in votes[key]:
                    votes[key][value_key] = 0
                votes[key][value_key] += weights.get(result.modality_id, 1.0)
        
        final_data = {}
        for key, value_votes in votes.items():
            winner = max(value_votes.items(), key=lambda x: x[1])
            final_data[key] = winner[0]
        
        total_latency = sum(r.latency_ms for r in results)
        avg_confidence = sum(r.confidence for r in successful_results) / len(successful_results)
        
        return FusedResult(
            result_id=str(uuid.uuid4()),
            primary_data=final_data,
            modality_results=results,
            fusion_strategy=self.strategy_name,
            total_latency_ms=total_latency,
            confidence=avg_confidence,
            metadata={"votes": votes}
        )


class ModalityPluginSystem:
    """
    多模态插件系统
    
    特性：
    1. 可插拔 - 动态注册/注销模态
    2. 并行处理 - asyncio 并行执行
    3. 低延迟 - 最小化等待时间
    4. 容错 - 单个模态失败不影响整体
    """
    
    def __init__(
        self,
        default_fusion: str = "attention",
        timeout_ms: float = 5000,
        parallel: bool = True
    ):
        self._plugins: Dict[str, ModalityPlugin] = {}
        self._weights: Dict[str, float] = {}
        self._statuses: Dict[str, ModalityStatus] = {}
        self._fusion_strategies: Dict[str, FusionStrategy] = {
            "weighted": WeightedFusionStrategy(),
            "attention": AttentionFusionStrategy(),
            "voting": VotingFusionStrategy()
        }
        self._default_fusion = default_fusion
        self._timeout_ms = timeout_ms
        self._parallel = parallel
        self._hooks: Dict[str, List[Callable]] = {
            "before_analyze": [],
            "after_analyze": [],
            "on_error": [],
            "on_plugin_register": [],
            "on_plugin_unregister": []
        }
    
    def register_plugin(
        self,
        plugin: ModalityPlugin,
        weight: float = None,
        auto_init: bool = True
    ) -> bool:
        """
        注册模态插件
        
        Args:
            plugin: 模态插件实例
            weight: 权重（默认使用插件的 default_weight）
            auto_init: 是否自动初始化
        
        Returns:
            是否注册成功
        """
        modality_id = plugin.modality_id
        
        if modality_id in self._plugins:
            return False
        
        self._plugins[modality_id] = plugin
        self._weights[modality_id] = weight or plugin.default_weight
        self._statuses[modality_id] = ModalityStatus.LOADING
        
        if auto_init:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._init_plugin(modality_id))
                else:
                    loop.run_until_complete(self._init_plugin(modality_id))
            except RuntimeError:
                self._statuses[modality_id] = ModalityStatus.ACTIVE
        
        self._run_hooks("on_plugin_register", plugin)
        
        return True
    
    async def _init_plugin(self, modality_id: str):
        """初始化插件"""
        plugin = self._plugins[modality_id]
        try:
            success = await plugin.initialize()
            self._statuses[modality_id] = ModalityStatus.ACTIVE if success else ModalityStatus.ERROR
        except Exception as e:
            self._statuses[modality_id] = ModalityStatus.ERROR
    
    def unregister_plugin(self, modality_id: str) -> bool:
        """
        注销模态插件
        
        Args:
            modality_id: 模态ID
        
        Returns:
            是否注销成功
        """
        if modality_id not in self._plugins:
            return False
        
        plugin = self._plugins[modality_id]
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(plugin.shutdown())
            else:
                loop.run_until_complete(plugin.shutdown())
        except RuntimeError:
            pass
        except Exception:
            pass
        
        del self._plugins[modality_id]
        del self._weights[modality_id]
        del self._statuses[modality_id]
        
        self._run_hooks("on_plugin_unregister", plugin)
        
        return True
    
    def set_weight(self, modality_id: str, weight: float):
        """设置模态权重"""
        if modality_id in self._weights:
            self._weights[modality_id] = weight
    
    def set_status(self, modality_id: str, status: ModalityStatus):
        """设置模态状态"""
        if modality_id in self._statuses:
            self._statuses[modality_id] = status
    
    def register_fusion_strategy(self, strategy: FusionStrategy):
        """注册融合策略"""
        self._fusion_strategies[strategy.strategy_name] = strategy
    
    def add_hook(self, event: str, callback: Callable):
        """添加钩子"""
        if event in self._hooks:
            self._hooks[event].append(callback)
    
    def _run_hooks(self, event: str, *args, **kwargs):
        """运行钩子"""
        for callback in self._hooks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception:
                pass
    
    async def analyze(
        self,
        input_data: Dict[str, Any],
        modalities: List[str] = None,
        fusion_strategy: str = None
    ) -> FusedResult:
        """
        分析输入数据
        
        Args:
            input_data: 输入数据
            modalities: 指定使用的模态（None 表示使用所有活跃模态）
            fusion_strategy: 融合策略
        
        Returns:
            FusedResult 融合结果
        """
        start_time = time.time()
        
        self._run_hooks("before_analyze", input_data)
        
        active_modalities = self._get_active_modalities(modalities)
        
        if not active_modalities:
            return FusedResult(
                result_id=str(uuid.uuid4()),
                primary_data={},
                modality_results=[],
                fusion_strategy="none",
                total_latency_ms=0,
                confidence=0,
                metadata={"error": "No active modalities"}
            )
        
        if self._parallel:
            results = await self._analyze_parallel(active_modalities, input_data)
        else:
            results = await self._analyze_sequential(active_modalities, input_data)
        
        strategy_name = fusion_strategy or self._default_fusion
        strategy = self._fusion_strategies.get(strategy_name, self._fusion_strategies["weighted"])
        
        fused_result = strategy.fuse(results, self._weights)
        fused_result.total_latency_ms = (time.time() - start_time) * 1000
        
        self._run_hooks("after_analyze", fused_result)
        
        return fused_result
    
    def _get_active_modalities(self, modalities: List[str] = None) -> List[ModalityPlugin]:
        """获取活跃的模态"""
        if modalities:
            return [
                self._plugins[mid] 
                for mid in modalities 
                if mid in self._plugins and self._statuses.get(mid) == ModalityStatus.ACTIVE
            ]
        
        return [
            plugin 
            for plugin in self._plugins.values() 
            if self._statuses.get(plugin.modality_id) == ModalityStatus.ACTIVE
        ]
    
    async def _analyze_parallel(
        self,
        modalities: List[ModalityPlugin],
        input_data: Dict[str, Any]
    ) -> List[ModalityResult]:
        """并行分析"""
        timeout_sec = self._timeout_ms / 1000
        
        tasks = [
            asyncio.wait_for(
                self._safe_analyze(plugin, input_data),
                timeout=timeout_sec
            )
            for plugin in modalities
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(ModalityResult(
                    modality_id=modalities[i].modality_id,
                    modality_name=modalities[i].modality_name,
                    success=False,
                    data={},
                    error=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _analyze_sequential(
        self,
        modalities: List[ModalityPlugin],
        input_data: Dict[str, Any]
    ) -> List[ModalityResult]:
        """顺序分析"""
        results = []
        timeout_sec = self._timeout_ms / 1000
        
        for plugin in modalities:
            try:
                result = await asyncio.wait_for(
                    self._safe_analyze(plugin, input_data),
                    timeout=timeout_sec
                )
                results.append(result)
            except asyncio.TimeoutError:
                results.append(ModalityResult(
                    modality_id=plugin.modality_id,
                    modality_name=plugin.modality_name,
                    success=False,
                    data={},
                    error="Timeout"
                ))
            except Exception as e:
                results.append(ModalityResult(
                    modality_id=plugin.modality_id,
                    modality_name=plugin.modality_name,
                    success=False,
                    data={},
                    error=str(e)
                ))
        
        return results
    
    async def _safe_analyze(
        self,
        plugin: ModalityPlugin,
        input_data: Dict[str, Any]
    ) -> ModalityResult:
        """安全分析（捕获异常）"""
        start_time = time.time()
        
        try:
            result = await plugin.analyze(input_data)
            result.latency_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            self._run_hooks("on_error", plugin, e)
            return ModalityResult(
                modality_id=plugin.modality_id,
                modality_name=plugin.modality_name,
                success=False,
                data={},
                latency_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )
    
    def get_plugin_info(self, modality_id: str = None) -> Dict:
        """获取插件信息"""
        if modality_id:
            if modality_id not in self._plugins:
                return {}
            plugin = self._plugins[modality_id]
            return {
                "id": plugin.modality_id,
                "name": plugin.modality_name,
                "version": plugin.version,
                "description": plugin.description,
                "input_types": plugin.input_types,
                "weight": self._weights.get(modality_id),
                "status": self._statuses.get(modality_id).value if modality_id in self._statuses else "unknown"
            }
        
        return {
            "plugins": [
                self.get_plugin_info(mid) 
                for mid in self._plugins
            ],
            "fusion_strategies": list(self._fusion_strategies.keys()),
            "default_fusion": self._default_fusion,
            "parallel": self._parallel,
            "timeout_ms": self._timeout_ms
        }
    
    def health_check(self) -> Dict:
        """健康检查"""
        plugin_health = {}
        for modality_id, plugin in self._plugins.items():
            try:
                plugin_health[modality_id] = plugin.health_check()
            except Exception as e:
                plugin_health[modality_id] = {
                    "modality_id": modality_id,
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "system_status": "healthy" if any(
                s == ModalityStatus.ACTIVE for s in self._statuses.values()
            ) else "degraded",
            "plugins": plugin_health,
            "active_count": sum(1 for s in self._statuses.values() if s == ModalityStatus.ACTIVE),
            "total_count": len(self._plugins)
        }


def create_plugin_system(
    default_fusion: str = "attention",
    timeout_ms: float = 5000,
    parallel: bool = True
) -> ModalityPluginSystem:
    """创建插件系统实例"""
    return ModalityPluginSystem(
        default_fusion=default_fusion,
        timeout_ms=timeout_ms,
        parallel=parallel
    )
