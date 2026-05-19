"""
QQ号与Calendar账号绑定管理模块

绑定规则：
1. 一个QQ号只能绑定一个calendar账号（一对一）
2. 绑定关系长期有效，直到用户主动解除或会话过期
3. 每次操作自动刷新会话有效期
4. 绑定和解绑都需要密码验证
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BindingInfo:
    qq: int
    calendar_username: str
    account_name: Optional[str] = None
    session_id: Optional[str] = None
    bound_at: str = ""
    expires_at: str = ""
    last_active: str = ""

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(UTC) > expires
        except Exception:
            return True

    def to_dict(self) -> dict:
        return {
            "qq": self.qq,
            "calendar_username": self.calendar_username,
            "account_name": self.account_name,
            "session_id": self.session_id,
            "bound_at": self.bound_at,
            "expires_at": self.expires_at,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BindingInfo":
        return cls(
            qq=data.get("qq", 0),
            calendar_username=data.get("calendar_username", ""),
            account_name=data.get("account_name"),
            session_id=data.get("session_id"),
            bound_at=data.get("bound_at", ""),
            expires_at=data.get("expires_at", ""),
            last_active=data.get("last_active", ""),
        )


class BindingManager:
    """
    QQ号与Calendar账号绑定管理器
    
    功能：
    - 管理QQ号与calendar账号的绑定关系
    - 绑定状态持久化存储
    - 会话有效期管理
    - 绑定状态查询与更新
    """

    def __init__(
        self,
        data_dir: Path,
        session_ttl_days: int = 30,
    ):
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._session_ttl = timedelta(days=session_ttl_days)
        
        self._bindings_file = self._data_dir / "qq_bindings.json"
        self._bindings: dict[int, BindingInfo] = {}
        
        self._load_bindings()

    def _load_bindings(self) -> None:
        if self._bindings_file.exists():
            try:
                data = json.loads(self._bindings_file.read_text(encoding="utf-8"))
                for qq_str, binding_data in data.get("bindings", {}).items():
                    qq = int(qq_str)
                    self._bindings[qq] = BindingInfo.from_dict(binding_data)
                logger.info(f"加载了 {len(self._bindings)} 个QQ绑定关系")
            except Exception as e:
                logger.error(f"加载绑定数据失败: {e}")

    def _save_bindings(self) -> None:
        try:
            bindings_data = {
                str(qq): binding.to_dict()
                for qq, binding in self._bindings.items()
            }
            data = {
                "bindings": bindings_data,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._bindings_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"保存绑定数据失败: {e}")

    def is_bound(self, qq: int) -> bool:
        """检查QQ号是否已绑定"""
        if qq not in self._bindings:
            return False
        binding = self._bindings[qq]
        if binding.is_expired():
            return False
        return True

    def get_binding(self, qq: int) -> Optional[BindingInfo]:
        """获取QQ号的绑定信息"""
        if qq not in self._bindings:
            return None
        binding = self._bindings[qq]
        if binding.is_expired():
            return None
        return binding

    def bind(
        self,
        qq: int,
        calendar_username: str,
        session_id: str,
        account_name: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        绑定QQ号到calendar账号
        
        参数：
        - qq: QQ号
        - calendar_username: calendar_backend 的用户名
        - session_id: 登录成功后的 session_id
        - account_name: 可选的本地别名
        """
        now = datetime.now(UTC)
        expires = now + self._session_ttl
        
        binding = BindingInfo(
            qq=qq,
            calendar_username=calendar_username,
            account_name=account_name or calendar_username,
            session_id=session_id,
            bound_at=now.isoformat(),
            expires_at=expires.isoformat(),
            last_active=now.isoformat(),
        )
        
        self._bindings[qq] = binding
        self._save_bindings()
        
        logger.info(f"QQ {qq} 绑定到账号 {calendar_username}")
        return True, f"绑定成功：QQ {qq} → 账号 {calendar_username}"

    def unbind(self, qq: int) -> tuple[bool, str]:
        """
        解除QQ号的绑定
        
        参数：
        - qq: QQ号
        """
        if qq not in self._bindings:
            return False, "该QQ号未绑定任何账号"
        
        binding = self._bindings[qq]
        username = binding.calendar_username
        del self._bindings[qq]
        self._save_bindings()
        
        logger.info(f"QQ {qq} 解除绑定（原账号: {username}）")
        return True, f"解除绑定成功：QQ {qq} 已与账号 {username} 解绑"

    def refresh_session(
        self,
        qq: int,
        session_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        刷新绑定会话
        
        参数：
        - qq: QQ号
        - session_id: 新的 session_id（可选）
        """
        if qq not in self._bindings:
            return False, "该QQ号未绑定任何账号"
        
        binding = self._bindings[qq]
        now = datetime.now(UTC)
        expires = now + self._session_ttl
        
        binding.last_active = now.isoformat()
        binding.expires_at = expires.isoformat()
        if session_id:
            binding.session_id = session_id
        
        self._save_bindings()
        return True, "会话已刷新"

    def update_session(self, qq: int, session_id: str) -> bool:
        """更新会话ID"""
        if qq not in self._bindings:
            return False
        self._bindings[qq].session_id = session_id
        self._save_bindings()
        return True

    def switch_binding(
        self,
        qq: int,
        calendar_username: str,
        session_id: str,
        account_name: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        切换绑定到另一个账号
        
        参数：
        - qq: QQ号
        - calendar_username: 新的 calendar 用户名
        - session_id: 新的 session_id
        - account_name: 可选的本地别名
        """
        old_binding = self._bindings.get(qq)
        old_username = old_binding.calendar_username if old_binding else None
        
        success, msg = self.bind(qq, calendar_username, session_id, account_name)
        if success:
            if old_username:
                return True, f"切换成功：{old_username} → {calendar_username}"
            return True, msg
        return False, msg

    def list_bindings(self) -> list[BindingInfo]:
        """列出所有有效的绑定"""
        result = []
        for qq, binding in self._bindings.items():
            if not binding.is_expired():
                result.append(binding)
        return result

    def get_binding_status(self, qq: int) -> dict:
        """获取绑定状态详情"""
        if qq not in self._bindings:
            return {
                "is_bound": False,
                "message": "未绑定任何账号",
            }
        
        binding = self._bindings[qq]
        if binding.is_expired():
            return {
                "is_bound": False,
                "message": "绑定已过期，请重新登录",
                "calendar_username": binding.calendar_username,
                "expired_at": binding.expires_at,
            }
        
        return {
            "is_bound": True,
            "message": "已绑定",
            "calendar_username": binding.calendar_username,
            "account_name": binding.account_name,
            "bound_at": binding.bound_at,
            "expires_at": binding.expires_at,
            "last_active": binding.last_active,
        }

    def cleanup_expired(self) -> int:
        """清理过期的绑定"""
        expired_qqs = [
            qq for qq, binding in self._bindings.items()
            if binding.is_expired()
        ]
        for qq in expired_qqs:
            del self._bindings[qq]
        
        if expired_qqs:
            self._save_bindings()
            logger.info(f"清理了 {len(expired_qqs)} 个过期绑定")
        
        return len(expired_qqs)
