"""
小萌的内心世界 — platform-independent idle agent.

当 bot 一段时间没有收到任何消息且任务池为空时，触发 InnerWorldAgent，
让小萌用自己的自由时间做点什么：刷 B 站、听音乐、写记忆、静静发呆……

用法（由 platform-specific gateway 调用）：
    from core.inner_world import InnerWorldAgent, InnerWorldEventLogger

    agent = InnerWorldAgent(router, executor_factory, ...)
    await agent.run()
"""

from .agent import InnerWorldAgent
from .events import InnerWorldEventLogger

__all__ = ["InnerWorldAgent", "InnerWorldEventLogger"]
