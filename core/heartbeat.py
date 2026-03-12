"""
XiaoMengCore 心跳任务系统
兼容 OpenClaw HEARTBEAT.md 格式，支持定时任务和自主行为
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable, Awaitable
from dataclasses import dataclass, field
from pathlib import Path
import json
import random


@dataclass
class HeartbeatTask:
    """心跳任务定义"""
    task_id: str
    name: str
    description: str = ""
    interval_minutes: int = 60
    conditions: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    
    def should_run(self, now: datetime) -> bool:
        """检查是否应该执行"""
        if not self.enabled:
            return False
        
        if self.next_run is None:
            return True
        
        return now >= self.next_run
    
    def mark_run(self, now: datetime):
        """标记已执行"""
        self.last_run = now
        self.next_run = now + timedelta(minutes=self.interval_minutes)


@dataclass
class HeartbeatConfig:
    """心跳配置"""
    tasks: List[HeartbeatTask] = field(default_factory=list)
    global_interval: int = 60
    enabled: bool = True
    
    @classmethod
    def from_markdown(cls, content: str) -> "HeartbeatConfig":
        """从 HEARTBEAT.md 解析配置"""
        tasks = []
        
        task_pattern = r"##\s+(.+)\n\n(?:描述[:：]\s*(.+)\n)?(?:间隔[:：]\s*(\d+)\s*分钟?\n)?(?:条件[:：]\n((?:-\s*.+\n)+))?(?:动作[:：]\n((?:-\s*.+\n)+))?"
        
        matches = re.finditer(task_pattern, content, re.MULTILINE)
        
        for i, match in enumerate(matches):
            name = match.group(1).strip()
            description = match.group(2).strip() if match.group(2) else ""
            interval = int(match.group(3)) if match.group(3) else 60
            
            conditions = []
            if match.group(4):
                conditions = [
                    line.strip()[2:].strip() 
                    for line in match.group(4).strip().split('\n') 
                    if line.strip().startswith('-')
                ]
            
            actions = []
            if match.group(5):
                actions = [
                    line.strip()[2:].strip() 
                    for line in match.group(5).strip().split('\n') 
                    if line.strip().startswith('-')
                ]
            
            tasks.append(HeartbeatTask(
                task_id=f"task_{i}",
                name=name,
                description=description,
                interval_minutes=interval,
                conditions=conditions,
                actions=actions
            ))
        
        global_match = re.search(r"全局间隔[:：]\s*(\d+)\s*分钟?", content)
        global_interval = int(global_match.group(1)) if global_match else 60
        
        enabled_match = re.search(r"心跳[:：]\s*(启用|禁用|enabled|disabled)", content, re.IGNORECASE)
        enabled = True
        if enabled_match:
            enabled = enabled_match.group(1).lower() in ["启用", "enabled"]
        
        return cls(
            tasks=tasks,
            global_interval=global_interval,
            enabled=enabled
        )
    
    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        lines = [
            "# 心跳任务",
            "",
            f"心跳：{'启用' if self.enabled else '禁用'}",
            f"全局间隔：{self.global_interval} 分钟",
            ""
        ]
        
        for task in self.tasks:
            lines.append(f"## {task.name}")
            lines.append("")
            
            if task.description:
                lines.append(f"描述：{task.description}")
            
            lines.append(f"间隔：{task.interval_minutes} 分钟")
            
            if task.conditions:
                lines.append("条件：")
                for cond in task.conditions:
                    lines.append(f"- {cond}")
            
            if task.actions:
                lines.append("动作：")
                for action in task.actions:
                    lines.append(f"- {action}")
            
            lines.append("")
        
        return "\n".join(lines)


class HeartbeatManager:
    """
    心跳管理器
    
    管理 AI 的自主行为和定时任务：
    1. 加载 HEARTBEAT.md 配置
    2. 定时检查任务条件
    3. 触发自主行为
    4. 支持动态添加/删除任务
    """
    
    _instance: Optional["HeartbeatManager"] = None
    
    def __init__(self, persona_dir: str = "./data/persona"):
        self._persona_dir = Path(persona_dir)
        self._config: Optional[HeartbeatConfig] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[HeartbeatTask, Dict], Awaitable[None]]] = []
        self._state: Dict[str, Any] = {
            "last_user_message": None,
            "idle_minutes": 0,
            "last_active": datetime.now(),
            "message_count_today": 0,
            "current_mood": "neutral"
        }
    
    def load_config(self) -> HeartbeatConfig:
        """加载心跳配置"""
        heartbeat_file = self._persona_dir / "HEARTBEAT.md"
        
        if heartbeat_file.exists():
            content = heartbeat_file.read_text(encoding='utf-8')
            self._config = HeartbeatConfig.from_markdown(content)
        else:
            self._config = self._create_default_config()
        
        return self._config
    
    def _create_default_config(self) -> HeartbeatConfig:
        """创建默认心跳配置"""
        default_content = """# 心跳任务

心跳：启用
全局间隔：30 分钟

## 问候主人

描述：在主人长时间未说话时主动问候
间隔：120 分钟
条件：
- idle_minutes >= 120
- current_hour >= 8 and current_hour <= 23
动作：
- 发送问候消息
- 更新心情状态

## 记忆整理

描述：定期整理记忆
间隔：1440 分钟
条件：
- message_count_today >= 50
动作：
- 总结今日对话
- 提取重要记忆
- 更新 MEMORY.md

## 心情变化

