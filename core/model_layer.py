"""
XiaoMengCore 多模型分层调度系统
Basic/Brain/Special 三层架构

Basic: 单一本地模型（如Qwen7b），用于快速决策和路由判断
Brain: 多个推理模型，用于复杂任务处理
Special: 专业模型API，用于特定领域任务（代码、视觉、语音等）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, AsyncGenerator, Callable, Awaitable
from enum import Enum
import asyncio
import time
import json


class ModelLayer(Enum):
    BASIC = "basic"
    BRAIN = "brain"
    SPECIAL = "special"


class ModelRole(Enum):
    ROUTER = "router"
    CHAT = "chat"
    REASONING = "reasoning"
    CODE = "code"
    VISION = "vision"
    AUDIO = "audio"
    EMBEDDING = "embedding"
    ASR = "asr"
    TTS = "tts"


class TaskType(Enum):
    SIMPLE_CHAT = "simple_chat"
    COMPLEX_REASONING = "complex_reasoning"
    CODE_GENERATION = "code_generation"
    IMAGE_UNDERSTANDING = "image_understanding"
    DECISION_MAKING = "decision_making"
    ROUTING = "routing"
    EMBEDDING = "embedding"
    SPEECH_RECOGNITION = "speech_recognition"
    SPEECH_SYNTHESIS = "speech_synthesis"


@dataclass
class ModelEndpoint:
    model_id: str
    layer: ModelLayer
    role: ModelRole
    endpoint: str
    model_name: str
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60
    enabled: bool = True
    priority: int = 1
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "model_id": self.model_id,
            "layer": self.layer.value,
            "role": self.role.value,
            "endpoint": self.endpoint,
            "model_name": self.model_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "priority": self.priority,
            "capabilities": self.capabilities,
            "metadata": self.metadata
        }


@dataclass
class ModelResponse:
    content: str
    model_id: str
    model_name: str
    layer: ModelLayer
    latency_ms: float
    token_count: int = 0
    tool_calls: List[Dict] = field(default_factory=list)
    finish_reason: str = "stop"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "layer": self.layer.value,
            "latency_ms": self.latency_ms,
            "token_count": self.token_count,
            "tool_calls": self.tool_calls,
            "finish_reason": self.finish_reason,
            "metadata": self.metadata
        }


class BaseModelAdapter(ABC):
    
    def __init__(self, endpoint: ModelEndpoint):
        self.endpoint = endpoint
        self._busy = False
        self._request_count = 0
        self._total_latency = 0.0
    
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
        return self.endpoint.enabled and not self._busy
    
    @property
    def avg_latency(self) -> float:
        if self._request_count == 0:
            return 0.0
        return self._total_latency / self._request_count


class OpenAICompatibleAdapter(BaseModelAdapter):
    
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
                "model": self.endpoint.model_name,
                "messages": full_messages,
                "max_tokens": kwargs.get("max_tokens", self.endpoint.max_tokens),
                "temperature": kwargs.get("temperature", self.endpoint.temperature)
            }
            
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            
            headers = {"Content-Type": "application/json"}
            if self.endpoint.api_key:
                headers["Authorization"] = f"Bearer {self.endpoint.api_key}"
            
            timeout = aiohttp.ClientTimeout(total=self.endpoint.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.endpoint.endpoint}/chat/completions",
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API error: {response.status} - {error_text}")
                    
                    data = await response.json()
            
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            tool_calls = choice["message"].get("tool_calls", [])
            
            latency_ms = (time.time() - start_time) * 1000
            self._request_count += 1
            self._total_latency += latency_ms
            
            return ModelResponse(
                content=content,
                model_id=self.endpoint.model_id,
                model_name=self.endpoint.model_name,
                layer=self.endpoint.layer,
                latency_ms=latency_ms,
                token_count=data.get("usage", {}).get("completion_tokens", 0),
                tool_calls=self._parse_tool_calls(tool_calls),
                finish_reason=choice.get("finish_reason", "stop")
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
                "model": self.endpoint.model_name,
                "messages": full_messages,
                "max_tokens": kwargs.get("max_tokens", self.endpoint.max_tokens),
                "temperature": kwargs.get("temperature", self.endpoint.temperature),
                "stream": True
            }
            
            headers = {"Content-Type": "application/json"}
            if self.endpoint.api_key:
                headers["Authorization"] = f"Bearer {self.endpoint.api_key}"
            
            timeout = aiohttp.ClientTimeout(total=self.endpoint.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.endpoint.endpoint}/chat/completions",
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
                                data = json.loads(data_str)
                                if "choices" in data and data["choices"]:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                            except:
                                continue
        finally:
            self._busy = False
    
    def _parse_tool_calls(self, tool_calls: List) -> List[Dict]:
        result = []
        for tc in tool_calls:
            result.append({
                "id": tc.get("id", ""),
                "name": tc.get("function", {}).get("name", ""),
                "arguments": json.loads(tc.get("function", {}).get("arguments", "{}"))
            })
        return result


class OllamaAdapter(BaseModelAdapter):
    
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
                "model": self.endpoint.model_name,
                "messages": full_messages,
                "stream": False,
                "options": {
                    "num_predict": kwargs.get("max_tokens", self.endpoint.max_tokens),
                    "temperature": kwargs.get("temperature", self.endpoint.temperature)
                }
            }
            
            timeout = aiohttp.ClientTimeout(total=self.endpoint.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.endpoint.endpoint}/api/chat",
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Ollama error: {response.status} - {error_text}")
                    
                    data = await response.json()
            
            content = data["message"]["content"]
            latency_ms = (time.time() - start_time) * 1000
            self._request_count += 1
            self._total_latency += latency_ms
            
            return ModelResponse(
                content=content,
                model_id=self.endpoint.model_id,
                model_name=self.endpoint.model_name,
                layer=self.endpoint.layer,
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
                "model": self.endpoint.model_name,
                "messages": full_messages,
                "stream": True,
                "options": {
                    "num_predict": kwargs.get("max_tokens", self.endpoint.max_tokens),
                    "temperature": kwargs.get("temperature", self.endpoint.temperature)
                }
            }
            
            timeout = aiohttp.ClientTimeout(total=self.endpoint.timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.endpoint.endpoint}/api/chat",
                    json=payload
                ) as response:
                    async for line in response.content:
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
                        except:
                            continue
        finally:
            self._busy = False


class TaskClassifier:
    
    SIMPLE_PATTERNS = [
        "你好", "在吗", "早上好", "晚安", "谢谢", "再见",
        "是", "不是", "好的", "知道了", "嗯", "哦"
    ]
    
    CODE_PATTERNS = [
        "写代码", "编程", "函数", "类", "方法", "算法",
        "bug", "debug", "重构", "优化代码", "代码"
    ]
    
    REASONING_PATTERNS = [
        "为什么", "怎么", "如何", "分析", "解释", "比较",
        "设计", "规划", "评估", "推理", "论证", "思考"
    ]
    
    VISION_PATTERNS = [
        "看", "图片", "图像", "照片", "视频", "画面",
        "这是什么", "识别", "描述一下", "看到", "截图"
    ]
    
    DECISION_PATTERNS = [
        "应该", "选择", "决定", "哪个更好", "推荐",
        "帮我选", "判断", "评估"
    ]
    
    @classmethod
    def classify(cls, message: str, has_image: bool = False) -> TaskType:
        if has_image:
            return TaskType.IMAGE_UNDERSTANDING
        
        message_lower = message.lower()
        
        for pattern in cls.VISION_PATTERNS:
            if pattern in message_lower:
                return TaskType.IMAGE_UNDERSTANDING
        
        for pattern in cls.CODE_PATTERNS:
            if pattern in message_lower:
                return TaskType.CODE_GENERATION
        
        for pattern in cls.REASONING_PATTERNS:
            if pattern in message_lower:
                return TaskType.COMPLEX_REASONING
        
        for pattern in cls.DECISION_PATTERNS:
            if pattern in message_lower:
                return TaskType.DECISION_MAKING
        
        if len(message) > 500:
            return TaskType.COMPLEX_REASONING
        
        for pattern in cls.SIMPLE_PATTERNS:
            if pattern in message_lower:
                return TaskType.SIMPLE_CHAT
        
        if len(message) > 100:
            return TaskType.COMPLEX_REASONING
        
        return TaskType.SIMPLE_CHAT


class ModelLayerRouter:
    """
    三层模型路由器
    
    Basic层：单一本地模型，用于快速决策和路由
    Brain层：多个推理模型，用于复杂任务
    Special层：专业模型API，用于特定领域
    """
    
    _instance: Optional["ModelLayerRouter"] = None
    
    def __init__(self):
        self._adapters: Dict[str, BaseModelAdapter] = {}
        self._layers: Dict[ModelLayer, List[str]] = {
            ModelLayer.BASIC: [],
            ModelLayer.BRAIN: [],
            ModelLayer.SPECIAL: []
        }
        self._roles: Dict[ModelRole, List[str]] = {
            role: [] for role in ModelRole
        }
        self._classifier = TaskClassifier()
        self._basic_model_id: Optional[str] = None
    
    def register_model(self, endpoint: ModelEndpoint) -> str:
        if "ollama" in endpoint.endpoint.lower():
            adapter = OllamaAdapter(endpoint)
        else:
            adapter = OpenAICompatibleAdapter(endpoint)
        
        self._adapters[endpoint.model_id] = adapter
        self._layers[endpoint.layer].append(endpoint.model_id)
        self._roles[endpoint.role].append(endpoint.model_id)
        
        if endpoint.layer == ModelLayer.BASIC:
            if self._basic_model_id is None or endpoint.priority < self._get_adapter(self._basic_model_id).endpoint.priority:
                self._basic_model_id = endpoint.model_id
        
        return endpoint.model_id
    
    def unregister_model(self, model_id: str) -> bool:
        if model_id not in self._adapters:
            return False
        
        adapter = self._adapters[model_id]
        layer = adapter.endpoint.layer
        role = adapter.endpoint.role
        
        del self._adapters[model_id]
        
        if model_id in self._layers[layer]:
            self._layers[layer].remove(model_id)
        if model_id in self._roles[role]:
            self._roles[role].remove(model_id)
        
        if self._basic_model_id == model_id:
            self._basic_model_id = self._layers[ModelLayer.BASIC][0] if self._layers[ModelLayer.BASIC] else None
        
        return True
    
    def _get_adapter(self, model_id: str) -> Optional[BaseModelAdapter]:
        return self._adapters.get(model_id)
    
    def get_available_adapter(self, layer: ModelLayer, role: ModelRole = None) -> Optional[BaseModelAdapter]:
        if role:
            for model_id in self._roles[role]:
                adapter = self._adapters.get(model_id)
                if adapter and adapter.is_available:
                    return adapter
        
        for model_id in self._layers[layer]:
            adapter = self._adapters.get(model_id)
            if adapter and adapter.is_available:
                return adapter
        
        return None
    
    def get_basic_adapter(self) -> Optional[BaseModelAdapter]:
        if self._basic_model_id:
            adapter = self._adapters.get(self._basic_model_id)
            if adapter and adapter.is_available:
                return adapter
        return self.get_available_adapter(ModelLayer.BASIC)
    
    async def should_use_special(self, message: str, context: Dict = None) -> Optional[ModelRole]:
        basic_adapter = self.get_basic_adapter()
        if not basic_adapter:
            return None
        
        system_prompt = """你是一个路由决策器。分析用户消息，判断是否需要使用专业模型。

