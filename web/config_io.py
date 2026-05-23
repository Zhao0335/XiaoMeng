"""
ConfigIO - 统一管理可被 HTML 面板编辑的配置文件。

- 支持 JSON 文件（qq_config / qq_permissions / identity_links）和 Markdown 文件（persona/*.md）
- 保存前自动写快照到 data/.config_history/，每文件保留最近 20 份
- JSON 内的敏感字段（api_key/token/...）默认 mask，前端"显示原值"通过 reveal_field 取
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

logger = logging.getLogger(__name__)

JsonOrText = Union[Dict[str, Any], List[Any], str]


class ConfigIO:
    # 文件注册表：key → (相对 data_dir 的路径, 类型)
    FILES: Dict[str, Tuple[str, str]] = {
        "qq_config":      ("qq_config.json",        "json"),
        "qq_permissions": ("qq_permissions.json",   "json"),
        "identity_links": ("identity_links.json",   "json"),
        "persona_soul":   ("persona/SOUL.md",       "text"),
        "persona_memory": ("persona/MEMORY.md",     "text"),
    }

    SENSITIVE_PATTERNS = ("api_key", "token", "password", "secret", "apikey")
    MASK = "••••••••"
    HISTORY_KEEP = 20

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._history_dir = self._data_dir / ".config_history"
        self._history_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────
    # 工具
    # ──────────────────────────────────────────────

    @classmethod
    def _is_sensitive(cls, field_name: str) -> bool:
        name_lower = field_name.lower()
        return any(p in name_lower for p in cls.SENSITIVE_PATTERNS)

    def _resolve(self, key: str) -> Tuple[Path, str]:
        if key not in self.FILES:
            raise KeyError(f"未知 config key: {key}")
        rel, kind = self.FILES[key]
        return self._data_dir / rel, kind

    def _mask_sensitive(self, data: Any) -> Any:
        """递归把所有敏感字段值替换为 MASK；保留非敏感字段原值。"""
        if isinstance(data, dict):
            return {
                k: (self.MASK if self._is_sensitive(k) and isinstance(v, str) and v
                    else self._mask_sensitive(v))
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [self._mask_sensitive(x) for x in data]
        return data

    def _merge_keep_masked(self, orig: Any, new: Any) -> Any:
        """提交保存时：若 new 的某敏感字段仍是 MASK，从 orig 拿回原值，避免误覆盖。"""
        if isinstance(new, dict) and isinstance(orig, dict):
            out = {}
            for k, v in new.items():
                if (self._is_sensitive(k) and isinstance(v, str) and v == self.MASK):
                    if k in orig:
                        out[k] = orig[k]
                    # 否则放弃（说明这个敏感字段在原值里就没有）
                else:
                    out[k] = self._merge_keep_masked(orig.get(k), v)
            return out
        if isinstance(new, list):
            if isinstance(orig, list):
                # 按下标配对：新增项 orig 部分为 None
                return [
                    self._merge_keep_masked(orig[i] if i < len(orig) else None, x)
                    for i, x in enumerate(new)
                ]
            return [self._merge_keep_masked(None, x) for x in new]
        return new

    # ──────────────────────────────────────────────
    # 读
    # ──────────────────────────────────────────────

    def list_keys(self) -> List[Dict[str, str]]:
        return [
            {"key": k, "path": rel, "kind": kind}
            for k, (rel, kind) in self.FILES.items()
        ]

    def read(self, key: str) -> Dict[str, Any]:
        path, kind = self._resolve(key)
        if not path.exists():
            if kind == "json":
                return {"kind": "json", "data": {}, "raw_text": "{}"}
            return {"kind": "text", "data": "", "raw_text": ""}
        text = path.read_text(encoding="utf-8")
        if kind == "json":
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as e:
                # 损坏的 JSON 也能编辑，前端按 text 模式展示
                return {"kind": "json_broken", "data": text, "raw_text": text, "error": str(e)}
            return {"kind": "json", "data": self._mask_sensitive(raw), "raw_text": text}
        return {"kind": "text", "data": text, "raw_text": text}

    def reveal_field(self, key: str, json_path: List[Union[str, int]]) -> Any:
        """按 json_path（如 ["models", 0, "api_key"]）取真实值。"""
        path, kind = self._resolve(key)
        if kind != "json" or not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        cur: Any = raw
        for seg in json_path:
            try:
                if isinstance(cur, list) and isinstance(seg, int):
                    cur = cur[seg]
                elif isinstance(cur, dict):
                    cur = cur[seg]
                else:
                    return None
            except (KeyError, IndexError, TypeError):
                return None
        return cur

    # ──────────────────────────────────────────────
    # 写
    # ──────────────────────────────────────────────

    def write(self, key: str, payload: Any) -> Dict[str, Any]:
        """
        payload:
          - JSON 文件：传 dict/list，会与原文件合并保留被 MASK 的敏感字段
          - 文本文件：传 str
        """
        path, kind = self._resolve(key)

        # 快照
        snapshot_name = self._snapshot(key, path)

        if kind == "json":
            try:
                orig = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except json.JSONDecodeError:
                orig = {}
            merged = self._merge_keep_masked(orig, payload)
            text = json.dumps(merged, ensure_ascii=False, indent=2)
        else:
            if not isinstance(payload, str):
                raise ValueError(f"{key} 是文本文件，payload 必须是 str")
            text = payload

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        logger.info(f"配置已保存: {key} → {path.name}（快照: {snapshot_name}）")

        self._prune_history(key)
        return {"snapshot": snapshot_name}

    # ──────────────────────────────────────────────
    # 历史快照
    # ──────────────────────────────────────────────

    def _snapshot_prefix(self, key: str) -> str:
        # 不能用文件名做 key（persona/SOUL.md 的 / 会出问题），所以直接用 key 名
        return f"{key}__"

    def _snapshot(self, key: str, path: Path) -> str | None:
        if not path.exists():
            return None
        # 加微秒精度避免同秒内连写覆盖
        ts = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        suffix = path.suffix
        snap_name = f"{self._snapshot_prefix(key)}{ts}{suffix}"
        snap_path = self._history_dir / snap_name
        snap_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        return snap_name

    def list_history(self, key: str) -> List[Dict[str, str]]:
        prefix = self._snapshot_prefix(key)
        items = []
        for p in sorted(self._history_dir.glob(f"{prefix}*"), reverse=True):
            ts_part = p.stem[len(prefix):]
            try:
                # 解析时间戳（支持微秒精度新版与旧版秒级）
                fmt = "%Y%m%dT%H%M%S_%f" if "_" in ts_part else "%Y%m%dT%H%M%S"
                dt = datetime.strptime(ts_part, fmt)
                pretty = dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pretty = ts_part
            items.append({
                "name": p.name,
                "timestamp": ts_part,
                "pretty": pretty,
                "size": p.stat().st_size,
            })
        return items

    def get_snapshot(self, name: str) -> str:
        p = self._history_dir / name
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(name)
        if p.parent.resolve() != self._history_dir.resolve():
            raise PermissionError(name)
        return p.read_text(encoding="utf-8")

    def restore(self, key: str, name: str) -> None:
        text = self.get_snapshot(name)
        path, kind = self._resolve(key)
        # 先给当前版本打个快照（不丢失"恢复前"的状态）
        self._snapshot(key, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        logger.info(f"已从快照恢复 {key}: {name}")
        self._prune_history(key)

    def _prune_history(self, key: str) -> None:
        prefix = self._snapshot_prefix(key)
        snaps = sorted(self._history_dir.glob(f"{prefix}*"), reverse=True)
        for old in snaps[self.HISTORY_KEEP:]:
            try:
                old.unlink()
            except OSError:
                pass
