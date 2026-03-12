"""
XiaoMengCore 核心数据模型
兼容 OpenClaw 人设记忆系统
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import uuid
import json


class Source(Enum):
    """消息来源平台"""
    QQ = "qq"
    WEB = "web"
    DESKTOP = "desktop"
    CLI = "cli"


class UserLevel(Enum):
    """用户身份等级"""
    OWNER = "owner"
    WHITELIST = "whitelist"
    STRANGER = "stranger"


class MessageType(Enum):
    """消息类型"""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    FILE = "file"
    COMMAND = "command"


class Emotion(Enum):
    """情感标签"""
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    NEUTRAL = "neutral"
    EXCITED = "excited"
    SHY = "shy"
    WORRIED = "worried"
    CARING = "caring"


@dataclass
class ChannelIdentity:
    """渠道身份 - 用于标识用户在不同平台的身份"""
    source: Source
    channel_user_id: str
    display_name: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "source": self.source.value,
            "channel_user_id": self.channel_user_id,
            "display_name": self.display_name
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ChannelIdentity":
        return cls(
            source=Source(data["source"]),
            channel_user_id=data["channel_user_id"],
            display_name=data.get("display_name")
        )
    
    @property
    def unique_key(self) -> str:
        """生成唯一标识键"""
        return f"{self.source.value}:{self.channel_user_id}"


@dataclass
class User:
    """用户信息"""
    user_id: str
    level: UserLevel
    identities: List[ChannelIdentity] = field(default_factory=list)
    nickname: Optional[str] = None
    whitelist_since: Optional[datetime] = None
    preferences: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "level": self.level.value,
            "identities": [i.to_dict() for i in self.identities],
            "nickname": self.nickname,
            "whitelist_since": self.whitelist_since.isoformat() if self.whitelist_since else None,
            "preferences": self.preferences,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "User":
        return cls(
            user_id=data["user_id"],
            level=UserLevel(data["level"]),
            identities=[ChannelIdentity.from_dict(i) for i in data.get("identities", [])],
            nickname=data.get("nickname"),
            whitelist_since=datetime.fromisoformat(data["whitelist_since"]) if data.get("whitelist_since") else None,
            preferences=data.get("preferences", {}),
            metadata=data.get("metadata", {})
        )
    
    def get_identity_for_source(self, source: Source) -> Optional[ChannelIdentity]:
        """获取指定平台的身份"""
        for identity in self.identities:
            if identity.source == source:
                return identity
        return None
    
    def has_identity(self, source: Source, channel_user_id: str) -> bool:
        """检查是否拥有指定身份"""
        for identity in self.identities:
            if identity.source == source and identity.channel_user_id == channel_user_id:
                return True
        return False


@dataclass
class Message:
    """统一消息格式"""
    message_id: str
    source: Source
    user: User
    content: str
    timestamp: datetime
    message_type: MessageType = MessageType.TEXT
    reply_to: Optional[str] = None
    emotion: Optional[Emotion] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)
    
    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "source": self.source.value,
            "user": self.user.to_dict(),
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "message_type": self.message_type.value,
            "reply_to": self.reply_to,
            "emotion": self.emotion.value if self.emotion else None,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Message":
        return cls(
            message_id=data["message_id"],
            source=Source(data["source"]),
            user=User.from_dict(data["user"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            message_type=MessageType(data.get("message_type", "text")),
            reply_to=data.get("reply_to"),
            emotion=Emotion(data["emotion"]) if data.get("emotion") else None,
            metadata=data.get("metadata", {})
        )
    
    @classmethod
    def create(cls, source: Source, user: User, content: str, **kwargs) -> "Message":
        """创建新消息"""
        return cls(
            message_id=str(uuid.uuid4()),
            source=source,
            user=user,
            content=content,
            timestamp=datetime.now(),
            **kwargs
        )


@dataclass
class Response:
    """AI 回复"""
    message_id: str
    reply_to: str
    content: str
    emotion: Emotion
    timestamp: datetime = field(default_factory=datetime.now)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "reply_to": self.reply_to,
            "content": self.content,
            "emotion": self.emotion.value,
            "timestamp": self.timestamp.isoformat(),
            "tool_calls": self.tool_calls,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Response":
        return cls(
            message_id=data["message_id"],
            reply_to=data["reply_to"],
            content=data["content"],
            emotion=Emotion(data["emotion"]),
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"],
            tool_calls=data.get("tool_calls", []),
            metadata=data.get("metadata", {})
        )
    
    @classmethod
    def create(cls, reply_to: str, content: str, emotion: Emotion = Emotion.NEUTRAL, **kwargs) -> "Response":
        """创建新回复"""
        return cls(
            message_id=str(uuid.uuid4()),
            reply_to=reply_to,
            content=content,
            emotion=emotion,
            **kwargs
        )


@dataclass
class Session:
    """会话 - 支持多渠道身份共享，完全兼容 OpenClaw SessionEntry"""
    session_id: str
    user: User
    created_at: datetime
    updated_at: datetime
    history: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    active_sources: List[Source] = field(default_factory=list)
    
    last_heartbeat_text: Optional[str] = None
    last_heartbeat_sent_at: Optional[datetime] = None
    session_file: Optional[str] = None
    spawned_by: Optional[str] = None
    spawn_depth: int = 0
    system_sent: bool = False
    aborted_last_run: bool = False
    chat_type: Optional[str] = None
    thinking_level: Optional[str] = None
    verbose_level: Optional[str] = None
    reasoning_level: Optional[str] = None
    elevated_level: Optional[str] = None
    tts_auto: Optional[str] = None
    exec_host: Optional[str] = None
    exec_security: Optional[str] = None
    exec_ask: Optional[str] = None
    exec_node: Optional[str] = None
    response_usage: Optional[str] = None
    provider_override: Optional[str] = None
    model_override: Optional[str] = None
    auth_profile_override: Optional[str] = None
    auth_profile_override_source: Optional[str] = None
    auth_profile_override_compaction_count: int = 0
    group_activation: Optional[str] = None
    group_activation_needs_system_intro: bool = False
    send_policy: str = "allow"
    queue_mode: Optional[str] = None
    queue_debounce_ms: Optional[int] = None
    queue_cap: Optional[int] = None
    queue_drop: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_tokens_fresh: Optional[bool] = None
    model_provider: Optional[str] = None
    model: Optional[str] = None
    context_tokens: int = 0
    compaction_count: int = 0
    memory_flush_at: Optional[datetime] = None
    memory_flush_compaction_count: int = 0
    cli_session_ids: Dict[str, str] = field(default_factory=dict)
    claude_cli_session_id: Optional[str] = None
    label: Optional[str] = None
    display_name: Optional[str] = None
    channel: Optional[str] = None
    group_id: Optional[str] = None
    subject: Optional[str] = None
    group_channel: Optional[str] = None
    space: Optional[str] = None
    origin: Dict[str, Any] = field(default_factory=dict)
    delivery_context: Dict[str, Any] = field(default_factory=dict)
    last_channel: Optional[str] = None
    last_to: Optional[str] = None
    last_account_id: Optional[str] = None
    last_thread_id: Optional[str] = None
    skills_snapshot: Dict[str, Any] = field(default_factory=dict)
    system_prompt_report: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "user": self.user.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "history": [m.to_dict() for m in self.history],
            "context": self.context,
            "active_sources": [s.value for s in self.active_sources],
            "lastHeartbeatText": self.last_heartbeat_text,
            "lastHeartbeatSentAt": self.last_heartbeat_sent_at.isoformat() if self.last_heartbeat_sent_at else None,
            "sessionFile": self.session_file,
            "spawnedBy": self.spawned_by,
            "spawnDepth": self.spawn_depth,
            "systemSent": self.system_sent,
            "abortedLastRun": self.aborted_last_run,
            "chatType": self.chat_type,
            "thinkingLevel": self.thinking_level,
            "verboseLevel": self.verbose_level,
            "reasoningLevel": self.reasoning_level,
            "elevatedLevel": self.elevated_level,
            "ttsAuto": self.tts_auto,
            "execHost": self.exec_host,
            "execSecurity": self.exec_security,
            "execAsk": self.exec_ask,
            "execNode": self.exec_node,
            "responseUsage": self.response_usage,
            "providerOverride": self.provider_override,
            "modelOverride": self.model_override,
            "authProfileOverride": self.auth_profile_override,
            "authProfileOverrideSource": self.auth_profile_override_source,
            "authProfileOverrideCompactionCount": self.auth_profile_override_compaction_count,
            "groupActivation": self.group_activation,
            "groupActivationNeedsSystemIntro": self.group_activation_needs_system_intro,
            "sendPolicy": self.send_policy,
            "queueMode": self.queue_mode,
            "queueDebounceMs": self.queue_debounce_ms,
            "queueCap": self.queue_cap,
            "queueDrop": self.queue_drop,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "totalTokens": self.total_tokens,
            "totalTokensFresh": self.total_tokens_fresh,
            "modelProvider": self.model_provider,
            "model": self.model,
            "contextTokens": self.context_tokens,
            "compactionCount": self.compaction_count,
            "memoryFlushAt": self.memory_flush_at.isoformat() if self.memory_flush_at else None,
            "memoryFlushCompactionCount": self.memory_flush_compaction_count,
            "cliSessionIds": self.cli_session_ids,
            "claudeCliSessionId": self.claude_cli_session_id,
            "label": self.label,
            "displayName": self.display_name,
            "channel": self.channel,
            "groupId": self.group_id,
            "subject": self.subject,
            "groupChannel": self.group_channel,
            "space": self.space,
            "origin": self.origin,
            "deliveryContext": self.delivery_context,
            "lastChannel": self.last_channel,
            "lastTo": self.last_to,
            "lastAccountId": self.last_account_id,
            "lastThreadId": self.last_thread_id,
            "skillsSnapshot": self.skills_snapshot,
            "systemPromptReport": self.system_prompt_report
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Session":
        return cls(
            session_id=data["session_id"],
            user=User.from_dict(data["user"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            history=[Message.from_dict(m) for m in data.get("history", [])],
            context=data.get("context", {}),
            active_sources=[Source(s) for s in data.get("active_sources", [])],
            last_heartbeat_text=data.get("lastHeartbeatText"),
            last_heartbeat_sent_at=datetime.fromisoformat(data["lastHeartbeatSentAt"]) if data.get("lastHeartbeatSentAt") else None,
            session_file=data.get("sessionFile"),
            spawned_by=data.get("spawnedBy"),
            spawn_depth=data.get("spawnDepth", 0),
            system_sent=data.get("systemSent", False),
            aborted_last_run=data.get("abortedLastRun", False),
            chat_type=data.get("chatType"),
            thinking_level=data.get("thinkingLevel"),
            verbose_level=data.get("verboseLevel"),
            reasoning_level=data.get("reasoningLevel"),
            elevated_level=data.get("elevatedLevel"),
            tts_auto=data.get("ttsAuto"),
            exec_host=data.get("execHost"),
            exec_security=data.get("execSecurity"),
            exec_ask=data.get("execAsk"),
            exec_node=data.get("execNode"),
            response_usage=data.get("responseUsage"),
            provider_override=data.get("providerOverride"),
            model_override=data.get("modelOverride"),
            auth_profile_override=data.get("authProfileOverride"),
            auth_profile_override_source=data.get("authProfileOverrideSource"),
            auth_profile_override_compaction_count=data.get("authProfileOverrideCompactionCount", 0),
            group_activation=data.get("groupActivation"),
            group_activation_needs_system_intro=data.get("groupActivationNeedsSystemIntro", False),
            send_policy=data.get("sendPolicy", "allow"),
            queue_mode=data.get("queueMode"),
            queue_debounce_ms=data.get("queueDebounceMs"),
            queue_cap=data.get("queueCap"),
            queue_drop=data.get("queueDrop"),
            input_tokens=data.get("inputTokens", 0),
            output_tokens=data.get("outputTokens", 0),
            total_tokens=data.get("totalTokens", 0),
            total_tokens_fresh=data.get("totalTokensFresh"),
            model_provider=data.get("modelProvider"),
            model=data.get("model"),
            context_tokens=data.get("contextTokens", 0),
            compaction_count=data.get("compactionCount", 0),
            memory_flush_at=datetime.fromisoformat(data["memoryFlushAt"]) if data.get("memoryFlushAt") else None,
            memory_flush_compaction_count=data.get("memoryFlushCompactionCount", 0),
            cli_session_ids=data.get("cliSessionIds", {}),
            claude_cli_session_id=data.get("claudeCliSessionId"),
            label=data.get("label"),
            display_name=data.get("displayName"),
            channel=data.get("channel"),
            group_id=data.get("groupId"),
            subject=data.get("subject"),
            group_channel=data.get("groupChannel"),
            space=data.get("space"),
            origin=data.get("origin", {}),
            delivery_context=data.get("deliveryContext", {}),
            last_channel=data.get("lastChannel"),
            last_to=data.get("lastTo"),
            last_account_id=data.get("lastAccountId"),
            last_thread_id=data.get("lastThreadId"),
            skills_snapshot=data.get("skillsSnapshot", {}),
            system_prompt_report=data.get("systemPromptReport", {})
        )
    
    @classmethod
    def create(cls, user: User) -> "Session":
        """创建新会话"""
        now = datetime.now()
        return cls(
            session_id=str(uuid.uuid4()),
            user=user,
            created_at=now,
            updated_at=now
        )
    
    def add_message(self, message: Message):
        """添加消息到历史"""
        self.history.append(message)
        self.updated_at = datetime.now()
        if message.source not in self.active_sources:
            self.active_sources.append(message.source)
    
    def get_recent_history(self, limit: int = 20) -> List[Message]:
        """获取最近的消息历史"""
        return self.history[-limit:] if self.history else []
    
    def update_tokens(self, input_tokens: int, output_tokens: int):
        """更新 Token 统计"""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.total_tokens_fresh = True
    
    def increment_compaction(self):
        """增加压缩计数"""
        self.compaction_count += 1


class QueueMode(Enum):
    """队列模式 - 参考 OpenClaw queueMode"""
    STEER = "steer"
    FOLLOWUP = "followup"
    COLLECT = "collect"
    STEER_BACKLOG = "steer-backlog"
    STEER_PLUS_BACKLOG = "steer+backlog"
    QUEUE = "queue"
    INTERRUPT = "interrupt"


class GroupActivation(Enum):
    """群组激活模式 - 参考 OpenClaw groupActivation"""
    MENTION = "mention"
    ALWAYS = "always"


class SendPolicy(Enum):
    """发送策略 - 参考 OpenClaw sendPolicy"""
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class MemoryEntry:
    """记忆条目 - 兼容 OpenClaw 格式"""
    entry_id: str
    content: str
    timestamp: datetime
    source: Optional[Source] = None
    importance: int = 1
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "entry_id": self.entry_id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source.value if self.source else None,
            "importance": self.importance,
            "tags": self.tags,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MemoryEntry":
        return cls(
            entry_id=data["entry_id"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=Source(data["source"]) if data.get("source") else None,
            importance=data.get("importance", 1),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {})
        )
    
    def to_markdown(self) -> str:
        """转换为 Markdown 格式（兼容 OpenClaw）"""
        time_str = self.timestamp.strftime("%Y-%m-%d %H:%M")
        tags_str = " ".join([f"#{t}" for t in self.tags]) if self.tags else ""
        return f"- [{time_str}] {self.content} {tags_str}".strip()
    
    @classmethod
    def from_markdown_line(cls, line: str) -> Optional["MemoryEntry"]:
        """从 Markdown 行解析"""
        import re
        pattern = r"- \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] (.+)"
        match = re.match(pattern, line)
        if match:
            timestamp_str, content = match.groups()
            tags = re.findall(r"#(\w+)", content)
            content_clean = re.sub(r"#\w+", "", content).strip()
            return cls(
                entry_id=str(uuid.uuid4()),
                content=content_clean,
                timestamp=datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M"),
                tags=tags
            )
        return None


@dataclass
class PersonaConfig:
    """
    人设配置 - 完全兼容 OpenClaw 核心文件
    
    OpenClaw 工作区核心文件结构：
    - SOUL.md: 人格定义（核心人格、性格特点、说话风格）
    - AGENTS.md: 行为规范（如何与不同用户交互、操作流程）
    - IDENTITY.md: 身份信息（名字、背景、能力、emoji风格）
    - USER.md: 用户信息（主人的信息、如何称谓用户）
    - TOOLS.md: 工具环境（可用工具说明）
    - MEMORY.md: 长期记忆（重要记忆、持久事实）
    - HEARTBEAT.md: 心跳任务（定时任务、主动行为）
    - BOOTSTRAP.md: 引导文件（首次初始化引导，完成后可删除）
    """
    soul: str = ""
    agents: str = ""
    identity: str = ""
    user_info: str = ""
    tools: str = ""
    memory: str = ""
    heartbeat: str = ""
    bootstrap: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "soul": self.soul,
            "agents": self.agents,
            "identity": self.identity,
            "user_info": self.user_info,
            "tools": self.tools,
            "memory": self.memory,
            "heartbeat": self.heartbeat,
            "bootstrap": self.bootstrap
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PersonaConfig":
        return cls(
            soul=data.get("soul", ""),
            agents=data.get("agents", ""),
            identity=data.get("identity", ""),
            user_info=data.get("user_info", ""),
            tools=data.get("tools", ""),
            memory=data.get("memory", ""),
            heartbeat=data.get("heartbeat", ""),
            bootstrap=data.get("bootstrap", "")
        )
    
    def get_system_prompt(
        self, 
        user_level: UserLevel, 
        include_tools: bool = True, 
        include_bootstrap: bool = False,
        is_group: bool = False
    ) -> str:
        """
        根据 OpenClaw 格式生成系统提示
        
        OpenClaw 核心文件加载顺序：
        1. SOUL.md - 人格定义（核心人格、性格特点）
        2. IDENTITY.md - 身份信息（名字、背景、能力）
        3. AGENTS.md - 行为规范（如何与不同用户交互）
        4. USER.md - 用户信息（仅主人可见）
        5. MEMORY.md - 长期记忆（仅主人私聊可见）
        6. TOOLS.md - 工具环境（仅主人可见）
        7. HEARTBEAT.md - 心跳任务（仅主人可见）
        8. BOOTSTRAP.md - 引导文件（仅首次初始化时加载）
        
        参考：OpenClaw workspace.ts loadWorkspaceBootstrapFiles()
        
        Args:
            user_level: 用户等级
            include_tools: 是否包含工具说明
            include_bootstrap: 是否包含引导文件
            is_group: 是否群聊（群聊时某些内容不加载）
        """
        parts = []
        
        if self.soul:
            parts.append(self.soul)
        
        if self.identity:
            parts.append(self.identity)
        
        if self.agents:
            parts.append(self.agents)
        
        if user_level == UserLevel.OWNER:
            if self.user_info:
                parts.append(self.user_info)
            
            if self.memory and not is_group:
                parts.append(self.memory)
        
        if include_tools and self.tools and user_level == UserLevel.OWNER:
            parts.append(self.tools)
        
        if self.heartbeat and user_level == UserLevel.OWNER and not is_group:
            parts.append(self.heartbeat)
        
        if include_bootstrap and self.bootstrap:
            parts.append(self.bootstrap)
        
        return "\n\n---\n\n".join(parts)
    
    def get_full_prompt(self) -> str:
        """获取完整提示（用于调试）"""
        return self.get_system_prompt(UserLevel.OWNER, include_tools=True, include_bootstrap=True)
    
    def get_bootstrap_prompt(self) -> str:
        """获取引导提示（用于首次初始化）"""
        if self.bootstrap:
            return self.bootstrap
        return ""
    
    def is_onboarding_complete(self) -> bool:
        """检查引导是否完成（BOOTSTRAP.md 为空表示已完成）"""
        return not self.bootstrap or self.bootstrap.strip() == ""
