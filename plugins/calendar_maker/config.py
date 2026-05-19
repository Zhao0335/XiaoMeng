"""
Calendar Maker Plugin 配置管理
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CalendarBackendConfig:
    backend_url: str = "http://127.0.0.1:5522"
    timeout: float = 30.0
    retry_count: int = 3
    retry_delay: float = 1.0


@dataclass
class AccountConfig:
    username: str
    password_hash: str
    session_id: Optional[str] = None
    last_used: Optional[str] = None


@dataclass
class SecurityConfig:
    password_hash_algorithm: str = "bcrypt"
    session_ttl_days: int = 30
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30


@dataclass
class CalendarMakerConfig:
    backend: CalendarBackendConfig = field(default_factory=CalendarBackendConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    accounts: dict[str, AccountConfig] = field(default_factory=dict)
    default_account: Optional[str] = None
    enabled: bool = True

    @classmethod
    def from_file(cls, config_path: Path) -> "CalendarMakerConfig":
        if not config_path.exists():
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            return cls()

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return cls()

    @classmethod
    def from_dict(cls, data: dict) -> "CalendarMakerConfig":
        backend_data = data.get("backend", {})
        backend = CalendarBackendConfig(
            backend_url=backend_data.get("url", "http://127.0.0.1:5522"),
            timeout=backend_data.get("timeout", 30.0),
            retry_count=backend_data.get("retry_count", 3),
            retry_delay=backend_data.get("retry_delay", 1.0),
        )

        security_data = data.get("security", {})
        security = SecurityConfig(
            password_hash_algorithm=security_data.get("password_hash_algorithm", "bcrypt"),
            session_ttl_days=security_data.get("session_ttl_days", 30),
            max_login_attempts=security_data.get("max_login_attempts", 5),
            lockout_duration_minutes=security_data.get("lockout_duration_minutes", 30),
        )

        accounts = {}
        for name, acc_data in data.get("accounts", {}).items():
            accounts[name] = AccountConfig(
                username=acc_data.get("username", name),
                password_hash=acc_data.get("password_hash", ""),
                session_id=acc_data.get("session_id"),
                last_used=acc_data.get("last_used"),
            )

        return cls(
            backend=backend,
            security=security,
            accounts=accounts,
            default_account=data.get("default_account"),
            enabled=data.get("enabled", True),
        )

    def to_dict(self) -> dict:
        accounts_data = {}
        for name, acc in self.accounts.items():
            accounts_data[name] = {
                "username": acc.username,
                "password_hash": acc.password_hash,
                "session_id": acc.session_id,
                "last_used": acc.last_used,
            }

        return {
            "enabled": self.enabled,
            "backend": {
                "url": self.backend.backend_url,
                "timeout": self.backend.timeout,
                "retry_count": self.backend.retry_count,
                "retry_delay": self.backend.retry_delay,
            },
            "security": {
                "password_hash_algorithm": self.security.password_hash_algorithm,
                "session_ttl_days": self.security.session_ttl_days,
                "max_login_attempts": self.security.max_login_attempts,
                "lockout_duration_minutes": self.security.lockout_duration_minutes,
            },
            "accounts": accounts_data,
            "default_account": self.default_account,
        }

    def save(self, config_path: Path) -> bool:
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