输出格式（只输出JSON，不要其他内容）：
{
    "need_special": true/false,
    "special_role": "code" / "vision" / null,
    "reason": "简短理由"
}

判断规则：
1. 涉及代码、编程、调试 → code
2. 涉及图片、图像理解 → vision
3. 简单对话、日常聊天 → 不需要special
4. 复杂推理、分析 → 不需要special（由Brain层处理）"""
        
        try:
            response = await basic_adapter.chat(
                messages=[{"role": "user", "content": message}],
                system_prompt=system_prompt,
                max_tokens=200,
                temperature=0.1
            )
            
            result = json.loads(response.content)
            if result.get("need_special"):
                role_str = result.get("special_role")
                if role_str:
                    return ModelRole(role_str)
        except:
            pass
        
        return None
    
    def route(self, message: str, has_image: bool = False, prefer_role: ModelRole = None) -> Optional[BaseModelAdapter]:
        task_type = self._classifier.classify(message, has_image)
        
        if prefer_role:
            adapter = self.get_available_adapter(ModelLayer.SPECIAL, prefer_role)
            if adapter:
                return adapter
        
        if task_type == TaskType.IMAGE_UNDERSTANDING:
            adapter = self.get_available_adapter(ModelLayer.SPECIAL, ModelRole.VISION)
            if adapter:
                return adapter
        
        if task_type == TaskType.CODE_GENERATION:
            adapter = self.get_available_adapter(ModelLayer.SPECIAL, ModelRole.CODE)
            if adapter:
                return adapter
        
        if task_type == TaskType.SIMPLE_CHAT:
            adapter = self.get_available_adapter(ModelLayer.BRAIN, ModelRole.CHAT)
            if adapter:
                return adapter
        
        if task_type in [TaskType.COMPLEX_REASONING, TaskType.DECISION_MAKING]:
            adapter = self.get_available_adapter(ModelLayer.BRAIN, ModelRole.REASONING)
            if adapter:
                return adapter
        
        for layer in [ModelLayer.BRAIN, ModelLayer.BASIC, ModelLayer.SPECIAL]:
            adapter = self.get_available_adapter(layer)
            if adapter:
                return adapter
        
        return None
    
    async def chat(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        tools: List[Dict] = None,
        prefer_model: str = None,
        prefer_role: ModelRole = None,
        prompt_mode: str = "full",
        minimal_system_prompt: str = None,
        **kwargs
    ) -> ModelResponse:
        if prefer_model and prefer_model in self._adapters:
            adapter = self._adapters[prefer_model]
            if adapter.is_available:
                return await adapter.chat(messages, system_prompt, tools, **kwargs)
        
        last_message = messages[-1]["content"] if messages else ""
        has_image = any(
            isinstance(m.get("content"), list) 
            for m in messages
        )
        
        special_role = await self.should_use_special(last_message)
        if special_role:
            adapter = self.get_available_adapter(ModelLayer.SPECIAL, special_role)
            if adapter:
                minimal_prompt = self._build_special_prompt(special_role, last_message)
                return await adapter.chat(messages, minimal_prompt, tools, **kwargs)
        
        adapter = self.route(last_message, has_image, prefer_role)
        
        if not adapter:
            return ModelResponse(
                content="抱歉，所有模型都忙不过来了，请稍后再试~",
                model_id="fallback",
                model_name="fallback",
                layer=ModelLayer.BASIC,
                latency_ms=0
            )
        
        effective_prompt = system_prompt
        if adapter.endpoint.layer == ModelLayer.BASIC:
            if minimal_system_prompt:
                effective_prompt = minimal_system_prompt
            else:
                effective_prompt = self._build_basic_prompt(last_message)
        
        return await adapter.chat(messages, effective_prompt, tools, **kwargs)
    
    def _build_basic_prompt(self, message: str) -> str:
        """构建Basic层的极简提示词 - 用于快速路由判断"""
        return """You are a routing assistant. Analyze the message and respond briefly.
