"""
Identity resolution mixin for QQGateway.
Extracted from gateway.py to reduce file size.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List

from .permissions import PermLevel

logger = logging.getLogger(__name__)


class IdentityMixin:
    """Mixin providing identity resolution and permission methods for QQGateway."""

    def _load_identity_links(self) -> dict:
        """
        读取 identity_links.json，兼容三种格式，统一返回 {str(qq): identity_name}。
          格式 A（原始）: {"links": {"qq:3797723137": "owner"}}
          格式 B（简洁）: {"3797723137": "owner"}
          格式 v2（当前）: {"_schema":"v2", "owner": {"qq_list":[...], "level":"owner"}, ...}
        """
        try:
            if not self._identity_links_path.exists():
                return {}
            data = json.loads(self._identity_links_path.read_text(encoding="utf-8"))
            result = {}

            if data.get("_schema") == "v2":
                for identity_name, info in data.items():
                    if identity_name.startswith("_") or not isinstance(info, dict):
                        continue
                    for qq in info.get("qq_list", []):
                        result[str(qq)] = identity_name
                return result

            if "links" in data and isinstance(data["links"], dict):
                for k, v in data["links"].items():
                    if not isinstance(v, str):
                        continue
                    platform_id = k.split(":", 1)[1] if ":" in k else k
                    result[platform_id] = v
                return result

            for k, v in data.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, str):
                    result[k] = v
                elif isinstance(v, dict):
                    identity = v.get("alias") or v.get("identity")
                    if identity:
                        result[k] = identity
            return result
        except Exception as e:
            logger.debug(f"读取 identity_links 失败: {e}")
            return {}

    def _resolve_identity(self, qq: int) -> str:
        """将 QQ 号解析为 canonical 身份名，每次读文件保证即时生效。"""
        links = self._load_identity_links()
        return links.get(str(qq), f"user_{qq}")

    def _init_person_memory_if_needed(self, qq: int, nick: str) -> None:
        """
        第一次和某人说话时，自动在 data/memory/ 建立基础档案。
        只写一次（文件存在就跳过），后续由 LLM add_memory 工具填充细节。
        """
        try:
            identity = self._resolve_identity(qq)
            mem_file = self._memory_dir / f"{identity}.md"
            if not mem_file.exists():
                now = datetime.now().strftime("%Y-%m-%d")
                content = f"# 关于 {nick}（QQ: {qq}）\n\n首次见面：{now}\n"
                mem_file.write_text(content, encoding="utf-8")
                logger.info(f"建立记忆档案: memory/{identity}.md ({nick})")
        except Exception as e:
            logger.debug(f"建立记忆档案失败: {e}")

    def _get_effective_level(self, qq: int) -> PermLevel:
        """
        综合权限判断：先查 QQPermissionManager，再查 identity_links。
        如果某个 QQ 和 owner_qq 共享同一个 identity，视为 OWNER。
        """
        level = self._perm.get_level(qq)
        if level == PermLevel.OWNER:
            return level
        if level == PermLevel.BLACKLIST:
            return level
        try:
            owner_identity = self._resolve_identity(self._owner_qq)
            this_identity = self._resolve_identity(qq)
            if this_identity == owner_identity and not this_identity.startswith("user_"):
                return PermLevel.OWNER
        except Exception:
            pass
        return level

    def _get_identity_sessions(self, identity: str) -> List[str]:
        """
        返回所有映射到这个 identity 的平台账号对应的 private session_key 列表。
        """
        links = self._load_identity_links()
        return [
            f"private:{platform_id}"
            for platform_id, ident in links.items()
            if ident == identity
        ]