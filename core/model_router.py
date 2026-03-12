"""
XiaoMengCore 多LLM路由层
支持多模型并存调度，智能选择合适的模型处理请求
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, AsyncGenerator
from enum import Enum
import asyncio
import time


class ModelType(Enum):
    """模型类型"""
    SMALL_7B = "7b"
    MEDIUM_14B = "14b"
    LARGE_70B = "70b"
    VLM = "vlm"
    ASR = "asr"
    TTS = "tts"
    EMBEDDING = "embedding"
    EXTERNAL_API = "external_api"


class TaskComplexity(Enum):
    """任务复杂度"""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    VISUAL = "visual"


class TaskPriority(Enum):
    """任务优先级"""
    REALTIME = 0
    INTERACTIVE = 1
    UNDERSTANDING = 2
    BACKGROUND = 3


@dataclass
class ModelConfig:
    """模型配置"""
    model_type: ModelType
    model_name: str
    endpoint: str
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60
    enabled: bool = True
    priority: int = 1
    
    def to_dict(self) -> Dict:
        return {
            "model_type": self.model_type.value,
            "model_name": self.model_name,
            "endpoint": self.endpoint,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "priority": self.priority
        }


@dataclass
class ModelResponse:
    """模型响应"""
    content: str
    model_type: ModelType
    model_name: str
    latency_ms: float
    token_count: int = 0
    tool_calls: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "model_type": self.model_type.value,
            "model_name": self.model_name,
            "latency_ms": self.latency_ms,
            "token_count": self.token_count,
            "tool_calls": self.tool_calls,
            "metadata": self.metadata
        }


class BaseModelClient(ABC):
    """模型客户端基类"""
    
    def __init__(self, config: ModelConfig):
        self.config = config
        self._busy = False
    
    @abstractmethod
    async def chat(
        self, 
        messages: List[Dict], 
        system_prompt: str = None,
        tools: List[Dict] = None,
        **kwargs
    ) -> ModelResponse:
        pass
    
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        pass
    
    @property
    def is_busy(self) -> bool:
        return self._busy
    
    @property
    def is_available(self) -> bool:
        return self.config.enabled and not self._busy


class OpenAIClient(BaseModelClient):
    """OpenAI 兼容客户端"""
    
    async def chat(
        self, 
        messages: List[Dict], 
        system_prompt: str = None,
        tools: List[Dict] = None,
        **kwargs
    ) -> ModelResponse:
        import aiohttp
        
        start_time = time.time()
        self._busy = True
        
        try:
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
            
            payload = {
                "model": self.config.model_name,
                "messages": full_messages,
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature)
            }
            
            if tools:
                payload["tools"] = tools
            
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.config.endpoint}/chat/completions",
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API error: {response.status} - {error_text}")
                    
                    data = await response.json()
            
            choice = data["choices"][0]
            content = choice["message"]["content"]
            tool_calls = choice["message"].get("tool_calls", [])
            
            latency_ms = (time.time() - start_time) * 1000
            
            return ModelResponse(
                content=content,
                model_type=self.config.model_type,
                model_name=self.config.model_name,
                latency_ms=latency_ms,
                token_count=data.get("usage", {}).get("completion_tokens", 0),
                tool_calls=tool_calls
            )
            
        finally:
            self._busy = False
    
    async def chat_stream(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        import aiohttp
        
        self._busy = True
        
        try:
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
            
            payload = {
                "model": self.config.model_name,
                "messages": full_messages,
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature),
                "stream": True
            }
            
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.config.endpoint}/chat/completions",
                    json=payload,
                    headers=headers
                ) as response:
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                import json
                                data = json.loads(data_str)
                                if "choices" in data and data["choices"]:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                            except:
                                continue
        finally:
            self._busy = False


class OllamaClient(BaseModelClient):
    """Ollama 本地模型客户端"""
    
    async def chat(
        self, 
        messages: List[Dict], 
        system_prompt: str = None,
        tools: List[Dict] = None,
        **kwargs
    ) -> ModelResponse:
        import aiohttp
        
        start_time = time.time()
        self._busy = True
        
        try:
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
            
            payload = {
                "model": self.config.model_name,
                "messages": full_messages,
                "stream": False,
                "options": {
                    "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
                    "temperature": kwargs.get("temperature", self.config.temperature)
                }
            }
            
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.config.endpoint}/api/chat",
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Ollama error: {response.status} - {error_text}")
                    
                    data = await response.json()
            
            content = data["message"]["content"]
            latency_ms = (time.time() - start_time) * 1000
            
            return ModelResponse(
                content=content,
                model_type=self.config.model_type,
                model_name=self.config.model_name,
                latency_ms=latency_ms,
                token_count=0
            )
            
        finally:
            self._busy = False
    
    async def chat_stream(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        import aiohttp
        
        self._busy = True
        
        try:
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
            
            payload = {
                "model": self.config.model_name,
                "messages": full_messages,
                "stream": True,
                "options": {
                    "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
                    "temperature": kwargs.get("temperature", self.config.temperature)
                }
            }
            
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.config.endpoint}/api/chat",
                    json=payload
                ) as response:
                    async for line in response.content:
                        try:
                            import json
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
                        except:
                            continue
        finally:
            self._busy = False


class ComplexityEstimator:
    """任务复杂度评估器"""
    
    SIMPLE_KEYWORDS = [
        "你好", "在吗", "早上好", "晚安", "谢谢", "再见",
        "是", "不是", "好的", "知道了", "嗯"
    ]
    
    COMPLEX_KEYWORDS = [
        "为什么", "怎么", "如何", "分析", "解释", "比较",
        "设计", "规划", "优化", "评估", "推理", "论证",
        "写代码", "编程", "算法", "架构"
    ]
    
    VISUAL_KEYWORDS = [
        "看", "图片", "图像", "照片", "视频", "画面",
        "这是什么", "识别", "描述一下", "看到"
    ]
    
    @classmethod
    def estimate(cls, message: str, has_image: bool = False) -> TaskComplexity:
        """评估任务复杂度"""
        if has_image:
            return TaskComplexity.VISUAL
        
        message_lower = message.lower()
        
        for keyword in cls.VISUAL_KEYWORDS:
            if keyword in message_lower:
                return TaskComplexity.VISUAL
        
        for keyword in cls.COMPLEX_KEYWORDS:
            if keyword in message_lower:
                return TaskComplexity.COMPLEX
        
        if len(message) > 500:
            return TaskComplexity.MEDIUM
        
        for keyword in cls.SIMPLE_KEYWORDS:
            if keyword in message_lower:
                return TaskComplexity.SIMPLE
        
        if len(message) > 100:
            return TaskComplexity.MEDIUM
        
        return TaskComplexity.SIMPLE


class ModelRouter:
    """
    模型路由器
    
    根据任务复杂度、优先级和模型可用性智能选择模型
    """
    
    _instance: Optional["ModelRouter"] = None
    
    def __init__(self):
        self._clients: Dict[ModelType, List[BaseModelClient]] = {
            model_type: [] for model_type in ModelType
        }
        self._complexity_estimator = ComplexityEstimator()
        self._routing_rules: Dict[TaskComplexity, ModelType] = {
            TaskComplexity.SIMPLE: ModelType.SMALL_7B,
            TaskComplexity.MEDIUM: ModelType.SMALL_7B,
            TaskComplexity.COMPLEX: ModelType.LARGE_70B,
            TaskComplexity.VISUAL: ModelType.VLM
        }
        self._fallback_chain: Dict[TaskComplexity, List[ModelType]] = {
            TaskComplexity.SIMPLE: [ModelType.SMALL_7B, ModelType.MEDIUM_14B, ModelType.LARGE_70B],
            TaskComplexity.MEDIUM: [ModelType.SMALL_7B, ModelType.MEDIUM_14B, ModelType.LARGE_70B],
            TaskComplexity.COMPLEX: [ModelType.LARGE_70B, ModelType.MEDIUM_14B, ModelType.SMALL_7B],
            TaskComplexity.VISUAL: [ModelType.VLM]
        }
    
    def register_client(self, client: BaseModelClient):
        """注册模型客户端"""
        model_type = client.config.model_type
        self._clients[model_type].append(client)
        self._clients[model_type].sort(key=lambda c: c.config.priority)
    
    def register_model(self, config: ModelConfig):
        """注册模型"""
        if "ollama" in config.endpoint.lower():
            client = OllamaClient(config)
        else:
            client = OpenAIClient(config)
        
        self.register_client(client)
    
    def get_available_client(self, model_type: ModelType) -> Optional[BaseModelClient]:
        """获取可用的模型客户端"""
        clients = self._clients.get(model_type, [])
        for client in clients:
            if client.is_available:
                return client
        return None
    
    def route(
        self, 
        message: str, 
        priority: TaskPriority = TaskPriority.INTERACTIVE,
        has_image: bool = False,
        prefer_model: ModelType = None
    ) -> Optional[BaseModelClient]:
        """路由到合适的模型"""
        if prefer_model:
            client = self.get_available_client(prefer_model)
            if client:
                return client
        
        complexity = self._complexity_estimator.estimate(message, has_image)
        
        fallback_types = self._fallback_chain.get(complexity, [ModelType.SMALL_7B])
        
        for model_type in fallback_types:
            client = self.get_available_client(model_type)
            if client:
                return client
        
        for model_type in ModelType:
            client = self.get_available_client(model_type)
            if client:
                return client
        
        return None
    
    async def chat(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        tools: List[Dict] = None,
        priority: TaskPriority = TaskPriority.INTERACTIVE,
        prefer_model: ModelType = None,
        **kwargs
    ) -> ModelResponse:
        """智能路由聊天"""
        last_message = messages[-1]["content"] if messages else ""
        has_image = any(
            isinstance(m.get("content"), list) 
            for m in messages
        )
        
        client = self.route(last_message, priority, has_image, prefer_model)
        
        if not client:
            return ModelResponse(
                content="抱歉，所有模型都忙不过来了，请稍后再试~",
                model_type=ModelType.SMALL_7B,
                model_name="fallback",
                latency_ms=0
            )
        
        return await client.chat(messages, system_prompt, tools, **kwargs)
    
    async def chat_stream(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        priority: TaskPriority = TaskPriority.INTERACTIVE,
        prefer_model: ModelType = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """智能路由流式聊天"""
        last_message = messages[-1]["content"] if messages else ""
        has_image = any(
            isinstance(m.get("content"), list) 
            for m in messages
        )
        
        client = self.route(last_message, priority, has_image, prefer_model)
        
        if not client:
            yield "抱歉，所有模型都忙不过来了，请稍后再试~"
            return
        
        async for chunk in client.chat_stream(messages, system_prompt, **kwargs):
            yield chunk
    
    def get_status(self) -> Dict:
        """获取路由器状态"""
        status = {}
        for model_type, clients in self._clients.items():
            status[model_type.value] = {
                "total": len(clients),
                "available": sum(1 for c in clients if c.is_available),
                "clients": [
                    {
                        "name": c.config.model_name,
                        "available": c.is_available
                    }
                    for c in clients
                ]
            }
        return status
    
    @classmethod
    def get_instance(cls) -> "ModelRouter":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