Focus on understanding user intent, not detailed responses."""
    
    def _build_special_prompt(self, role: ModelRole, message: str) -> str:
        """构建Special层的定制提示词"""
        role_prompts = {
            ModelRole.CODE: """You are a code expert. Focus on:
- Writing clean, efficient code
- Explaining technical concepts
- Debugging and optimization
Provide code solutions with brief explanations.""",
            
            ModelRole.VISION: """You are a vision expert. Focus on:
- Image analysis and description
- Visual content understanding
- OCR and text extraction
Describe what you see clearly and concisely.""",
            
            ModelRole.REASONING: """You are a reasoning expert. Focus on:
- Logical analysis
- Problem decomposition
- Step-by-step solutions
Think through problems methodically."""
        }
        return role_prompts.get(role, "You are a specialized assistant.")
    
    async def chat_stream(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        prefer_model: str = None,
        prefer_role: ModelRole = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        if prefer_model and prefer_model in self._adapters:
            adapter = self._adapters[prefer_model]
            if adapter.is_available:
                async for chunk in adapter.chat_stream(messages, system_prompt, **kwargs):
                    yield chunk
                return
        
        last_message = messages[-1]["content"] if messages else ""
        has_image = any(
            isinstance(m.get("content"), list) 
            for m in messages
        )
        
        adapter = self.route(last_message, has_image, prefer_role)
        
        if not adapter:
            yield "抱歉，所有模型都忙不过来了，请稍后再试~"
            return
        
        async for chunk in adapter.chat_stream(messages, system_prompt, **kwargs):
            yield chunk
    
    async def parallel_chat(
        self,
        messages_list: List[List[Dict]],
        system_prompt: str = None,
        **kwargs
    ) -> List[ModelResponse]:
        tasks = [
            self.chat(messages, system_prompt, **kwargs)
            for messages in messages_list
        ]
        return await asyncio.gather(*tasks)
    
    def get_status(self) -> Dict:
        status = {
            "layers": {},
            "models": [],
            "basic_model": self._basic_model_id
        }
        
        for layer in ModelLayer:
            models = []
            for model_id in self._layers[layer]:
                adapter = self._adapters.get(model_id)
                if adapter:
                    models.append({
                        "model_id": model_id,
                        "model_name": adapter.endpoint.model_name,
                        "role": adapter.endpoint.role.value,
                        "available": adapter.is_available,
                        "avg_latency_ms": adapter.avg_latency
                    })
            status["layers"][layer.value] = {
                "count": len(models),
                "models": models
            }
        
        for model_id, adapter in self._adapters.items():
            status["models"].append(adapter.endpoint.to_dict())
        
        return status
    
    def get_model(self, model_id: str) -> Optional[ModelEndpoint]:
        adapter = self._adapters.get(model_id)
        return adapter.endpoint if adapter else None
    
    def list_models(self, layer: ModelLayer = None) -> List[ModelEndpoint]:
        if layer:
            return [
                self._adapters[mid].endpoint 
                for mid in self._layers[layer] 
                if mid in self._adapters
            ]
        return [a.endpoint for a in self._adapters.values()]
    
    @classmethod
    def get_instance(cls) -> "ModelLayerRouter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        cls._instance = None