描述：根据时间自然变化心情
间隔：60 分钟
动作：
- 根据时间调整心情
- 可能发送状态更新
"""
        
        self._persona_dir.mkdir(parents=True, exist_ok=True)
        (self._persona_dir / "HEARTBEAT.md").write_text(default_content, encoding='utf-8')
        
        return HeartbeatConfig.from_markdown(default_content)
    
    def register_callback(self, callback: Callable[[HeartbeatTask, Dict], Awaitable[None]]):
        """注册任务执行回调"""
        self._callbacks.append(callback)
    
    def update_state(self, key: str, value: Any):
        """更新状态"""
        self._state[key] = value
        
        if key == "last_user_message":
            self._state["last_active"] = datetime.now()
            self._state["idle_minutes"] = 0
    
    def increment_message_count(self):
        """增加消息计数"""
        self._state["message_count_today"] = self._state.get("message_count_today", 0) + 1
    
    def check_condition(self, condition: str) -> bool:
        """检查条件"""
        now = datetime.now()
        
        context = {
            "idle_minutes": self._state.get("idle_minutes", 0),
            "current_hour": now.hour,
            "current_minute": now.minute,
            "message_count_today": self._state.get("message_count_today", 0),
            "current_mood": self._state.get("current_mood", "neutral"),
            "last_active_minutes_ago": (now - self._state.get("last_active", now)).total_seconds() / 60
        }
        
        try:
            condition_clean = condition.lower().replace("and", "and").replace("or", "or")
            for key, value in context.items():
                condition_clean = condition_clean.replace(key, str(value))
            
            return bool(eval(condition_clean))
        except:
            return False
    
    async def execute_task(self, task: HeartbeatTask) -> Dict[str, Any]:
        """执行任务"""
        result = {
            "task_id": task.task_id,
            "task_name": task.name,
            "executed_at": datetime.now().isoformat(),
            "actions": [],
            "success": True
        }
        
        all_conditions_met = True
        for condition in task.conditions:
            if not self.check_condition(condition):
                all_conditions_met = False
                break
        
        if not all_conditions_met and task.conditions:
            result["skipped"] = True
            result["reason"] = "条件不满足"
            return result
        
        for action in task.actions:
            action_result = await self._execute_action(action, task)
            result["actions"].append({
                "action": action,
                "result": action_result
            })
        
        task.mark_run(datetime.now())
        
        for callback in self._callbacks:
            try:
                await callback(task, result)
            except Exception as e:
                print(f"Callback error: {e}")
        
        return result
    
    async def _execute_action(self, action: str, task: HeartbeatTask) -> Dict[str, Any]:
        """执行单个动作"""
        action_lower = action.lower()
        
        if "发送" in action or "消息" in action:
            return await self._action_send_message(action)
        
        elif "更新" in action and "记忆" in action:
            return await self._action_update_memory(action)
        
        elif "整理" in action or "总结" in action:
            return await self._action_summarize(action)
        
        elif "心情" in action:
            return await self._action_update_mood(action)
        
        else:
            return {"status": "unknown_action", "action": action}
    
    async def _action_send_message(self, action: str) -> Dict[str, Any]:
        """发送消息动作"""
        greetings = [
            "主人~你还在吗？(｡･ω･｡)",
            "主人，想你了~",
            "主人今天怎么样呀？",
            "主人~小萌在等你呢~",
            "主人有空吗？想和你聊天~"
        ]
        
        message = random.choice(greetings)
        
        return {
            "status": "message_prepared",
            "message": message,
            "type": "proactive"
        }
    
    async def _action_update_memory(self, action: str) -> Dict[str, Any]:
        """更新记忆动作"""
        return {
            "status": "memory_update_requested",
            "action": action
        }
    
    async def _action_summarize(self, action: str) -> Dict[str, Any]:
        """总结动作"""
        return {
            "status": "summarize_requested",
            "action": action
        }
    
    async def _action_update_mood(self, action: str) -> Dict[str, Any]:
        """更新心情动作"""
        now = datetime.now()
        hour = now.hour
        
        if 6 <= hour < 12:
            mood = "energetic"
        elif 12 <= hour < 18:
            mood = "happy"
        elif 18 <= hour < 22:
            mood = "relaxed"
        else:
            mood = "sleepy"
        
        self._state["current_mood"] = mood
        
        return {
            "status": "mood_updated",
            "mood": mood,
            "hour": hour
        }
    
    async def _heartbeat_loop(self):
        """心跳主循环"""
        while self._running:
            try:
                if self._config is None:
                    self.load_config()
                
                if not self._config.enabled:
                    await asyncio.sleep(self._config.global_interval * 60)
                    continue
                
                now = datetime.now()
                
                idle_delta = now - self._state.get("last_active", now)
                self._state["idle_minutes"] = idle_delta.total_seconds() / 60
                
                if now.hour == 0 and now.minute < 5:
                    self._state["message_count_today"] = 0
                
                for task in self._config.tasks:
                    if task.should_run(now):
                        await self.execute_task(task)
                
                await asyncio.sleep(self._config.global_interval * 60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Heartbeat error: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        """启动心跳"""
        if self._running:
            return
        
        self.load_config()
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
    
    async def stop(self):
        """停止心跳"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
    
    def add_task(self, task: HeartbeatTask):
        """添加任务"""
        if self._config:
            self._config.tasks.append(task)
    
    def remove_task(self, task_id: str) -> bool:
        """删除任务"""
        if not self._config:
            return False
        
        for i, task in enumerate(self._config.tasks):
            if task.task_id == task_id:
                self._config.tasks.pop(i)
                return True
        return False
    
    def save_config(self):
        """保存配置到 HEARTBEAT.md"""
        if self._config:
            content = self._config.to_markdown()
            self._persona_dir.mkdir(parents=True, exist_ok=True)
            (self._persona_dir / "HEARTBEAT.md").write_text(content, encoding='utf-8')
    
    @classmethod
    def get_instance(cls) -> "HeartbeatManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
