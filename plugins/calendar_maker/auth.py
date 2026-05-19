"""
身份验证模块
实现完整的身份验证机制，确保密码安全存储与验证
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logger.warning("bcrypt 未安装，将使用 SHA256 作为备选哈希算法")


class PasswordService:
    """密码服务 - 安全的密码哈希和验证"""

    @staticmethod
    def hash_password(password: str, algorithm: str = "bcrypt") -> str:
        if algorithm == "bcrypt" and BCRYPT_AVAILABLE:
            salt = bcrypt.gensalt()
            return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
        else:
            salt = secrets.token_hex(16)
            hash_value = hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()
            return f"sha256${salt}${hash_value}"

    @staticmethod
    def verify(password: str, password_hash: str) -> bool:
        if not password_hash:
            return False

        if password_hash.startswith("sha256$"):
            parts = password_hash.split("$")
            if len(parts) != 3:
                return False
            salt, stored_hash = parts[1], parts[2]
            computed = hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()
            return secrets.compare_digest(computed, stored_hash)
        elif BCRYPT_AVAILABLE:
            try:
                return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
            except Exception:
                return False
        else:
            return False


class LoginAttemptManager:
    """登录尝试管理 - 防止暴力破解"""

    def __init__(self, max_attempts: int = 5, lockout_minutes: int = 30):
        self._max_attempts = max_attempts
        self._lockout_duration = timedelta(minutes=lockout_minutes)
        self._attempts: dict[str, list[datetime]] = {}
        self._lockouts: dict[str, datetime] = {}

    def record_attempt(self, identifier: str, success: bool) -> None:
        now = datetime.now(UTC)
        if identifier not in self._attempts:
            self._attempts[identifier] = []

        if success:
            self._attempts[identifier] = []
            self._lockouts.pop(identifier, None)
        else:
            self._attempts[identifier].append(now)
            recent = [
                t for t in self._attempts[identifier]
                if now - t < timedelta(hours=1)
            ]
            self._attempts[identifier] = recent
            if len(recent) >= self._max_attempts:
                self._lockouts[identifier] = now

    def is_locked_out(self, identifier: str) -> bool:
        if identifier not in self._lockouts:
            return False
        lockout_time = self._lockouts[identifier]
        if datetime.now(UTC) - lockout_time > self._lockout_duration:
            self._lockouts.pop(identifier, None)
            self._attempts.pop(identifier, None)
            return False
        return True

    def get_remaining_attempts(self, identifier: str) -> int:
        attempts = self._attempts.get(identifier, [])
        recent = [
            t for t in attempts
            if datetime.now(UTC) - t < timedelta(hours=1)
        ]
        return max(0, self._max_attempts - len(recent))


class SessionManager:
    """会话管理"""

    def __init__(self, ttl_days: int = 30):
        self._ttl = timedelta(days=ttl_days)
        self._sessions: dict[str, dict] = {}

    def create_session(self, user_id: str, username: str) -> str:
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self._sessions[session_id] = {
            "user_id": user_id,
            "username": username,
            "created_at": now,
            "expires_at": now + self._ttl,
        }
        return session_id

    def validate_session(self, session_id: str) -> Optional[dict]:
        if not session_id or session_id not in self._sessions:
            return None
        session = self._sessions[session_id]
        if datetime.now(UTC) > session["expires_at"]:
            self._sessions.pop(session_id, None)
            return None
        return session

    def revoke_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._sessions.pop(session_id)
            return True
        return False

    def extend_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._sessions[session_id]["expires_at"] = datetime.now(UTC) + self._ttl
            return True
        return False


class CalendarAuth:
    """日历系统认证管理器"""

    def __init__(
        self,
        max_login_attempts: int = 5,
        lockout_minutes: int = 30,
        session_ttl_days: int = 30,
    ):
        self._password_service = PasswordService()
        self._attempt_manager = LoginAttemptManager(max_login_attempts, lockout_minutes)
        self._session_manager = SessionManager(session_ttl_days)
        self._users: dict[str, dict] = {}

    def register_user(self, username: str, password: str, user_id: str) -> bool:
        if username in self._users:
            return False
        self._users[username] = {
            "user_id": user_id,
            "username": username,
            "password_hash": self._password_service.hash_password(password),
            "created_at": datetime.now(UTC).isoformat(),
        }
        return True

    def login(self, username: str, password: str) -> tuple[Optional[str], Optional[str], str]:
        if self._attempt_manager.is_locked_out(username):
            return None, None, "账号已锁定，请稍后再试"

        user = self._users.get(username)
        if not user:
            self._attempt_manager.record_attempt(username, False)
            return None, None, "用户名或密码错误"

        if not self._password_service.verify(password, user["password_hash"]):
            self._attempt_manager.record_attempt(username, False)
            remaining = self._attempt_manager.get_remaining_attempts(username)
            return None, None, f"用户名或密码错误，剩余尝试次数: {remaining}"

        self._attempt_manager.record_attempt(username, True)
        session_id = self._session_manager.create_session(
            user["user_id"],
            user["username"]
        )
        return session_id, user["user_id"], "登录成功"

    def logout(self, session_id: str) -> bool:
        return self._session_manager.revoke_session(session_id)

    def validate_session(self, session_id: str) -> Optional[dict]:
        return self._session_manager.validate_session(session_id)

    def change_password(
        self,
        username: str,
        old_password: str,
        new_password: str
    ) -> tuple[bool, str]:
        user = self._users.get(username)
        if not user:
            return False, "用户不存在"

        if not self._password_service.verify(old_password, user["password_hash"]):
            return False, "原密码错误"

        user["password_hash"] = self._password_service.hash_password(new_password)
        return True, "密码修改成功"

    def get_user_by_username(self, username: str) -> Optional[dict]:
        return self._users.get(username)

    def hash_password(self, password: str) -> str:
        return self._password_service.hash_password(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return self._password_service.verify(password, password_hash)
