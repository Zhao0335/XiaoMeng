"""
XiaoMengCore LLM 客户端
支持 DeepSeek 和其他 OpenAI 兼容的 API，集成多模型路由
"""

from typing import Optional, Dict, List, Any, AsyncGenerator
import asyncio
import json

from config import XiaoMengConfig, ConfigManager


class LLMClient:
    """
    LLM 客户端
    
    支持：
    - DeepSeek API
    - OpenAI 兼容 API
    - 流式输出
    - 工具调用
    - 多模型路由
    """
    
    _instance: Optional["LLMClient"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[XiaoMengConfig] = None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self._config = config or ConfigManager.get_instance().get()
        self._client = None
        self._model_router = None
        self._use_router = False
        self._init_client()
        self._initialized = True
    
    def _init_client(self):
        """初始化客户端"""
        try:
            from openai import AsyncOpenAI
            
            self._client = AsyncOpenAI(
                api_key=self._config.llm.api_key,
                base_url=self._config.llm.base_url
            )
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
    
    def enable_router(self, models_config: List[Dict] = None):
        """
        启用多模型路由
        
        models_config: 模型配置列表
        [
            {
                "model_type": "7b",
                "model_name": "qwen2.5:7b",
                "endpoint": "http://localhost:11434/v1",
                "enabled": True
            },
            {
                "model_type": "70b",
                "model_name": "deepseek-chat",
                "endpoint": "https://api.deepseek.com/v1",
                "api_key": "xxx",
                "enabled": True
            }
        ]
        """
        from .model_router import ModelRouter, ModelConfig, ModelType
        
        self._model_router = ModelRouter.get_instance()
        
        if models_config:
            for model_cfg in models_config:
                model_type = ModelType(model_cfg.get("model_type", "7b"))
                config = ModelConfig(
                    model_type=model_type,
                    model_name=model_cfg["model_name"],
                    endpoint=model_cfg["endpoint"],
                    api_key=model_cfg.get("api_key"),
                    max_tokens=model_cfg.get("max_tokens", 4096),
                    temperature=model_cfg.get("temperature", 0.7),
                    enabled=model_cfg.get("enabled", True)
                )
                self._model_router.register_model(config)
        
        self._use_router = True
    
    def disable_router(self):
        """禁用多模型路由"""
        self._use_router = False
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        prefer_model: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送聊天请求
        
        参数:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            system_prompt: 系统提示
            tools: 工具列表
            prefer_model: 首选模型类型 ("7b", "70b", "vlm")
            **kwargs: 其他参数
        
        返回:
            {
                "content": "回复内容",
                "tool_calls": [...],
                "usage": {...}
            }
        """
        if self._use_router and self._model_router:
            from .model_router import ModelType, TaskPriority
            
            prefer = ModelType(prefer_model) if prefer_model else None
            priority = kwargs.pop("priority", TaskPriority.INTERACTIVE)
            
            response = await self._model_router.chat(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                prefer_model=prefer,
                priority=priority,
                **kwargs
            )
            
            return {
                "content": response.content,
                "tool_calls": response.tool_calls,
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": response.token_count,
                    "total_tokens": response.token_count
                },
                "model": response.model_name,
                "latency_ms": response.latency_ms
            }
        
        return await self._chat_direct(messages, system_prompt, tools, **kwargs)
    
    async def _chat_direct(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """直接调用单一模型"""
        full_messages = []
        
        if system_prompt:
            full_messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        full_messages.extend(messages)
        
        request_params = {
            "model": self._config.llm.model,
            "messages": full_messages,
            "max_tokens": kwargs.get("max_tokens", self._config.llm.max_tokens),
            "temperature": kwargs.get("temperature", self._config.llm.temperature),
        }
        
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"
        
        response = await self._client.chat.completions.create(**request_params)
        
        result = {
            "content": response.choices[0].message.content or "",
            "tool_calls": [],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
        
        if response.choices[0].message.tool_calls:
            for tc in response.choices[0].message.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
        
        return result
    
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        prefer_model: str = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天
        
        生成器，逐字返回内容
        """
        if self._use_router and self._model_router:
            from .model_router import ModelType, TaskPriority
            
            prefer = ModelType(prefer_model) if prefer_model else None
            
            async for chunk in self._model_router.chat_stream(
                messages=messages,
                system_prompt=system_prompt,
                prefer_model=prefer,
                **kwargs
            ):
                yield chunk
            return
        
        full_messages = []
        
        if system_prompt:
            full_messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        full_messages.extend(messages)
        
        stream = await self._client.chat.completions.create(
            model=self._config.llm.model,
            messages=full_messages,
            max_tokens=kwargs.get("max_tokens", self._config.llm.max_tokens),
            temperature=kwargs.get("temperature", self._config.llm.temperature),
            stream=True
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def chat_with_context(
        self,
        user_message: str,
        context: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        带上下文的聊天
        
        参数:
            user_message: 用户消息
            context: 上下文消息列表
            system_prompt: 系统提示
        """
        messages = context + [{"role": "user", "content": user_message}]
        return await self.chat(messages, system_prompt, **kwargs)
    
    def update_config(self, config: XiaoMengConfig):
        """更新配置"""
        self._config = config
        self._init_client()
    
    def get_router_status(self) -> Optional[Dict]:
        """获取路由器状态"""
        if self._model_router:
            return self._model_router.get_status()
        return None
    
    @classmethod
    def get_instance(cls) -> "LLMClient":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
