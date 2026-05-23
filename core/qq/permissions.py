"""
QQ 权限系统
4 级权限：OWNER > ADMIN > STRANGER > BLACKLIST

设计原则：
- Owner QQ 号写死在配置文件，不存数据库，不可被修改
- Admin / Blacklist / Whitelist 统一存在 data/qq_permissions.json
- Blacklist 优先级最高：黑名单用户的所有消息被无视
- 启动时检测旧的 qq_admins.json / qq_blacklist.json / whitelist.json 自动迁移
"""

import json
import logging
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Dict, List

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

    存储：data/qq_permissions.json
        {
          "admins":    {qq: {"nickname": ..., "added_at": ..., "added_by": ...}},
          "blacklist": {qq: {"nickname": ..., "added_at": ..., "added_by": ...}},
          "whitelist": {qq: {"nickname": ..., "added_at": ..., "added_by": ...}}
        }
    """

    _FILE_NAME = "qq_permissions.json"
    _LEGACY_FILES = {
        "admins":    "qq_admins.json",
        "blacklist": "qq_blacklist.json",
        "whitelist": "whitelist.json",
    }

    def __init__(self, data_dir: str, owner_qq: int):
        self._data_dir = Path(data_dir)
        self._owner_qq = owner_qq
        self._admins: Dict[int, dict] = {}
        self._blacklist: Dict[int, dict] = {}
        self._whitelist: Dict[int, dict] = {}
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_if_needed()
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
            return False
        already = target_qq in self._admins
        self._admins[target_qq] = {
            "nickname": nickname,
            "added_at": datetime.now().isoformat(),
            "added_by": by_qq,
        }
        self._blacklist.pop(target_qq, None)
        self._save()
        return not already

    def revoke_admin(self, target_qq: int, by_qq: int) -> bool:
        if target_qq not in self._admins:
            return False
        del self._admins[target_qq]
        self._save()
        return True

    def add_blacklist(self, target_qq: int, by_qq: int, nickname: str = "") -> bool:
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
        if target_qq not in self._blacklist:
            return False
        del self._blacklist[target_qq]
        self._save()
        return True

    # ──────────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────────

    def _migrate_legacy_if_needed(self) -> None:
        """启动时检测旧的 3 个文件，若新文件不存在则合并迁移并把旧文件重命名为 .bak"""
        new_file = self._data_dir / self._FILE_NAME
        if new_file.exists():
            return
        legacy_present = {
            k: self._data_dir / fn
            for k, fn in self._LEGACY_FILES.items()
            if (self._data_dir / fn).exists()
        }
        if not legacy_present:
            return
        merged = {"admins": {}, "blacklist": {}, "whitelist": {}}
        for k, path in legacy_present.items():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    merged[k] = raw
            except Exception as e:
                logger.warning(f"迁移 {path.name} 失败: {e}")
        try:
            new_file.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for k, path in legacy_present.items():
                path.rename(path.with_suffix(path.suffix + ".bak"))
            logger.info(
                f"qq_permissions.json 迁移成功（合并 {list(legacy_present)}，旧文件已 .bak）"
            )
        except Exception as e:
            logger.error(f"qq_permissions.json 迁移失败: {e}")

    def _load(self) -> None:
        path = self._data_dir / self._FILE_NAME
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._admins    = {int(k): v for k, v in raw.get("admins", {}).items()}
            self._blacklist = {int(k): v for k, v in raw.get("blacklist", {}).items()}
            self._whitelist = {int(k): v for k, v in raw.get("whitelist", {}).items()}
        except Exception as e:
            logger.warning(f"加载 qq_permissions.json 失败: {e}")

    def _save(self) -> None:
        path = self._data_dir / self._FILE_NAME
        payload = {
            "admins":    {str(k): v for k, v in self._admins.items()},
            "blacklist": {str(k): v for k, v in self._blacklist.items()},
            "whitelist": {str(k): v for k, v in self._whitelist.items()},
        }
        try:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"保存 qq_permissions.json 失败: {e}")
