"""
XiaoMengCore 多模型分层调度系统
Basic/Brain/Special 三层架构

Basic: 单一本地模型（如Qwen7b），用于快速决策和路由判断
Brain: 多个推理模型，用于复杂任务处理
Special: 专业模型API，用于特定领域任务（代码、视觉、语音等）
"""

import asyncio
import contextlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ModelLayer(Enum):
    BASIC = "basic"
    BRAIN = "brain"
    SPECIAL = "special"
    PRO = "pro"


class ModelRole(Enum):
    ROUTER = "router"  # 专职路由判断（轻量模型）
    CHAT = "chat"
    REASONING = "reasoning"
    CODE = "code"
    VISION = "vision"
    AUDIO = "audio"
    EMBEDDING = "embedding"
    ASR = "asr"
    TTS = "tts"


class ModelProvider(Enum):
    """API 协议类型，决定用哪个 Adapter"""

    OPENAI = "openai"  # OpenAI 兼容 API（含 DeepSeek、OneAPI 等）
    OLLAMA = "ollama"  # Ollama 原生 API


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
    proxy: Optional[str] = None  # e.g. "http://127.0.0.1:7890"
    num_ctx: Optional[int] = None  # ollama only: context window size
    provider: Optional[ModelProvider] = None  # 显式指定协议；None 则自动检测
    capabilities: List[str] = field(default_factory=list)
    # thinking: "disable" → 发 enable_thinking:false；"none"/None → 不干预
    thinking: Optional[str] = None
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
            "provider": self.provider.value if self.provider else None,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
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
    reasoning_content: Optional[str] = None  # 推理模型（如 DeepSeek R1）的思考链
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
            "metadata": self.metadata,
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
        **kwargs,
    ) -> ModelResponse:
        pass

    @abstractmethod
    async def chat_stream(
        self, messages: List[Dict], system_prompt: str = None, **kwargs
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

    def _get_proxy(self):
        """Return (proxy_url, ctx_manager). ctx_manager clears system proxy env vars when proxy_raw==""."""
        proxy_raw = self.endpoint.proxy
        if proxy_raw == "":
            return None, self._clear_proxy_env()
        return proxy_raw or None, contextlib.nullcontext()

    @staticmethod
    @contextlib.contextmanager
    def _clear_proxy_env():
        keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            yield
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


class OpenAICompatibleAdapter(BaseModelAdapter):
    async def chat(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        tools: List[Dict] = None,
        **kwargs,
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
                "temperature": kwargs.get("temperature", self.endpoint.temperature),
            }

            # thinking 控制：allow_thinking=True 时强制放开（用于图片描述等需要推理的场景）
            force_thinking = kwargs.get("allow_thinking", False)
            if self.endpoint.thinking == "disable" and not force_thinking:
                # 多种方式同时下发，兼容不同后端：
                # 1) 顶层 enable_thinking=false（部分自建网关接受）
                # 2) chat_template_kwargs.enable_thinking=false（vLLM/SGLang 的 Qwen3 标准）
                # 3) 系统提示注入 /no_think（Qwen3 模板硬触发）
                payload["enable_thinking"] = False
                payload["chat_template_kwargs"] = {"enable_thinking": False}
                if full_messages and full_messages[0]["role"] == "system":
                    if "/no_think" not in full_messages[0]["content"]:
                        full_messages[0]["content"] += "\n/no_think"
                else:
                    full_messages.insert(0, {"role": "system", "content": "/no_think"})

            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            headers = {"Content-Type": "application/json"}
            if self.endpoint.api_key:
                headers["Authorization"] = f"Bearer {self.endpoint.api_key}"

            _req_timeout = kwargs.get("request_timeout", self.endpoint.timeout)
            timeout = aiohttp.ClientTimeout(total=_req_timeout)

            _proxy, _proxy_ctx = self._get_proxy()
            with _proxy_ctx:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{self.endpoint.endpoint}/chat/completions",
                        json=payload,
                        headers=headers,
                        proxy=_proxy,
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f"API error: {response.status} - {error_text}")

                        data = await response.json()

            choice = data["choices"][0]
            msg = choice["message"]
            content = msg.get("content") or ""
            tool_calls_raw = msg.get("tool_calls") or []
            reasoning_content = (
                msg.get("reasoning_content")
                or msg.get("reasoning")
                or choice.get("reasoning_content")
                or ""
            )
            # litellm 等代理会把 thinking 内容放进 reasoning_content，content 留空
            # 此时用 reasoning_content 作为 fallback（_clean_reply 会进一步清理）
            # 但 thinking="disable" 时不 fallback：否则 router 拿到的就是思考过程而非分类结果
            thinking_disabled = (
                self.endpoint.thinking == "disable" and not force_thinking
            )
            if not content and reasoning_content and not thinking_disabled:
                content = reasoning_content

            # 优先用标准 tool_calls 字段；没有时尝试从 content 解析 DSML 格式
            if tool_calls_raw:
                parsed_tool_calls = self._parse_tool_calls(tool_calls_raw)
            else:
                parsed_tool_calls, content = self._parse_dsml_tool_calls(content)

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
                tool_calls=parsed_tool_calls,
                finish_reason=choice.get("finish_reason", "stop"),
                reasoning_content=reasoning_content,
            )

        finally:
            self._busy = False

    async def chat_stream(
        self, messages: List[Dict], system_prompt: str = None, **kwargs
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
                "stream": True,
            }

            headers = {"Content-Type": "application/json"}
            if self.endpoint.api_key:
                headers["Authorization"] = f"Bearer {self.endpoint.api_key}"

            timeout = aiohttp.ClientTimeout(total=self.endpoint.timeout)

            _proxy, _proxy_ctx = self._get_proxy()
            with _proxy_ctx:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{self.endpoint.endpoint}/chat/completions",
                        json=payload,
                        headers=headers,
                        proxy=_proxy,
                    ) as response:
                        async for line in response.content:
                            line = line.decode("utf-8").strip()
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
                                except (json.JSONDecodeError, KeyError, IndexError):
                                    continue
        finally:
            self._busy = False

    def _parse_tool_calls(self, tool_calls: List) -> List[Dict]:
        result = []
        for tc in tool_calls:
            try:
                args_raw = tc.get("function", {}).get("arguments", "{}")
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except Exception:
                args = {}
            result.append(
                {
                    "id": tc.get("id", ""),
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": args,
                }
            )
        return result

    @staticmethod
    def _parse_dsml_tool_calls(content: str):
        """
        解析 DeepSeek 推理模型在 content 里输出的 DSML 格式工具调用。
        返回 (tool_calls_list, cleaned_content)。
        DSML 格式：<｜｜DSML｜｜tool_calls>...<｜｜DSML｜｜invoke name="...">...</>
        """
        P = "｜｜DSML｜｜"  # fullwidth vertical lines + DSML + fullwidth vertical lines
        tc_open = f"<{P}tool_calls>"
        tc_close = f"</{P}tool_calls>"

        start = content.find(tc_open)
        if start == -1:
            return [], content
        end = content.find(tc_close, start)
        if end == -1:
            return [], content

        tc_block = content[start + len(tc_open) : end]
        cleaned = content[:start].strip()

        calls = []
        inv_prefix = f'<{P}invoke name="'
        inv_close = f"</{P}invoke>"
        param_prefix = f'<{P}parameter name="'
        param_close = f"</{P}parameter>"

        pos = 0
        idx = 0
        while True:
            s = tc_block.find(inv_prefix, pos)
            if s == -1:
                break
            name_start = s + len(inv_prefix)
            name_end = tc_block.find('">', name_start)
            if name_end == -1:
                break
            tool_name = tc_block[name_start:name_end]

            body_start = name_end + 2
            inv_end = tc_block.find(inv_close, body_start)
            if inv_end == -1:
                break
            params_block = tc_block[body_start:inv_end]

            args = {}
            pp = 0
            while True:
                ps = params_block.find(param_prefix, pp)
                if ps == -1:
                    break
                pname_start = ps + len(param_prefix)
                pname_end = params_block.find('"', pname_start)
                if pname_end == -1:
                    break
                param_name = params_block[pname_start:pname_end]
                tag_end = params_block.find(">", pname_end)
                if tag_end == -1:
                    break
                pc = params_block.find(param_close, tag_end)
                if pc == -1:
                    break
                param_value = params_block[tag_end + 1 : pc].strip()
                try:
                    args[param_name] = json.loads(param_value)
                except Exception:
                    args[param_name] = param_value
                pp = pc + len(param_close)

            calls.append({"id": f"dsml_{idx}", "name": tool_name, "arguments": args})
            idx += 1
            pos = inv_end + len(inv_close)

        return calls, cleaned


