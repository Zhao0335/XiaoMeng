"""
XiaoMengCore 工具策略系统
参考 OpenClaw 的 Tool Profiles 和 Tool Groups 设计
"""

from typing import Dict, List, Set, Optional
from enum import Enum
from dataclasses import dataclass, field


TOOL_GROUPS: Dict[str, List[str]] = {
    "group:memory": ["memory_search", "memory_get", "add_memory"],
    "group:web": ["web_search", "web_fetch", "download"],
    "group:fs": ["read", "write", "edit", "apply_patch", "find", "grep", "ls", "delete"],
    "group:runtime": ["exec", "process"],
    "group:sessions": [
        "sessions_list", "sessions_history", "sessions_send", 
        "sessions_spawn", "subagents", "session_status"
    ],
    "group:ui": ["browser", "image"],
    "group:automation": ["cron", "gateway", "message"],
    "group:messaging": ["message"],
    "group:schedule": ["add_schedule", "get_schedule", "add_todo", "list_todos", "complete_todo"],
    "group:self_improve": [
        "record_error", "record_correction", "record_best_practice",
        "record_feature_request", "get_learnings"
    ],
    "group:persona": [
        "update_persona", "create_skill", "get_history", "rollback",
        "get_diff", "get_pending_changes", "confirm_change", "reject_change"
    ],
    "group:model": ["register_model", "unregister_model", "get_models_status"],
    "group:info": ["get_weather", "get_news", "add_special_day", "set_preference"],
}


class ToolProfile(Enum):
    MINIMAL = "minimal"
    CODING = "coding"
    MESSAGING = "messaging"
    MEMORY = "memory"
    FULL = "full"


TOOL_PROFILES: Dict[str, Dict] = {
    "minimal": {
        "description": "最小工具集，用于简单对话",
        "allow": ["session_status"],
        "deny": []
    },
    "coding": {
        "description": "编程工作工具集",
        "allow": ["group:fs", "group:runtime", "group:sessions", "group:memory", "image"],
        "deny": []
    },
    "messaging": {
        "description": "消息处理工具集",
        "allow": ["group:messaging", "sessions_list", "sessions_history", "sessions_send", "session_status"],
        "deny": []
    },
    "memory": {
        "description": "记忆管理工具集",
        "allow": ["group:memory", "group:schedule", "group:info"],
        "deny": []
    },
    "full": {
        "description": "完整工具集，无限制",
        "allow": [],
        "deny": []
    }
}


@dataclass
class ToolPolicyConfig:
    """工具策略配置"""
    profile: ToolProfile = ToolProfile.FULL
    custom_allow: Set[str] = field(default_factory=set)
    custom_deny: Set[str] = field(default_factory=set)
    max_tool_calls_per_turn: int = 20
    max_identical_calls: int = 3
    loop_detection_window: int = 5


