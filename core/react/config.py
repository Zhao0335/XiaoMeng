"""
ReAct 配置与数据结构
====================
ReActPhase / ReActStep / ReActConfig
"""

from typing import Dict, List, Optional


class ReActPhase:
    """ReAct 循环中的各个阶段"""

    ROUTING = "routing"
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVE = "observe"
    REFLECT = "reflect"
    RESPOND = "respond"


class ReActStep:
    """记录 ReAct 循环中的每一步"""

    def __init__(self, phase: str):
        self.phase = phase
        self.thought: Optional[str] = None
        self.action: Optional[Dict] = None
        self.observation: Optional[str] = None
        self.reflection: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "phase": self.phase,
            "thought": self.thought,
            "action": self.action,
            "observation": self.observation,
            "reflection": self.reflection,
        }


class ReActConfig:
    """ReAct 循环的可配置参数"""

    def __init__(
        self,
        max_tool_loops: int = 10,
        max_searches_before_write: int = 4,
        write_tools: Optional[set] = None,
        search_tools: Optional[set] = None,
    ):
        self.max_tool_loops = max_tool_loops
        self.max_searches_before_write = max_searches_before_write
        self.write_tools = write_tools or {"write_file", "add_memory", "update_soul"}
        self.search_tools = search_tools or {"web_search"}
