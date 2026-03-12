"""
XiaoMengCore v2 - 消息队列系统

参考 OpenClaw 的队列模式：
- STEER: 打断当前任务，立即处理新消息
- FOLLOWUP: 追加到队列末尾
- COLLECT: 收集多条消息后一起处理
- INTERRUPT: 中断当前运行
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime
from pathlib import Path
import asyncio
import json
from collections import deque

from .identity import Identity, Platform


class QueueMode(Enum):
    STEER = "steer"
    FOLLOWUP = "followup"
    COLLECT = "collect"
    STEER_BACKLOG = "steer-backlog"
    STEER_PLUS_BACKLOG = "steer+backlog"
    QUEUE = "queue"
    INTERRUPT = "interrupt"


class GroupActivation(Enum):
    MENTION = "mention"
    ALWAYS = "always"


@dataclass
class QueuedMessage:
    message_id: str
    content: str
    platform: Platform
    platform_user_id: str
    identity: Optional[Identity]
    session_key: str
    queue_mode: QueueMode
    queued_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "content": self.content,
            "platform": self.platform.value,
            "platform_user_id": self.platform_user_id,
            "identity_id": self.identity.identity_id if self.identity else None,
            "session_key": self.session_key,
            "queue_mode": self.queue_mode.value,
            "queued_at": self.queued_at.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class SessionLane:
    session_key: str
    queue: deque = field(default_factory=deque)
    current_run_id: Optional[str] = None
    current_task: Optional[asyncio.Task] = None
    is_processing: bool = False
    last_message_at: Optional[datetime] = None
    
    def __post_init__(self):
        self.queue = deque()


class MessageQueue:
    """
    消息队列管理器
    
    每个会话一个队列，支持多种队列模式
    """
    
    _instance: Optional["MessageQueue"] = None
    
    def __init__(self):
        self._lanes: Dict[str, SessionLane] = {}
        self._global_queue: deque = deque()
        self._global_processing = False
        self._collect_buffers: Dict[str, List[QueuedMessage]] = {}
        self._collect_timers: Dict[str, asyncio.Task] = {}
        self._handlers: Dict[str, Callable] = {}
    
    @classmethod
    def get_instance(cls) -> "MessageQueue":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register_handler(self, name: str, handler: Callable[[QueuedMessage], Awaitable[Any]]):
        self._handlers[name] = handler
    
    def _get_or_create_lane(self, session_key: str) -> SessionLane:
        if session_key not in self._lanes:
            self._lanes[session_key] = SessionLane(session_key=session_key)
        return self._lanes[session_key]
    
    async def enqueue(
        self,
        content: str,
        platform: Platform,
        platform_user_id: str,
        identity: Optional[Identity],
        session_key: str,
        queue_mode: QueueMode = QueueMode.FOLLOWUP,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        将消息加入队列
        
        根据队列模式决定如何处理：
        - STEER: 打断当前任务
        - FOLLOWUP: 追加到队列
        - COLLECT: 收集后批量处理
        """
        import uuid
        message_id = f"msg_{uuid.uuid4().hex[:8]}"
        
        message = QueuedMessage(
            message_id=message_id,
            content=content,
            platform=platform,
            platform_user_id=platform_user_id,
            identity=identity,
            session_key=session_key,
            queue_mode=queue_mode,
            metadata=metadata or {}
        )
        
        lane = self._get_or_create_lane(session_key)
        
        if queue_mode == QueueMode.STEER:
            await self._handle_steer(lane, message)
        elif queue_mode == QueueMode.INTERRUPT:
            await self._handle_interrupt(lane, message)
        elif queue_mode == QueueMode.COLLECT:
            await self._handle_collect(lane, message)
        else:
            lane.queue.append(message)
        
        lane.last_message_at = datetime.now()
        
        if not lane.is_processing:
            asyncio.create_task(self._process_lane(lane))
        
        return message_id
    
    async def _handle_steer(self, lane: SessionLane, message: QueuedMessage):
        if lane.current_task and not lane.current_task.done():
            lane.current_task.cancel()
            try:
                await lane.current_task
            except asyncio.CancelledError:
                pass
        
        lane.queue.appendleft(message)
    
    async def _handle_interrupt(self, lane: SessionLane, message: QueuedMessage):
        lane.queue.clear()
        
        if lane.current_task and not lane.current_task.done():
            lane.current_task.cancel()
            try:
                await lane.current_task
            except asyncio.CancelledError:
                pass
        
        lane.queue.append(message)
    
    async def _handle_collect(self, lane: SessionLane, message: QueuedMessage):
        buffer_key = lane.session_key
        
        if buffer_key not in self._collect_buffers:
            self._collect_buffers[buffer_key] = []
            self._collect_timers[buffer_key] = asyncio.create_task(
                self._collect_timeout(buffer_key, lane)
            )
        
        self._collect_buffers[buffer_key].append(message)
    
    async def _collect_timeout(self, buffer_key: str, lane: SessionLane):
        await asyncio.sleep(2.0)
        
        if buffer_key in self._collect_buffers:
            messages = self._collect_buffers.pop(buffer_key)
            self._collect_timers.pop(buffer_key, None)
            
            if messages:
                combined_content = "\n---\n".join(m.content for m in messages)
                combined_message = QueuedMessage(
                    message_id=messages[-1].message_id,
                    content=combined_content,
                    platform=messages[-1].platform,
                    platform_user_id=messages[-1].platform_user_id,
                    identity=messages[-1].identity,
                    session_key=lane.session_key,
                    queue_mode=QueueMode.FOLLOWUP,
                    metadata={"collected_count": len(messages)}
                )
                lane.queue.append(combined_message)
                
                if not lane.is_processing:
                    asyncio.create_task(self._process_lane(lane))
    
    async def _process_lane(self, lane: SessionLane):
        if lane.is_processing:
            return
        
        lane.is_processing = True
        
        try:
            while lane.queue:
                message = lane.queue.popleft()
                
                handler = self._handlers.get("default")
                if handler:
                    try:
                        lane.current_run_id = message.message_id
                        lane.current_task = asyncio.create_task(
                            handler(message)
                        )
                        await lane.current_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        print(f"处理消息失败: {e}")
                    finally:
                        lane.current_run_id = None
                        lane.current_task = None
        finally:
            lane.is_processing = False
    
    def get_queue_status(self, session_key: str) -> Dict[str, Any]:
        lane = self._lanes.get(session_key)
        if not lane:
            return {"queue_length": 0, "is_processing": False}
        
        return {
            "session_key": session_key,
            "queue_length": len(lane.queue),
            "is_processing": lane.is_processing,
            "current_run_id": lane.current_run_id,
            "last_message_at": lane.last_message_at.isoformat() if lane.last_message_at else None
        }
    
    def get_all_status(self) -> List[Dict[str, Any]]:
        return [self.get_queue_status(key) for key in self._lanes]
    
    async def abort_run(self, session_key: str, run_id: str) -> bool:
        lane = self._lanes.get(session_key)
        if not lane:
            return False
        
        if lane.current_run_id == run_id and lane.current_task:
            lane.current_task.cancel()
            return True
        
        return False
