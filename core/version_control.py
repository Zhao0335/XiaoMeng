"""
XiaoMengCore 版本控制系统
- Git 集成
- 变更审计日志
- 回滚机制
- 变更确认流程
"""

import os
import json
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum


class ChangeType(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class AuditEntry:
    """审计日志条目"""
    entry_id: str
    timestamp: datetime
    file_path: str
    change_type: ChangeType
    user_id: str
    old_content_hash: Optional[str]
    new_content_hash: Optional[str]
    old_content: Optional[str]
    new_content: Optional[str]
    message: str
    confirmed: bool = False
    rolled_back: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "file_path": self.file_path,
            "change_type": self.change_type.value,
            "user_id": self.user_id,
            "old_content_hash": self.old_content_hash,
            "new_content_hash": self.new_content_hash,
            "message": self.message,
            "confirmed": self.confirmed,
            "rolled_back": self.rolled_back
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AuditEntry":
        return cls(
            entry_id=data["entry_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            file_path=data["file_path"],
            change_type=ChangeType(data["change_type"]),
            user_id=data["user_id"],
            old_content_hash=data.get("old_content_hash"),
            new_content_hash=data.get("new_content_hash"),
            old_content=data.get("old_content"),
            new_content=data.get("new_content"),
            message=data["message"],
            confirmed=data.get("confirmed", False),
            rolled_back=data.get("rolled_back", False)
        )


@dataclass
class PendingChange:
    """待确认的变更"""
    change_id: str
    file_path: str
    old_content: str
    new_content: str
    message: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    
    def to_dict(self) -> Dict:
        return {
            "change_id": self.change_id,
            "file_path": self.file_path,
            "old_content": self.old_content,
            "new_content": self.new_content,
            "message": self.message,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat()
        }


class AuditLog:
    """审计日志管理器"""
    
    def __init__(self, log_dir: str = "./data/audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_dir / "audit.jsonl"
        self._entries: List[AuditEntry] = []
        self._load_entries()
    
    def _load_entries(self):
        """加载历史审计日志"""
        if self._log_file.exists():
            with open(self._log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            self._entries.append(AuditEntry.from_dict(data))
                        except json.JSONDecodeError:
                            continue
    
    def _generate_id(self) -> str:
        """生成唯一 ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _hash_content(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def log(
        self,
        file_path: str,
        change_type: ChangeType,
        user_id: str,
        old_content: Optional[str],
        new_content: Optional[str],
        message: str
    ) -> AuditEntry:
        """记录审计日志"""
        entry = AuditEntry(
            entry_id=self._generate_id(),
            timestamp=datetime.now(),
            file_path=file_path,
            change_type=change_type,
            user_id=user_id,
            old_content_hash=self._hash_content(old_content) if old_content else None,
            new_content_hash=self._hash_content(new_content) if new_content else None,
            old_content=old_content,
            new_content=new_content,
            message=message
        )
        
        self._entries.append(entry)
        self._append_to_file(entry)
        
        return entry
    
    def _append_to_file(self, entry: AuditEntry):
        """追加到日志文件"""
        with open(self._log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + '\n')
    
    def get_entries(self, file_path: str = None, limit: int = 100) -> List[AuditEntry]:
        """获取审计日志"""
        entries = self._entries
        if file_path:
            entries = [e for e in entries if e.file_path == file_path]
        return entries[-limit:]
    
    def get_entry(self, entry_id: str) -> Optional[AuditEntry]:
        """获取指定条目"""
        for entry in self._entries:
            if entry.entry_id == entry_id:
                return entry
        return None
    
    def mark_confirmed(self, entry_id: str):
        """标记为已确认"""
        entry = self.get_entry(entry_id)
        if entry:
            entry.confirmed = True
            self._rewrite_log()
    
    def mark_rolled_back(self, entry_id: str):
        """标记为已回滚"""
        entry = self.get_entry(entry_id)
        if entry:
            entry.rolled_back = True
            self._rewrite_log()
    
    def _rewrite_log(self):
        """重写日志文件"""
        with open(self._log_file, 'w', encoding='utf-8') as f:
            for entry in self._entries:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + '\n')


class GitManager:
    """Git 管理器"""
    
    def __init__(self, repo_dir: str):
        self.repo_dir = Path(repo_dir)
        self._enabled = self._check_git()
    
    def _check_git(self) -> bool:
        """检查 Git 是否可用"""
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                timeout=5000
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def is_repo(self) -> bool:
        """检查是否是 Git 仓库"""
        return (self.repo_dir / ".git").exists()
    
    def init_repo(self) -> bool:
        """初始化 Git 仓库"""
        if not self._enabled:
            return False
        
        if self.is_repo():
            return True
        
        try:
            subprocess.run(
                ["git", "init"],
                cwd=str(self.repo_dir),
                capture_output=True,
                timeout=10000
            )
            subprocess.run(
                ["git", "config", "user.email", "xiaomeng@local"],
                cwd=str(self.repo_dir),
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "XiaoMeng"],
                cwd=str(self.repo_dir),
                capture_output=True
            )
            return True
        except Exception:
            return False
    
    def add(self, file_path: str) -> bool:
        """添加文件到暂存区"""
        if not self._enabled or not self.is_repo():
            return False
        
        try:
            subprocess.run(
                ["git", "add", file_path],
                cwd=str(self.repo_dir),
                capture_output=True,
                timeout=10000
            )
            return True
        except Exception:
            return False
    
    def commit(self, message: str) -> Optional[str]:
        """提交变更"""
        if not self._enabled or not self.is_repo():
            return None
        
        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.repo_dir),
                capture_output=True,
                timeout=30000
            )
            if result.returncode == 0:
                hash_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    text=True
                )
                return hash_result.stdout.strip()[:8]
        except Exception:
            pass
        return None
    
    def get_log(self, limit: int = 20) -> List[Dict]:
        """获取提交历史"""
        if not self._enabled or not self.is_repo():
            return []
        
        try:
            result = subprocess.run(
                ["git", "log", f"-{limit}", "--pretty=format:%H|%h|%s|%an|%ai"],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=10000
            )
            
            logs = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('|')
                    if len(parts) >= 5:
                        logs.append({
                            "hash": parts[0],
                            "short_hash": parts[1],
                            "message": parts[2],
                            "author": parts[3],
                            "date": parts[4]
                        })
            return logs
        except Exception:
            return []
    
    def get_file_at_commit(self, file_path: str, commit_hash: str) -> Optional[str]:
        """获取指定提交时的文件内容"""
        if not self._enabled or not self.is_repo():
            return None
        
        try:
            result = subprocess.run(
                ["git", "show", f"{commit_hash}:{file_path}"],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=10000
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return None
    
    def revert_file(self, file_path: str, commit_hash: str = None) -> bool:
        """回滚文件"""
        if not self._enabled or not self.is_repo():
            return False
        
        try:
            if commit_hash:
                subprocess.run(
                    ["git", "checkout", commit_hash, "--", file_path],
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    timeout=10000
                )
            else:
                subprocess.run(
                    ["git", "checkout", "HEAD", "--", file_path],
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    timeout=10000
                )
            return True
        except Exception:
            return False
    
    def diff(self, file_path: str = None) -> str:
        """查看差异"""
        if not self._enabled or not self.is_repo():
            return ""
        
        try:
            cmd = ["git", "diff"]
            if file_path:
                cmd.append(file_path)
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=10000
            )
            return result.stdout
        except Exception:
            return ""


class ChangeConfirmation:
    """变更确认管理器"""
    
    def __init__(self, confirm_dir: str = "./data/pending"):
        self.confirm_dir = Path(confirm_dir)
        self.confirm_dir.mkdir(parents=True, exist_ok=True)
        self._pending_file = self.confirm_dir / "pending.json"
        self._pending: Dict[str, PendingChange] = {}
        self._load_pending()
    
    def _load_pending(self):
        """加载待确认变更"""
        if self._pending_file.exists():
            with open(self._pending_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for change_id, change_data in data.items():
                    self._pending[change_id] = PendingChange(
                        change_id=change_data["change_id"],
                        file_path=change_data["file_path"],
                        old_content=change_data["old_content"],
                        new_content=change_data["new_content"],
                        message=change_data["message"],
                        user_id=change_data["user_id"],
                        created_at=datetime.fromisoformat(change_data["created_at"]),
                        expires_at=datetime.fromisoformat(change_data["expires_at"])
                    )
    
    def _save_pending(self):
        """保存待确认变更"""
        data = {cid: c.to_dict() for cid, c in self._pending.items()}
        with open(self._pending_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _generate_id(self) -> str:
        import uuid
        return str(uuid.uuid4())[:8]
    
    def create_pending(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        message: str,
        user_id: str,
        expire_minutes: int = 30
    ) -> PendingChange:
        """创建待确认变更"""
        now = datetime.now()
        change = PendingChange(
            change_id=self._generate_id(),
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            message=message,
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(minutes=expire_minutes)
        )
        
        self._pending[change.change_id] = change
        self._save_pending()
        
        return change
    
    def get_pending(self, change_id: str) -> Optional[PendingChange]:
        """获取待确认变更"""
        return self._pending.get(change_id)
    
    def get_all_pending(self) -> List[PendingChange]:
        """获取所有待确认变更"""
        self._cleanup_expired()
        return list(self._pending.values())
    
    def confirm(self, change_id: str) -> bool:
        """确认变更"""
        if change_id in self._pending:
            del self._pending[change_id]
            self._save_pending()
            return True
        return False
    
    def reject(self, change_id: str) -> Optional[PendingChange]:
        """拒绝变更"""
        if change_id in self._pending:
            change = self._pending.pop(change_id)
            self._save_pending()
            return change
        return None
    
    def _cleanup_expired(self):
        """清理过期变更"""
        now = datetime.now()
        expired = [cid for cid, c in self._pending.items() if c.expires_at < now]
        for cid in expired:
            del self._pending[cid]
        if expired:
            self._save_pending()


from datetime import timedelta


class VersionControl:
    """
    版本控制系统
    
    集成:
    - Git 版本控制
    - 审计日志
    - 回滚机制
    - 变更确认流程
    """
    
    _instance: "VersionControl" = None
    
    def __init__(
        self,
        repo_dir: str = "./data",
        enable_git: bool = True,
        require_confirmation: bool = False
    ):
        self.repo_dir = Path(repo_dir)
        self._enable_git = enable_git
        self._require_confirmation = require_confirmation
        
        self._git = GitManager(repo_dir) if enable_git else None
        self._audit = AuditLog(f"{repo_dir}/audit")
        self._confirmation = ChangeConfirmation(f"{repo_dir}/pending")
        
        if enable_git and self._git:
            self._git.init_repo()
    
    @classmethod
    def get_instance(cls) -> "VersionControl":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def init(cls, repo_dir: str = "./data", **kwargs) -> "VersionControl":
        cls._instance = cls(repo_dir=repo_dir, **kwargs)
        return cls._instance
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self._enable_git and self._git and self._git.is_repo()
    
    def commit(
        self,
        file_path: str,
        message: str,
        user_id: str,
        old_content: str = None,
        new_content: str = None
    ) -> Optional[str]:
        """提交变更"""
        change_type = ChangeType.CREATE
        if old_content and new_content:
            change_type = ChangeType.UPDATE
        elif new_content and not old_content:
            change_type = ChangeType.CREATE
        elif old_content and not new_content:
            change_type = ChangeType.DELETE
        
        self._audit.log(
            file_path=file_path,
            change_type=change_type,
            user_id=user_id,
            old_content=old_content,
            new_content=new_content,
            message=message
        )
        
        if self.is_enabled():
            rel_path = Path(file_path).name
            self._git.add(rel_path)
            return self._git.commit(message)
        
        return None
    
    def get_history(self, file_path: str = None, limit: int = 20) -> List[Dict]:
        """获取变更历史"""
        if file_path:
            entries = self._audit.get_entries(file_path=file_path, limit=limit)
            return [e.to_dict() for e in entries]
        else:
            return self._git.get_log(limit=limit) if self.is_enabled() else []
    
    def rollback(self, file_path: str, entry_id: str = None, commit_hash: str = None) -> bool:
        """回滚变更"""
        if commit_hash and self.is_enabled():
            rel_path = Path(file_path).name
            success = self._git.revert_file(rel_path, commit_hash)
            if success:
                self._audit.mark_rolled_back(entry_id or commit_hash)
            return success
        
        entry = self._audit.get_entry(entry_id) if entry_id else None
        if entry and entry.old_content is not None:
            Path(file_path).write_text(entry.old_content, encoding='utf-8')
            self._audit.mark_rolled_back(entry_id)
            return True
        
        return False
    
    def create_pending_change(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        message: str,
        user_id: str
    ) -> PendingChange:
        """创建待确认变更"""
        return self._confirmation.create_pending(
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            message=message,
            user_id=user_id
        )
    
    def confirm_change(self, change_id: str) -> bool:
        """确认变更"""
        change = self._confirmation.get_pending(change_id)
        if change:
            Path(change.file_path).write_text(change.new_content, encoding='utf-8')
            self._confirmation.confirm(change_id)
            return True
        return False
    
    def reject_change(self, change_id: str) -> bool:
        """拒绝变更"""
        result = self._confirmation.reject(change_id)
        return result is not None
    
    def get_pending_changes(self) -> List[PendingChange]:
        """获取待确认变更列表"""
        return self._confirmation.get_all_pending()
    
    def get_diff(self, file_path: str = None) -> str:
        """获取差异"""
        if self.is_enabled():
            rel_path = Path(file_path).name if file_path else None
            return self._git.diff(rel_path)
        return ""
    
    def get_file_at_version(self, file_path: str, commit_hash: str) -> Optional[str]:
        """获取指定版本的文件内容"""
        if self.is_enabled():
            rel_path = Path(file_path).name
            return self._git.get_file_at_commit(rel_path, commit_hash)
        return None
