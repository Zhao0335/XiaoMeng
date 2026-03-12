"""
XiaoMengCore 会话管理器
支持多渠道身份共享会话
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pathlib import Path
import json
import asyncio
from dataclasses import dataclass, field

from models import User, Session, Message, Source
from config import XiaoMengConfig, ConfigManager


@dataclass
class SessionStats:
    """会话统计"""
    total_messages: int = 0
    total_sessions: int = 0
    active_sessions: int = 0
    last_activity: Optional[datetime] = None


class SessionManager:
    """
    会话管理器
    
    核心功能：
    1. 多渠道共享会话 - 同一用户在不同平台的会话共享
    2. 会话超时管理 - 自动清理过期会话
    3. 历史记录管理 - 限制历史长度，自动保存
    """
    
    _instance: Optional["SessionManager"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[XiaoMengConfig] = None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        
        self._config = config or ConfigManager.get_instance().get()
        self._data_dir = Path(self._config.data_dir) / "sessions"
        self._sessions_file = self._data_dir / "sessions.json"
        
        self._sessions: Dict[str, Session] = {}
        self._user_session_map: Dict[str, str] = {}
        
        self._stats = SessionStats()
        self._auto_save_task: Optional[asyncio.Task] = None
        
        self._load()
        self._initialized = True
    
    def _load(self):
        """加载会话数据"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        if self._sessions_file.exists():
            with open(self._sessions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._sessions = {
                    sid: Session.from_dict(s) 
                    for sid, s in data.get("sessions", {}).items()
                }
                self._user_session_map = data.get("user_session_map", {})
                self._stats.total_sessions = len(self._sessions)
    
    def _save(self):
        """保存会话数据"""
        data = {
            "sessions": {sid: s.to_dict() for sid, s in self._sessions.items()},
            "user_session_map": self._user_session_map,
            "stats": {
                "total_messages": self._stats.total_messages,
                "total_sessions": self._stats.total_sessions,
                "last_activity": self._stats.last_activity.isoformat() if self._stats.last_activity else None
            }
        }
        with open(self._sessions_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_or_create_session(self, user: User) -> Session:
        """
        获取或创建用户会话
        
        关键：同一个 user_id 在任何渠道都返回同一个会话
        """
        user_id = user.user_id
        
        if user_id in self._user_session_map:
            session_id = self._user_session_map[user_id]
            if session_id in self._sessions:
                session = self._sessions[session_id]
                if not self._is_session_expired(session):
                    return session
        
        session = Session.create(user)
        self._sessions[session.session_id] = session
        self._user_session_map[user_id] = session.session_id
        self._stats.total_sessions += 1
        self._save()
        
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """根据会话ID获取会话"""
        session = self._sessions.get(session_id)
        if session and not self._is_session_expired(session):
            return session
        return None
    
    def get_session_by_user(self, user_id: str) -> Optional[Session]:
        """根据用户ID获取会话"""
        if user_id in self._user_session_map:
            session_id = self._user_session_map[user_id]
            return self.get_session(session_id)
        return None
    
    def get_current_session(self, user_id: str) -> Optional[Dict]:
        """
        获取当前用户的会话信息（用于 session_status 工具）
        
        Returns:
            包含会话信息的字典，或 None
        """
        session = self.get_session_by_user(user_id)
        if not session:
            return None
        
        return {
            "session_key": session.session_id,
            "identity_id": user_id,
            "message_count": len(session.history),
            "created_at": session.created_at,
            "last_active": session.updated_at
        }
    
    def list_sessions(self) -> List[Dict]:
        """列出所有会话（用于 sessions_list 工具）"""
        sessions = []
        for session_id, session in self._sessions.items():
            if not self._is_session_expired(session):
                sessions.append({
                    "session_key": session_id,
                    "identity_id": session.user_id,
                    "message_count": len(session.history),
                    "created_at": session.created_at,
                    "last_active": session.updated_at
                })
        return sessions
    
    def get_history(self, session_key: str, limit: int = 20) -> List[Dict]:
        """获取会话历史（用于 sessions_history 工具）"""
        session = self._sessions.get(session_key)
        if not session:
            return []
        
        history = []
        for msg in session.get_recent_history(limit):
            history.append({
                "role": "user" if msg.source != Source.SYSTEM else "system",
                "content": msg.content,
                "timestamp": msg.timestamp
            })
        return history
    
    def _is_session_expired(self, session: Session) -> bool:
        """检查会话是否过期"""
        timeout = timedelta(seconds=self._config.session.session_timeout)
        return datetime.now() - session.updated_at > timeout
    
    def add_message_to_session(self, session: Session, message: Message):
        """添加消息到会话"""
        session.add_message(message)
        self._stats.total_messages += 1
        self._stats.last_activity = datetime.now()
        
        if len(session.history) > self._config.session.max_history_length:
            session.history = session.history[-self._config.session.max_history_length:]
        
        if self._config.session.auto_save:
            self._save()
    
    def add_message_to_session_by_key(self, session_key: str, message: Message) -> bool:
        """根据 session_key 添加消息到会话"""
        session = self._sessions.get(session_key)
        if session:
            self.add_message_to_session(session, message)
            return True
        return False
    
    def reset_session(self, user: User) -> Session:
        """重置用户会话"""
        user_id = user.user_id
        
        if user_id in self._user_session_map:
            old_session_id = self._user_session_map[user_id]
            if old_session_id in self._sessions:
                del self._sessions[old_session_id]
        
        new_session = Session.create(user)
        self._sessions[new_session.session_id] = new_session
        self._user_session_map[user_id] = new_session.session_id
        self._save()
        
        return new_session
    
    def clear_session_history(self, session: Session):
        """清空会话历史"""
        session.history = []
        session.updated_at = datetime.now()
        self._save()
    
    def get_context_for_llm(self, session: Session, limit: Optional[int] = None) -> List[Dict]:
        """
        获取用于 LLM 的上下文
        
        返回格式化的消息历史
        """
        limit = limit or self._config.session.max_history_length
        recent = session.get_recent_history(limit)
        
        context = []
        for msg in recent:
            context.append({
                "role": "user",
                "content": self._format_message_for_context(msg)
            })
        
        return context
    
    def _format_message_for_context(self, message: Message) -> str:
        """格式化消息用于上下文"""
        source_name = {
            Source.QQ: "QQ",
            Source.WEB: "网页",
            Source.DESKTOP: "桌宠",
            Source.CLI: "命令行"
        }.get(message.source, "未知")
        
        time_str = message.timestamp.strftime("%H:%M")
        return f"[{source_name} {time_str}] {message.content}"
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        expired_count = 0
        expired_session_ids = []
        
        for session_id, session in self._sessions.items():
            if self._is_session_expired(session):
                expired_session_ids.append(session_id)
        
        for session_id in expired_session_ids:
            session = self._sessions[session_id]
            user_id = session.user.user_id
            if user_id in self._user_session_map:
                if self._user_session_map[user_id] == session_id:
                    del self._user_session_map[user_id]
            del self._sessions[session_id]
            expired_count += 1
        
        if expired_count > 0:
            self._save()
        
        return expired_count
    
    def get_active_sessions_count(self) -> int:
        """获取活跃会话数"""
        count = 0
        for session in self._sessions.values():
            if not self._is_session_expired(session):
                count += 1
        self._stats.active_sessions = count
        return count
    
    def get_stats(self) -> SessionStats:
        """获取会话统计"""
        self._stats.active_sessions = self.get_active_sessions_count()
        return self._stats
    
    async def start_auto_save(self, interval: Optional[int] = None):
        """启动自动保存任务"""
        interval = interval or self._config.session.save_interval
        
        async def auto_save_loop():
            while True:
                await asyncio.sleep(interval)
                self._save()
        
        if self._auto_save_task:
            self._auto_save_task.cancel()
        
        self._auto_save_task = asyncio.create_task(auto_save_loop())
    
    def stop_auto_save(self):
        """停止自动保存任务"""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            self._auto_save_task = None
    
    def export_session(self, session_id: str, format: str = "json") -> Optional[str]:
        """导出会话"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        if format == "json":
            return json.dumps(session.to_dict(), ensure_ascii=False, indent=2)
        elif format == "markdown":
            lines = [f"# 会话导出", f""]
            lines.append(f"用户: {session.user.user_id}")
            lines.append(f"创建时间: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"消息数: {len(session.history)}")
            lines.append(f"")
            lines.append(f"## 消息历史")
            lines.append(f"")
            
            for msg in session.history:
                time_str = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                source = msg.source.value
                lines.append(f"### [{time_str}] {source}")
                lines.append(f"")
                lines.append(msg.content)
                lines.append(f"")
            
            return "\n".join(lines)
        
        return None
    
    @classmethod
    def get_instance(cls) -> "SessionManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
