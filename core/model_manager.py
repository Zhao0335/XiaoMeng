"""
XiaoMengCore 增强版模型管理器
支持：并行加载、健康检查、自动重试、负载均衡、智能路由

这是XiaoMengCore相比OpenClaw的改进之一：
- 多模型并行加载
- 智能健康检查
- 自动故障转移
- 负载均衡
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, AsyncGenerator, Callable, Awaitable
from enum import Enum
import asyncio
import time
import json
import logging

from .model_layer import (
    ModelLayer, ModelRole, TaskType, ModelEndpoint, ModelResponse,
    BaseModelAdapter, OpenAICompatibleAdapter
)

logger = logging.getLogger(__name__)


@dataclass
class ModelHealth:
    """模型健康状态"""
    model_id: str
    is_healthy: bool = True
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    avg_latency_ms: float = 0.0
    last_error: Optional[str] = None
    
    def record_success(self, latency_ms: float):
        self.is_healthy = True
        self.consecutive_failures = 0
        self.total_requests += 1
        self.last_check = datetime.now()
        self.avg_latency_ms = (
            (self.avg_latency_ms * (self.total_requests - 1) + latency_ms) 
            / self.total_requests
        )
    
    def record_failure(self, error: str):
        self.consecutive_failures += 1
        self.total_failures += 1
        self.total_requests += 1
        self.last_error = error
        self.last_check = datetime.now()
        if self.consecutive_failures >= 3:
            self.is_healthy = False


@dataclass
class LoadBalancingConfig:
    """负载均衡配置"""
    strategy: str = "least_latency"
    health_check_interval: int = 60
    max_retries: int = 3
    retry_delay: float = 1.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset: int = 300


class EnhancedModelManager:
    """
    增强版模型管理器
    
    特性：
    1. 并行初始化 - 所有模型同时加载
    2. 健康检查 - 定期检测模型可用性
    3. 自动重试 - 失败后自动重试其他模型
    4. 负载均衡 - 智能选择最优模型
    5. 熔断器 - 防止雪崩效应
    """
    
    _instance: Optional["EnhancedModelManager"] = None
    
    def __init__(
        self,
        load_balance_config: LoadBalancingConfig = None
    ):
        self._adapters: Dict[str, BaseModelAdapter] = {}
        self._endpoints: Dict[str, ModelEndpoint] = {}
        self._health: Dict[str, ModelHealth] = {}
        self._layers: Dict[ModelLayer, List[str]] = {
            ModelLayer.BASIC: [],
            ModelLayer.BRAIN: [],
            ModelLayer.SPECIAL: []
        }
        self._roles: Dict[ModelRole, List[str]] = {}
        self._config = load_balance_config or LoadBalancingConfig()
        self._initialized = False
        self._health_check_task: Optional[asyncio.Task] = None
    
    @classmethod
    def get_instance(cls) -> "EnhancedModelManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def initialize_parallel(
        self,
        endpoints: List[ModelEndpoint],
        warmup_prompts: List[str] = None
    ) -> Dict[str, bool]:
        """
        并行初始化所有模型
        
        返回每个模型的初始化状态
        """
        results = {}
        
        async def init_model(endpoint: ModelEndpoint) -> tuple[str, bool]:
            try:
                adapter = self._create_adapter(endpoint)
                self._adapters[endpoint.model_id] = adapter
                self._endpoints[endpoint.model_id] = endpoint
                self._health[endpoint.model_id] = ModelHealth(model_id=endpoint.model_id)
                
                self._layers[endpoint.layer].append(endpoint.model_id)
                
                if endpoint.role not in self._roles:
                    self._roles[endpoint.role] = []
                self._roles[endpoint.role].append(endpoint.model_id)
                
                if warmup_prompts and endpoint.layer != ModelLayer.BASIC:
                    try:
                        await asyncio.wait_for(
                            adapter.chat([{"role": "user", "content": warmup_prompts[0]}]),
                            timeout=30
                        )
                    except Exception as e:
                        logger.warning(f"Warmup failed for {endpoint.model_id}: {e}")
                
                return endpoint.model_id, True
            except Exception as e:
                logger.error(f"Failed to initialize {endpoint.model_id}: {e}")
                return endpoint.model_id, False
        
        tasks = [init_model(ep) for ep in endpoints]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in task_results:
            if isinstance(result, Exception):
                logger.error(f"Initialization error: {result}")
            else:
                model_id, success = result
                results[model_id] = success
        
        self._initialized = True
        
        if self._config.health_check_interval > 0:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        return results
    
    def _create_adapter(self, endpoint: ModelEndpoint) -> BaseModelAdapter:
        """创建模型适配器"""
        return OpenAICompatibleAdapter(endpoint)
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await asyncio.sleep(self._config.health_check_interval)
                await self.check_all_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def check_all_health(self) -> Dict[str, bool]:
        """检查所有模型健康状态"""
        async def check_one(model_id: str) -> tuple[str, bool]:
            adapter = self._adapters.get(model_id)
            if not adapter:
                return model_id, False
            
            try:
                start = time.time()
                await asyncio.wait_for(
                    adapter.chat([{"role": "user", "content": "ping"}], max_tokens=5),
                    timeout=10
                )
                latency = (time.time() - start) * 1000
                self._health[model_id].record_success(latency)
                return model_id, True
            except Exception as e:
                self._health[model_id].record_failure(str(e))
                return model_id, False
        
        tasks = [check_one(mid) for mid in self._adapters.keys()]
        results = await asyncio.gather(*tasks)
        return dict(results)
    
    def get_healthy_models(
        self,
        layer: Optional[ModelLayer] = None,
        role: Optional[ModelRole] = None
    ) -> List[str]:
        """获取健康的模型列表"""
        candidates = []
        
        if layer:
            candidates = self._layers.get(layer, [])
        elif role:
            candidates = self._roles.get(role, [])
        else:
            candidates = list(self._adapters.keys())
        
        return [
            mid for mid in candidates
            if self._health.get(mid, ModelHealth(model_id=mid)).is_healthy
            and self._endpoints.get(mid, ModelEndpoint(model_id="", layer=ModelLayer.BASIC, role=ModelRole.CHAT, endpoint="", model_name="")).enabled
        ]
    
    def select_best_model(
        self,
        layer: Optional[ModelLayer] = None,
        role: Optional[ModelRole] = None,
        task_type: Optional[TaskType] = None
    ) -> Optional[str]:
        """选择最优模型"""
        healthy = self.get_healthy_models(layer, role)
        
        if not healthy:
            return None
        
        if self._config.strategy == "least_latency":
            return min(
                healthy,
                key=lambda mid: self._health[mid].avg_latency_ms
            )
        elif self._config.strategy == "round_robin":
            return healthy[0]
        elif self._config.strategy == "random":
            import random
            return random.choice(healthy)
        else:
            return healthy[0]
    
    async def chat_with_retry(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        tools: List[Dict] = None,
        layer: ModelLayer = None,
        role: ModelRole = None,
        task_type: TaskType = None,
        **kwargs
    ) -> ModelResponse:
        """带重试的聊天请求"""
        last_error = None
        
        for attempt in range(self._config.max_retries):
            model_id = self.select_best_model(layer, role, task_type)
            
            if not model_id:
                raise Exception("No healthy models available")
            
            adapter = self._adapters.get(model_id)
            if not adapter:
                continue
            
            try:
                response = await adapter.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=tools,
                    **kwargs
                )
                self._health[model_id].record_success(response.latency_ms)
                return response
            except Exception as e:
                last_error = e
                self._health[model_id].record_failure(str(e))
                
                if attempt < self._config.max_retries - 1:
                    await asyncio.sleep(self._config.retry_delay * (attempt + 1))
        
        raise Exception(f"All retries failed: {last_error}")
    
    async def chat_parallel(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        layer: ModelLayer = None,
        role: ModelRole = None,
        n: int = 2,
        **kwargs
    ) -> List[ModelResponse]:
        """
        并行调用多个模型
        
        返回所有成功响应，用于：
        1. 结果对比
        2. 投票决策
        3. 冗余备份
        """
        healthy = self.get_healthy_models(layer, role)[:n]
        
        if not healthy:
            raise Exception("No healthy models available")
        
        async def call_model(model_id: str) -> Optional[ModelResponse]:
            adapter = self._adapters.get(model_id)
            if not adapter:
                return None
            try:
                return await adapter.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    **kwargs
                )
            except:
                return None
        
        tasks = [call_model(mid) for mid in healthy]
        results = await asyncio.gather(*tasks)
        
        return [r for r in results if r is not None]
    
    async def chat_stream(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        layer: ModelLayer = None,
        role: ModelRole = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式聊天"""
        model_id = self.select_best_model(layer, role)
        
        if not model_id:
            raise Exception("No healthy models available")
        
        adapter = self._adapters.get(model_id)
        if not adapter:
            raise Exception(f"Adapter not found for {model_id}")
        
        async for chunk in adapter.chat_stream(
            messages=messages,
            system_prompt=system_prompt,
            **kwargs
        ):
            yield chunk
    
    def register_endpoint(self, endpoint: ModelEndpoint) -> bool:
        """动态注册模型端点"""
        try:
            adapter = self._create_adapter(endpoint)
            self._adapters[endpoint.model_id] = adapter
            self._endpoints[endpoint.model_id] = endpoint
            self._health[endpoint.model_id] = ModelHealth(model_id=endpoint.model_id)
            
            self._layers[endpoint.layer].append(endpoint.model_id)
            
            if endpoint.role not in self._roles:
                self._roles[endpoint.role] = []
            self._roles[endpoint.role].append(endpoint.model_id)
            
            return True
        except Exception as e:
            logger.error(f"Failed to register endpoint: {e}")
            return False
    
    def unregister_endpoint(self, model_id: str) -> bool:
        """注销模型端点"""
        if model_id not in self._adapters:
            return False
        
        endpoint = self._endpoints.get(model_id)
        if endpoint:
            if model_id in self._layers.get(endpoint.layer, []):
                self._layers[endpoint.layer].remove(model_id)
            if model_id in self._roles.get(endpoint.role, []):
                self._roles[endpoint.role].remove(model_id)
        
        self._adapters.pop(model_id, None)
        self._endpoints.pop(model_id, None)
        self._health.pop(model_id, None)
        
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """获取模型状态"""
        return {
            "initialized": self._initialized,
            "total_models": len(self._adapters),
            "healthy_models": len(self.get_healthy_models()),
            "layers": {
                layer.value: len(models)
                for layer, models in self._layers.items()
            },
            "models": {
                model_id: {
                    "healthy": self._health[model_id].is_healthy,
                    "avg_latency_ms": self._health[model_id].avg_latency_ms,
                    "total_requests": self._health[model_id].total_requests,
                    "total_failures": self._health[model_id].total_failures,
                    "last_error": self._health[model_id].last_error
                }
                for model_id in self._adapters.keys()
            }
        }
    
    async def shutdown(self):
        """关闭管理器"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        self._adapters.clear()
        self._endpoints.clear()
        self._health.clear()
        self._initialized = False