class OllamaAdapter(BaseModelAdapter):
    async def chat(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        tools: List[Dict] = None,
        **kwargs,
    ) -> ModelResponse:
        import aiohttp

        start_time = time.time()
        self._busy = True

        try:
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)

            options: Dict = {
                "num_predict": kwargs.get("max_tokens", self.endpoint.max_tokens),
                "temperature": kwargs.get("temperature", self.endpoint.temperature),
            }
            if self.endpoint.num_ctx:
                options["num_ctx"] = self.endpoint.num_ctx
            payload = {
                "model": self.endpoint.model_name,
                "messages": full_messages,
                "stream": False,
                "options": options,
            }
            if tools:
                payload["tools"] = tools

            timeout = aiohttp.ClientTimeout(total=self.endpoint.timeout)

            _proxy, _proxy_ctx = self._get_proxy()
            with _proxy_ctx:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{self.endpoint.endpoint}/api/chat", json=payload, proxy=_proxy
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(
                                f"Ollama error: {response.status} - {error_text}"
                            )

                        data = await response.json()

            msg = data["message"]
            content = msg.get("content") or ""
            tool_calls_raw = msg.get("tool_calls") or []

            # Ollama tool_calls 格式: [{"function": {"name": ..., "arguments": {...}}}]
            parsed_tool_calls = []
            for tc in tool_calls_raw:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                parsed_tool_calls.append(
                    {
                        "id": tc.get("id", f"ollama_{len(parsed_tool_calls)}"),
                        "name": fn.get("name", ""),
                        "arguments": args,
                    }
                )

            latency_ms = (time.time() - start_time) * 1000
            self._request_count += 1
            self._total_latency += latency_ms

            logger.info(
                f"[Ollama] done={data.get('done_reason')} tc={len(parsed_tool_calls)} content={content!r:.120}"
            )

            return ModelResponse(
                content=content,
                model_id=self.endpoint.model_id,
                model_name=self.endpoint.model_name,
                layer=self.endpoint.layer,
                latency_ms=latency_ms,
                token_count=0,
                tool_calls=parsed_tool_calls,
            )

        finally:
            self._busy = False

    async def chat_stream(
        self, messages: List[Dict], system_prompt: str = None, **kwargs
    ) -> AsyncGenerator[str, None]:
        import aiohttp

        self._busy = True

        try:
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)

            options: Dict = {
                "num_predict": kwargs.get("max_tokens", self.endpoint.max_tokens),
                "temperature": kwargs.get("temperature", self.endpoint.temperature),
            }
            if self.endpoint.num_ctx:
                options["num_ctx"] = self.endpoint.num_ctx
            payload = {
                "model": self.endpoint.model_name,
                "messages": full_messages,
                "stream": True,
                "options": options,
            }

            timeout = aiohttp.ClientTimeout(total=self.endpoint.timeout)

            _proxy, _proxy_ctx = self._get_proxy()
            with _proxy_ctx:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        f"{self.endpoint.endpoint}/api/chat", json=payload, proxy=_proxy
                    ) as response:
                        async for line in response.content:
                            try:
                                data = json.loads(line)
                                if "message" in data and "content" in data["message"]:
                                    yield data["message"]["content"]
                            except (json.JSONDecodeError, KeyError):
                                continue
        finally:
            self._busy = False