class ToolPolicy:
    """工具策略管理器"""
    
    def __init__(self, config: Optional[ToolPolicyConfig] = None):
        self.config = config or ToolPolicyConfig()
        self._expanded_groups: Dict[str, List[str]] = {}
        self._expand_all_groups()
    
    def _expand_all_groups(self):
        """展开所有工具组"""
        for group_name, tools in TOOL_GROUPS.items():
            self._expanded_groups[group_name] = self._expand_group(group_name, set())
    
    def _expand_group(self, group_name: str, visited: Set[str]) -> List[str]:
        """递归展开工具组"""
        if group_name in visited:
            return []
        
        visited.add(group_name)
        
        if group_name not in TOOL_GROUPS:
            return [group_name]
        
        result = []
        for item in TOOL_GROUPS[group_name]:
            if item.startswith("group:"):
                result.extend(self._expand_group(item, visited))
            else:
                result.append(item)
        
        return result
    
    def get_allowed_tools(self, base_tools: List[str]) -> List[str]:
        """获取允许的工具列表"""
        if self.config.profile == ToolProfile.FULL:
            allowed = set(base_tools)
        else:
            profile_config = TOOL_PROFILES.get(self.config.profile.value, {})
            allow_list = profile_config.get("allow", [])
            
            allowed = set()
            for item in allow_list:
                if item.startswith("group:"):
                    allowed.update(self._expanded_groups.get(item, []))
                else:
                    allowed.add(item)
        
        allowed.update(self.config.custom_allow)
        allowed.difference_update(self.config.custom_deny)
        
        return list(allowed & set(base_tools))
    
    def is_tool_allowed(self, tool_name: str, available_tools: List[str]) -> bool:
        """检查工具是否被允许"""
        allowed = self.get_allowed_tools(available_tools)
        return tool_name in allowed
    
    def check_loop(self, call_history: List[str]) -> tuple[bool, Optional[str]]:
        """
        检测工具调用循环
        
        Returns:
            (is_loop, reason) - 是否检测到循环，以及原因
        """
        if len(call_history) < 2:
            return False, None
        
        window = call_history[-self.config.loop_detection_window:]
        
        if len(window) >= self.config.loop_detection_window:
            if len(set(window)) == 1:
                return True, f"检测到重复调用同一工具 {window[0]} 超过 {self.config.loop_detection_window} 次"
        
        if len(window) >= 2:
            for i in range(len(window) - 1):
                pattern_len = 1
                while i + 2 * pattern_len <= len(window):
                    pattern = window[i:i + pattern_len]
                    next_pattern = window[i + pattern_len:i + 2 * pattern_len]
                    if pattern == next_pattern:
                        return True, f"检测到循环模式: {' -> '.join(pattern)}"
                    pattern_len += 1
        
        tool_counts = {}
        for tool in window:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
            if tool_counts[tool] > self.config.max_identical_calls:
                return True, f"工具 {tool} 在最近 {self.config.loop_detection_window} 次调用中出现 {tool_counts[tool]} 次"
        
        return False, None


class ToolLoopDetector:
    """工具循环检测器"""
    
    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self._call_history: List[Dict] = []
        self._session_histories: Dict[str, List[str]] = {}
    
    def record_call(self, session_key: str, tool_name: str, arguments: Dict):
        """记录工具调用"""
        import time
        
        call_record = {
            "session_key": session_key,
            "tool_name": tool_name,
            "arguments": arguments,
            "timestamp": time.time()
        }
        
        self._call_history.append(call_record)
        if len(self._call_history) > self.max_history:
            self._call_history = self._call_history[-self.max_history:]
        
        if session_key not in self._session_histories:
            self._session_histories[session_key] = []
        self._session_histories[session_key].append(tool_name)
        
        session_history = self._session_histories[session_key]
        if len(session_history) > self.max_history:
            self._session_histories[session_key] = session_history[-self.max_history:]
    
    def check_session_loop(self, session_key: str, config: Optional[ToolPolicyConfig] = None) -> tuple[bool, Optional[str]]:
        """检查会话的工具调用循环"""
        config = config or ToolPolicyConfig()
        policy = ToolPolicy(config)
        
        history = self._session_histories.get(session_key, [])
        return policy.check_loop(history)
    
    def get_session_stats(self, session_key: str) -> Dict:
        """获取会话的工具调用统计"""
        history = self._session_histories.get(session_key, [])
        
        tool_counts = {}
        for tool in history:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
        
        return {
            "total_calls": len(history),
            "unique_tools": len(tool_counts),
            "tool_distribution": tool_counts,
            "most_used": max(tool_counts.items(), key=lambda x: x[1])[0] if tool_counts else None
        }
    
    def clear_session(self, session_key: str):
        """清除会话历史"""
        if session_key in self._session_histories:
            del self._session_histories[session_key]
    
    def get_recent_calls(self, session_key: str, limit: int = 10) -> List[Dict]:
        """获取最近的工具调用记录"""
        recent = [
            call for call in self._call_history
            if call["session_key"] == session_key
        ][-limit:]
        return recent


_tool_loop_detector: Optional[ToolLoopDetector] = None


def get_tool_loop_detector() -> ToolLoopDetector:
    """获取全局工具循环检测器"""
    global _tool_loop_detector
    if _tool_loop_detector is None:
        _tool_loop_detector = ToolLoopDetector()
    return _tool_loop_detector
