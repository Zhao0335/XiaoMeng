"""
XiaoMengCore v2 - 会话记录层

参考 OpenClaw 的双层持久化：
1. sessions.json: 会话元数据
2. <sessionId>.jsonl: 完整对话记录（树形结构）

.jsonl 格式支持：
- 树形结构（id + parentId）
- 工具调用记录
- 压缩摘要
- 多分支对话
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import json
import uuid


@dataclass
class TranscriptEntry:
    """
    记录条目
    
    支持树形结构：每个条目有 id 和 parentId
    """
    id: str
    parent_id: Optional[str]
    role: str
    content: str
    created_at: datetime = field(default_factory=datetime.now)
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    tool_result: Optional[Any] = None
    model: Optional[str] = None
    tokens: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "parentId": self.parent_id,
            "role": self.role,
            "content": self.content,
            "createdAt": self.created_at.isoformat()
        }
        if self.tool_name:
            result["toolName"] = self.tool_name
        if self.tool_args:
            result["toolArgs"] = self.tool_args
        if self.tool_result is not None:
            result["toolResult"] = self.tool_result
        if self.model:
            result["model"] = self.model
        if self.tokens:
            result["tokens"] = self.tokens
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TranscriptEntry":
        return cls(
            id=data["id"],
            parent_id=data.get("parentId"),
            role=data["role"],
            content=data["content"],
            created_at=datetime.fromisoformat(data["createdAt"]) if data.get("createdAt") else datetime.now(),
            tool_name=data.get("toolName"),
            tool_args=data.get("toolArgs"),
            tool_result=data.get("toolResult"),
            model=data.get("model"),
            tokens=data.get("tokens"),
            metadata=data.get("metadata", {})
        )


class TranscriptStore:
    """
    记录存储
    
    每个会话一个 .jsonl 文件，支持追加写入
    """
    
    def __init__(self, store_dir: str = "data/transcripts"):
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._open_files: Dict[str, Any] = {}
    
    def _get_transcript_path(self, session_id: str) -> Path:
        return self._store_dir / f"{session_id}.jsonl"
    
    def append(self, session_id: str, entry: TranscriptEntry):
        """追加条目到记录文件"""
        path = self._get_transcript_path(session_id)
        
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    
    def read_all(self, session_id: str) -> List[TranscriptEntry]:
        """读取所有条目"""
        path = self._get_transcript_path(session_id)
        
        if not path.exists():
            return []
        
        entries = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(TranscriptEntry.from_dict(json.loads(line)))
                    except:
                        pass
        
        return entries
    
    def read_tail(self, session_id: str, limit: int = 50) -> List[TranscriptEntry]:
        """读取最后 N 条"""
        entries = self.read_all(session_id)
        return entries[-limit:]
    
    def get_entry(self, session_id: str, entry_id: str) -> Optional[TranscriptEntry]:
        """获取特定条目"""
        entries = self.read_all(session_id)
        for entry in entries:
            if entry.id == entry_id:
                return entry
        return None
    
    def get_children(self, session_id: str, parent_id: str) -> List[TranscriptEntry]:
        """获取子条目"""
        entries = self.read_all(session_id)
        return [e for e in entries if e.parent_id == parent_id]
    
    def build_tree(self, session_id: str) -> Dict[str, Any]:
        """构建树形结构"""
        entries = self.read_all(session_id)
        
        entry_map = {e.id: e for e in entries}
        children_map: Dict[str, List[str]] = {}
        root_ids = []
        
        for entry in entries:
            if entry.parent_id:
                if entry.parent_id not in children_map:
                    children_map[entry.parent_id] = []
                children_map[entry.parent_id].append(entry.id)
            else:
                root_ids.append(entry.id)
        
        def build_node(entry_id: str) -> Dict[str, Any]:
            entry = entry_map[entry_id]
            children = children_map.get(entry_id, [])
            return {
                "id": entry.id,
                "role": entry.role,
                "content": entry.content[:100] + "..." if len(entry.content) > 100 else entry.content,
                "children": [build_node(cid) for cid in children]
            }
        
        return {
            "session_id": session_id,
            "total_entries": len(entries),
            "roots": [build_node(rid) for rid in root_ids]
        }
    
    def delete_session(self, session_id: str):
        """删除会话记录"""
        path = self._get_transcript_path(session_id)
        if path.exists():
            path.unlink()


class SessionStore:
    """
    会话存储
    
    管理 sessions.json 和 .jsonl 记录
    """
    
    _instance: Optional["SessionStore"] = None
    
    def __init__(self, data_dir: str = "data"):
        self._data_dir = Path(data_dir)
        self._sessions_file = self._data_dir / "sessions.json"
        self._transcript_store = TranscriptStore(str(self._data_dir / "transcripts"))
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._load_sessions()
    
    @classmethod
    def get_instance(cls) -> "SessionStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _load_sessions(self):
        if self._sessions_file.exists():
            try:
                with open(self._sessions_file, "r", encoding="utf-8") as f:
                    self._sessions = json.load(f)
            except:
                self._sessions = {}
    
    def _save_sessions(self):
        with open(self._sessions_file, "w", encoding="utf-8") as f:
            json.dump(self._sessions, f, ensure_ascii=False, indent=2, default=str)
    
    def create_session(
        self,
        session_key: str,
        identity_id: str,
        group_id: Optional[str] = None,
        channel: Optional[str] = None
    ) -> str:
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        
        self._sessions[session_key] = {
            "session_key": session_key,
            "session_id": session_id,
            "identity_id": identity_id,
            "group_id": group_id,
            "channel": channel,
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "message_count": 0,
            "total_tokens": 0,
            "metadata": {}
        }
        
        self._save_sessions()
        return session_id
    
    def get_session(self, session_key: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_key)
    
    def update_session(
        self,
        session_key: str,
        message_count: Optional[int] = None,
        tokens: Optional[int] = None,
        **kwargs
    ):
        if session_key not in self._sessions:
            return
        
        session = self._sessions[session_key]
        session["last_active"] = datetime.now().isoformat()
        
        if message_count is not None:
            session["message_count"] = message_count
        if tokens is not None:
            session["total_tokens"] = session.get("total_tokens", 0) + tokens
        
        for key, value in kwargs.items():
            session[key] = value
        
        self._save_sessions()
    
    def delete_session(self, session_key: str):
        if session_key in self._sessions:
            session_id = self._sessions[session_key].get("session_id")
            if session_id:
                self._transcript_store.delete_session(session_id)
            del self._sessions[session_key]
            self._save_sessions()
    
    def list_sessions(
        self,
        identity_id: Optional[str] = None,
        group_id: Optional[str] = None,
        active_within_minutes: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        sessions = list(self._sessions.values())
        
        if identity_id:
            sessions = [s for s in sessions if s.get("identity_id") == identity_id]
        
        if group_id:
            sessions = [s for s in sessions if s.get("group_id") == group_id]
        
        if active_within_minutes:
            cutoff = datetime.now().timestamp() - active_within_minutes * 60
            sessions = [
                s for s in sessions
                if datetime.fromisoformat(s["last_active"]).timestamp() > cutoff
            ]
        
        return sorted(sessions, key=lambda x: x["last_active"], reverse=True)
    
    def append_transcript(
        self,
        session_key: str,
        role: str,
        content: str,
        parent_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict] = None,
        tool_result: Optional[Any] = None,
        model: Optional[str] = None,
        tokens: Optional[Dict[str, int]] = None
    ) -> str:
        session = self._sessions.get(session_key)
        if not session:
            return ""
        
        session_id = session["session_id"]
        entry_id = f"entry_{uuid.uuid4().hex[:8]}"
        
        entry = TranscriptEntry(
            id=entry_id,
            parent_id=parent_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            model=model,
            tokens=tokens
        )
        
        self._transcript_store.append(session_id, entry)
        
        self.update_session(
            session_key,
            message_count=session.get("message_count", 0) + 1,
            tokens=tokens.get("total", 0) if tokens else 0
        )
        
        return entry_id
    
    def get_transcript(self, session_key: str, limit: int = 50) -> List[TranscriptEntry]:
        session = self._sessions.get(session_key)
        if not session:
            return []
        
        return self._transcript_store.read_tail(session["session_id"], limit)
    
    def get_transcript_tree(self, session_key: str) -> Dict[str, Any]:
        session = self._sessions.get(session_key)
        if not session:
            return {}
        
        return self._transcript_store.build_tree(session["session_id"])


from typing import Optional
