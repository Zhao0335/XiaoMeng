"""Configuration utilities for LingMeng TUI."""

import copy
import json
import shutil
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "data" / "qq_config.json"

SENSITIVE_KEYS = {"api_key", "napcat_token", "token"}
SECRET_MASK = "******"


def is_sensitive(key: str) -> bool:
    return key.lower() in SENSITIVE_KEYS or any(s in key.lower() for s in SENSITIVE_KEYS)


def mask_value(val: str) -> str:
    if not val:
        return "(empty)"
    return SECRET_MASK


def truncate(s: str, max_len: int) -> str:
    if max_len < 4:
        return s[:max_len]
    if len(s) <= max_len:
        return s
    return s[:max_len - 2] + ".."


def load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"error": f"Failed to load {CONFIG_PATH}"}


def save_config(config: Dict[str, Any]) -> bool:
    try:
        backup = CONFIG_PATH.with_suffix(".json.bak")
        if CONFIG_PATH.exists():
            shutil.copy2(CONFIG_PATH, backup)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return True
    except Exception:
        return False


def set_nested(cfg: dict, dotted_key: str, value: Any) -> None:
    keys = dotted_key.split(".")
    d = cfg
    for k in keys[:-1]:
        d = d[k]
    d[keys[-1]] = value


def get_nested(cfg: dict, dotted_key: str) -> Any:
    keys = dotted_key.split(".")
    d = cfg
    for k in keys:
        d = d[k]
    return d


def parse_value(raw: str, original: Any) -> Any:
    if isinstance(original, bool):
        if raw.lower() in ("true", "1", "yes"):
            return True
        elif raw.lower() in ("false", "0", "no"):
            return False
        return None
    elif isinstance(original, int):
        try:
            return int(raw)
        except ValueError:
            return None
    elif isinstance(original, float):
        try:
            return float(raw)
        except ValueError:
            return None
    return raw
