"""
QQ 权限系统
4 级权限：OWNER > ADMIN > STRANGER > BLACKLIST

设计原则：
- Owner QQ 号写死在配置文件，不存数据库，不可被修改
- Admin / Blacklist 存在 data/qq_blacklist.json 和 data/whitelist.json
- 复用现有 UserManager 的白名单基础设施
- Blacklist 优先级最高：黑名单用户的所有消息被无视
"""

import json
import logging
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PermLevel(IntEnum):
    BLACKLIST = -1
    STRANGER  = 0
    ADMIN     = 1
    OWNER     = 2

    def label(self) -> str:
        return {
            PermLevel.BLACKLIST: "黑名单",
            PermLevel.STRANGER:  "陌生人",
            PermLevel.ADMIN:     "管理员",
            PermLevel.OWNER:     "主人",
        }[self]


class QQPermissionManager:
    """
    管理 QQ 用户的权限级别。

    存储：
    - data/qq_admins.json     : {qq: {"nickname": ..., "added_at": ..., "added_by": ...}}
    - data/qq_blacklist.json  : {qq: {"nickname": ..., "added_at": ..., "added_by": ...}}
    """

    def __init__(self, data_dir: str, owner_qq: int):
        self._data_dir = Path(data_dir)
        self._owner_qq = owner_qq
        self._admins: Dict[int, dict] = {}
        self._blacklist: Dict[int, dict] = {}
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    # ──────────────────────────────────────────────
    # 查询
    # ──────────────────────────────────────────────

    def get_level(self, qq: int) -> PermLevel:
        if qq == self._owner_qq:
            return PermLevel.OWNER
        if qq in self._blacklist:
            return PermLevel.BLACKLIST
        if qq in self._admins:
            return PermLevel.ADMIN
        return PermLevel.STRANGER

    def is_owner(self, qq: int) -> bool:
        return qq == self._owner_qq

    def is_blacklisted(self, qq: int) -> bool:
        return qq in self._blacklist

    def is_admin_or_above(self, qq: int) -> bool:
        return self.get_level(qq) >= PermLevel.ADMIN

    def list_admins(self) -> List[dict]:
        return [{"qq": qq, **info} for qq, info in self._admins.items()]

    def list_blacklist(self) -> List[dict]:
        return [{"qq": qq, **info} for qq, info in self._blacklist.items()]

    # ──────────────────────────────────────────────
    # 变更
    # ──────────────────────────────────────────────

    def grant_admin(self, target_qq: int, by_qq: int, nickname: str = "") -> bool:
        """授予管理员权限，返回是否是新授权"""
        if target_qq == self._owner_qq:
            return False  # 主人不需要授权
        already = target_qq in self._admins
        self._admins[target_qq] = {
            "nickname": nickname,
            "added_at": datetime.now().isoformat(),
            "added_by": by_qq,
        }
        # 若在黑名单则先移除
        self._blacklist.pop(target_qq, None)
        self._save()
        return not already

    def revoke_admin(self, target_qq: int, by_qq: int) -> bool:
        """撤销管理员权限，返回是否存在"""
        if target_qq not in self._admins:
            return False
        del self._admins[target_qq]
        self._save()
        return True

    def add_blacklist(self, target_qq: int, by_qq: int, nickname: str = "") -> bool:
        """加入黑名单"""
        if target_qq == self._owner_qq:
            return False
        self._blacklist[target_qq] = {
            "nickname": nickname,
            "added_at": datetime.now().isoformat(),
            "added_by": by_qq,
        }
        self._admins.pop(target_qq, None)
        self._save()
        return True

    def remove_blacklist(self, target_qq: int, by_qq: int) -> bool:
        """移出黑名单"""
        if target_qq not in self._blacklist:
            return False
        del self._blacklist[target_qq]
        self._save()
        return True

    # ──────────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────────

    def _load(self) -> None:
        admins_file = self._data_dir / "qq_admins.json"
        blacklist_file = self._data_dir / "qq_blacklist.json"

        if admins_file.exists():
            try:
                raw = json.loads(admins_file.read_text(encoding="utf-8"))
                self._admins = {int(k): v for k, v in raw.items()}
            except Exception as e:
                logger.warning(f"加载 qq_admins.json 失败: {e}")

        if blacklist_file.exists():
            try:
                raw = json.loads(blacklist_file.read_text(encoding="utf-8"))
                self._blacklist = {int(k): v for k, v in raw.items()}
            except Exception as e:
                logger.warning(f"加载 qq_blacklist.json 失败: {e}")

    def _save(self) -> None:
        admins_file = self._data_dir / "qq_admins.json"
        blacklist_file = self._data_dir / "qq_blacklist.json"
        try:
            admins_file.write_text(
                json.dumps({str(k): v for k, v in self._admins.items()},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            blacklist_file.write_text(
                json.dumps({str(k): v for k, v in self._blacklist.items()},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"保存权限数据失败: {e}")