class TaskClassifier:
    SIMPLE_PATTERNS = [
        "你好",
        "在吗",
        "早上好",
        "晚安",
        "谢谢",
        "再见",
        "是",
        "不是",
        "好的",
        "知道了",
        "嗯",
        "哦",
    ]

    CODE_PATTERNS = [
        "写代码",
        "编程",
        "函数",
        "类",
        "方法",
        "算法",
        "bug",
        "debug",
        "重构",
        "优化代码",
        "代码",
    ]

    REASONING_PATTERNS = [
        "为什么",
        "怎么",
        "如何",
        "分析",
        "解释",
        "比较",
        "设计",
        "规划",
        "评估",
        "推理",
        "论证",
        "思考",
    ]

    VISION_PATTERNS = [
        "看",
        "图片",
        "图像",
        "照片",
        "视频",
        "画面",
        "这是什么",
        "识别",
        "描述一下",
        "看到",
        "截图",
    ]

    DECISION_PATTERNS = [
        "应该",
        "选择",
        "决定",
        "哪个更好",
        "推荐",
        "帮我选",
        "判断",
        "评估",
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

    # ── 适配器注册表：provider → adapter class ──
    _ADAPTER_REGISTRY: Dict[ModelProvider, type] = {
        ModelProvider.OPENAI: OpenAICompatibleAdapter,
        ModelProvider.OLLAMA: OllamaAdapter,
    }

    _instance: Optional["ModelLayerRouter"] = None

    def __init__(self):
        self._adapters: Dict[str, BaseModelAdapter] = {}
        self._layers: Dict[ModelLayer, List[str]] = {
            ModelLayer.BASIC: [],
            ModelLayer.BRAIN: [],
            ModelLayer.SPECIAL: [],
            ModelLayer.PRO: [],
        }
        self._roles: Dict[ModelRole, List[str]] = {role: [] for role in ModelRole}
        self._classifier = TaskClassifier()
        self._basic_model_id: Optional[str] = None

    # ── 类方法：注册 / 查询适配器 ──

    @classmethod
    def register_adapter(cls, provider: ModelProvider, adapter_cls: type) -> None:
        """注册新的协议适配器（插件化扩展点）"""
        if not issubclass(adapter_cls, BaseModelAdapter):
            raise TypeError(f"{adapter_cls} 必须继承 BaseModelAdapter")
        cls._ADAPTER_REGISTRY[provider] = adapter_cls

    @classmethod
    def get_adapter_class(cls, provider: ModelProvider) -> Optional[type]:
        return cls._ADAPTER_REGISTRY.get(provider)

    @staticmethod
    def _detect_provider(endpoint_url: str) -> ModelProvider:
        """
        根据 endpoint URL 自动检测协议类型。
        规则：
        - 含 'ollama' 或端口 11434 → OLLAMA
        - 其余 → OPENAI（默认）
        """
        ep_lower = endpoint_url.lower()
        if "ollama" in ep_lower or ":11434" in ep_lower:
            return ModelProvider.OLLAMA
        return ModelProvider.OPENAI

    @staticmethod
    def _resolve_provider(endpoint: ModelEndpoint) -> ModelProvider:
        """
        解析最终使用的 provider：优先取显式配置，否则自动检测。
        """
        if endpoint.provider is not None:
            return endpoint.provider
        return ModelLayerRouter._detect_provider(endpoint.endpoint)

    # ── 模型注册 ──

    def register_model(self, endpoint: ModelEndpoint) -> str:
        provider = self._resolve_provider(endpoint)
        adapter_cls = self._ADAPTER_REGISTRY.get(provider)
        if adapter_cls is None:
            raise ValueError(
                f"未知的 provider '{provider}'，已注册: {list(self._ADAPTER_REGISTRY.keys())}"
            )

        adapter = adapter_cls(endpoint)

        self._adapters[endpoint.model_id] = adapter
        self._layers[endpoint.layer].append(endpoint.model_id)
        self._roles[endpoint.role].append(endpoint.model_id)

        if endpoint.layer == ModelLayer.BASIC:
            if (
                self._basic_model_id is None
                or endpoint.priority
                < self._get_adapter(self._basic_model_id).endpoint.priority
            ):
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
            self._basic_model_id = (
                self._layers[ModelLayer.BASIC][0]
                if self._layers[ModelLayer.BASIC]
                else None
            )

        return True

    def _get_adapter(self, model_id: str) -> Optional[BaseModelAdapter]:
        return self._adapters.get(model_id)

    def get_available_adapter(
        self, layer: ModelLayer, role: ModelRole = None
    ) -> Optional[BaseModelAdapter]:
        if role:
            # Role 优先：忽略 _busy（远程 API 能处理并发请求），不 fall-through 到 layer
            for model_id in self._roles[role]:
                adapter = self._adapters.get(model_id)
                if adapter and adapter.endpoint.enabled:
                    return adapter
            return None

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

    async def should_use_special(
        self, message: str, context: Dict = None
    ) -> Optional[ModelRole]:
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
                temperature=0.1,
            )

            result = json.loads(response.content)
            if result.get("need_special"):
                role_str = result.get("special_role")
                if role_str:
                    return ModelRole(role_str)
        except Exception as e:
            logger.debug(f"should_use_special 解析失败: {e}")

        return None

    def route(
        self, message: str, has_image: bool = False, prefer_role: ModelRole = None
    ) -> Optional[BaseModelAdapter]:
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
        **kwargs,
    ) -> ModelResponse:
        if prefer_model and prefer_model in self._adapters:
            adapter = self._adapters[prefer_model]
            if adapter.is_available:
                return await adapter.chat(messages, system_prompt, tools, **kwargs)

        last_message = messages[-1]["content"] if messages else ""
        has_image = any(isinstance(m.get("content"), list) for m in messages)

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
                latency_ms=0,
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
Think through problems methodically.""",
        }
        return role_prompts.get(role, "You are a specialized assistant.")

    async def chat_stream(
        self,
        messages: List[Dict],
        system_prompt: str = None,
        prefer_model: str = None,
        prefer_role: ModelRole = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        if prefer_model and prefer_model in self._adapters:
            adapter = self._adapters[prefer_model]
            if adapter.is_available:
                async for chunk in adapter.chat_stream(
                    messages, system_prompt, **kwargs
                ):
                    yield chunk
                return

        last_message = messages[-1]["content"] if messages else ""
        has_image = any(isinstance(m.get("content"), list) for m in messages)

        adapter = self.route(last_message, has_image, prefer_role)

        if not adapter:
            yield "抱歉，所有模型都忙不过来了，请稍后再试~"
            return

        async for chunk in adapter.chat_stream(messages, system_prompt, **kwargs):
            yield chunk

    async def parallel_chat(
        self, messages_list: List[List[Dict]], system_prompt: str = None, **kwargs
    ) -> List[ModelResponse]:
        tasks = [
            self.chat(messages, system_prompt, **kwargs) for messages in messages_list
        ]
        return await asyncio.gather(*tasks)

    def get_status(self) -> Dict:
        status = {"layers": {}, "models": [], "basic_model": self._basic_model_id}

        for layer in ModelLayer:
            models = []
            for model_id in self._layers[layer]:
                adapter = self._adapters.get(model_id)
                if adapter:
                    models.append(
                        {
                            "model_id": model_id,
                            "model_name": adapter.endpoint.model_name,
                            "role": adapter.endpoint.role.value,
                            "available": adapter.is_available,
                            "avg_latency_ms": adapter.avg_latency,
                        }
                    )
            status["layers"][layer.value] = {"count": len(models), "models": models}

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
