"""
XiaoMengCore 优先级调度系统
支持 P0/P1/P2/P3 分级调度，确保实时响应
"""

import asyncio
import heapq
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Awaitable, List
from enum import IntEnum


class Priority(IntEnum):
    """任务优先级"""
    REALTIME = 0
    INTERACTIVE = 1
    UNDERSTANDING = 2
    BACKGROUND = 3


@dataclass(order=True)
class ScheduledTask:
    """调度任务"""
    priority: int
    created_at: datetime = field(compare=True)
    task_id: str = field(compare=False)
    task_type: str = field(compare=False)
    handler: Callable = field(compare=False)
    args: tuple = field(compare=False, default=())
    kwargs: dict = field(compare=False, default_factory=dict)
    callback: Optional[Callable] = field(compare=False, default=None)
    timeout: int = field(compare=False, default=60)
    retries: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=2)
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    retry_count: int = 0


class PriorityScheduler:
    """
    优先级调度器
    
    特点：
    1. 优先级队列，高优先级任务先执行
    2. 并发限制，防止资源耗尽
    3. 超时控制，防止任务卡死
    4. 重试机制，提高可靠性
    """
    
    _instance: Optional["PriorityScheduler"] = None
    
    def __init__(self, max_concurrent: int = 5):
        self._queue: List[ScheduledTask] = []
        self._max_concurrent = max_concurrent
        self._current_tasks = 0
        self._lock = asyncio.Lock()
        self._running = False
        self._task_results: Dict[str, TaskResult] = {}
        self._handlers: Dict[str, Callable] = {}
    
    def register_handler(self, task_type: str, handler: Callable):
        """注册任务处理器"""
        self._handlers[task_type] = handler
    
    async def submit(
        self,
        task_type: str,
        priority: Priority,
        handler: Callable = None,
        args: tuple = (),
        kwargs: dict = None,
        callback: Callable = None,
        timeout: int = 60,
        max_retries: int = 2
    ) -> str:
        """提交任务"""
        task_id = str(uuid.uuid4())[:8]
        
        if handler is None:
            handler = self._handlers.get(task_type)
            if handler is None:
                raise ValueError(f"No handler registered for task type: {task_type}")
        
        task = ScheduledTask(
            priority=int(priority),
            created_at=datetime.now(),
            task_id=task_id,
            task_type=task_type,
            handler=handler,
            args=args,
            kwargs=kwargs or {},
            callback=callback,
            timeout=timeout,
            max_retries=max_retries
        )
        
        async with self._lock:
            heapq.heappush(self._queue, task)
        
        return task_id
    
    async def submit_and_wait(
        self,
        task_type: str,
        priority: Priority,
        handler: Callable = None,
        args: tuple = (),
        kwargs: dict = None,
        timeout: int = 60
    ) -> TaskResult:
        """提交任务并等待结果"""
        future = asyncio.Future()
        
        def callback(result: TaskResult):
            if not future.done():
                future.set_result(result)
        
        task_id = await self.submit(
            task_type=task_type,
            priority=priority,
            handler=handler,
            args=args,
            kwargs=kwargs,
            callback=callback,
            timeout=timeout
        )
        
        try:
            result = await asyncio.wait_for(future, timeout=timeout + 10)
            return result
        except asyncio.TimeoutError:
            return TaskResult(
                task_id=task_id,
                success=False,
                error="Task timeout"
            )
    
    async def start(self):
        """启动调度器"""
        self._running = True
        while self._running:
            await self._process_next()
            await asyncio.sleep(0.01)
    
    async def stop(self):
        """停止调度器"""
        self._running = False
    
    async def _process_next(self):
        """处理下一个任务"""
        async with self._lock:
            if not self._queue or self._current_tasks >= self._max_concurrent:
                return
            
            task = heapq.heappop(self._queue)
            self._current_tasks += 1
        
        asyncio.create_task(self._execute_task(task))
    
    async def _execute_task(self, task: ScheduledTask):
        """执行任务"""
        start_time = datetime.now()
        
        try:
            if asyncio.iscoroutinefunction(task.handler):
                result = await asyncio.wait_for(
                    task.handler(*task.args, **task.kwargs),
                    timeout=task.timeout
                )
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: task.handler(*task.args, **task.kwargs)
                )
            
            execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            task_result = TaskResult(
                task_id=task.task_id,
                success=True,
                result=result,
                execution_time_ms=execution_time_ms,
                retry_count=task.retries
            )
            
        except asyncio.TimeoutError:
            task_result = TaskResult(
                task_id=task.task_id,
                success=False,
                error=f"Task timeout after {task.timeout}s",
                retry_count=task.retries
            )
            
            if task.retries < task.max_retries:
                await self._retry_task(task)
                return
                
        except Exception as e:
            task_result = TaskResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
                retry_count=task.retries
            )
            
            if task.retries < task.max_retries:
                await self._retry_task(task)
                return
        
        finally:
            async with self._lock:
                self._current_tasks -= 1
        
        self._task_results[task.task_id] = task_result
        
        if task.callback:
            try:
                if asyncio.iscoroutinefunction(task.callback):
                    await task.callback(task_result)
                else:
                    task.callback(task_result)
            except Exception as e:
                print(f"Callback error for task {task.task_id}: {e}")
    
    async def _retry_task(self, task: ScheduledTask):
        """重试任务"""
        task.retries += 1
        task.created_at = datetime.now()
        
        async with self._lock:
            heapq.heappush(self._queue, task)
    
    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """获取任务结果"""
        return self._task_results.get(task_id)
    
    def get_queue_status(self) -> Dict:
        """获取队列状态"""
        return {
            "queue_length": len(self._queue),
            "current_tasks": self._current_tasks,
            "max_concurrent": self._max_concurrent,
            "pending_by_priority": {
                str(Priority.REALTIME): sum(1 for t in self._queue if t.priority == Priority.REALTIME),
                str(Priority.INTERACTIVE): sum(1 for t in self._queue if t.priority == Priority.INTERACTIVE),
                str(Priority.UNDERSTANDING): sum(1 for t in self._queue if t.priority == Priority.UNDERSTANDING),
                str(Priority.BACKGROUND): sum(1 for t in self._queue if t.priority == Priority.BACKGROUND)
            }
        }
    
    @classmethod
    def get_instance(cls) -> "PriorityScheduler":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class LayerType(IntEnum):
    """层级类型"""
    CEREBELLUM = 0
    BRAINSTEM = 1
    BRAIN = 2


@dataclass
class LayerStatus:
    """层级状态"""
    layer: LayerType
    busy: bool = False
    current_task: Optional[str] = None
    queue_length: int = 0
    last_heartbeat: Optional[datetime] = None


class ThreeLayerCoordinator:
    """
    三层协同调度器
    
    协调小脑、脑干、大脑三层之间的任务分发和结果汇总
    
    小脑 (CEREBELLUM) - P0 实时级：
    - 唤醒词检测
    - 避障、平衡
    - 智能家居控制
    - 延迟 < 10ms
    
    脑干 (BRAINSTEM) - P1 交互级：
    - 简单对话
    - 语音识别/合成
    - 基础情感分析
    - 延迟 < 500ms
    
    大脑 (BRAIN) - P2/P3：
    - 复杂推理
    - 视觉理解
    - 图像生成
    - 延迟 100ms - 3s
    """
    
    _instance: Optional["ThreeLayerCoordinator"] = None
    
    def __init__(self):
        self._layer_status: Dict[LayerType, LayerStatus] = {
            LayerType.CEREBELLUM: LayerStatus(layer=LayerType.CEREBELLUM),
            LayerType.BRAINSTEM: LayerStatus(layer=LayerType.BRAINSTEM),
            LayerType.BRAIN: LayerStatus(layer=LayerType.BRAIN),
        }
        
        self._layer_handlers: Dict[LayerType, Dict[str, Callable]] = {
            layer: {} for layer in LayerType
        }
        
        self._fallback_responses = {
            "busy": "我现在有点忙，稍后回复你~",
            "thinking": "让我想想...",
            "processing": "正在处理中...",
        }
        
        self._task_layer_mapping = {
            LayerType.CEREBELLUM: {
                "wake_word", "obstacle_avoid", "motor_control",
                "smart_home_control", "emergency_stop", "balance"
            },
            LayerType.BRAINSTEM: {
                "simple_chat", "asr", "tts", "emotion_basic",
                "quick_response", "greeting"
            },
            LayerType.BRAIN: {
                "complex_reasoning", "visual_understanding",
                "deep_emotion", "image_generation", "long_context"
            }
        }
    
    def register_handler(self, layer: LayerType, task_type: str, handler: Callable):
        """注册层级处理器"""
        self._layer_handlers[layer][task_type] = handler
    
    def determine_layer(self, task_type: str, priority: Priority) -> LayerType:
        """确定任务应该由哪层处理"""
        for layer, tasks in self._task_layer_mapping.items():
            if task_type in tasks:
                return layer
        
        if priority == Priority.REALTIME:
            return LayerType.CEREBELLUM
        elif priority == Priority.INTERACTIVE:
            return LayerType.BRAINSTEM
        else:
            return LayerType.BRAIN
    
    async def dispatch(
        self,
        task_type: str,
        data: Dict,
        priority: Priority = Priority.INTERACTIVE,
        timeout: int = 30
    ) -> Dict:
        """分发任务到合适的层级"""
        target_layer = self.determine_layer(task_type, priority)
        
        handler = self._layer_handlers[target_layer].get(task_type)
        
        if not handler:
            return {
                "success": False,
                "error": f"No handler for task type: {task_type}",
                "layer": target_layer.name
            }
        
        layer_status = self._layer_status[target_layer]
        layer_status.busy = True
        layer_status.current_task = task_type
        
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await asyncio.wait_for(
                    handler(data),
                    timeout=timeout
                )
            else:
                result = handler(data)
            
            return {
                "success": True,
                "result": result,
                "layer": target_layer.name
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Timeout",
                "layer": target_layer.name,
                "fallback": self._fallback_responses.get("busy")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "layer": target_layer.name
            }
            
        finally:
            layer_status.busy = False
            layer_status.current_task = None
            layer_status.last_heartbeat = datetime.now()
    
    async def dispatch_with_fallback(
        self,
        task_type: str,
        data: Dict,
        priority: Priority = Priority.INTERACTIVE
    ) -> Dict:
        """带降级的任务分发"""
        target_layer = self.determine_layer(task_type, priority)
        
        result = await self.dispatch(task_type, data, priority)
        
        if result["success"]:
            return result
        
        fallback_layer = self._get_fallback_layer(target_layer)
        if fallback_layer and fallback_layer != target_layer:
            fallback_result = await self.dispatch(
                task_type, data, priority,
                timeout=10
            )
            if fallback_result["success"]:
                return fallback_result
        
        return {
            "success": False,
            "error": result.get("error"),
            "fallback_response": self._fallback_responses.get("busy"),
            "original_layer": target_layer.name
        }
    
    def _get_fallback_layer(self, layer: LayerType) -> Optional[LayerType]:
        """获取降级层级"""
        fallback_map = {
            LayerType.BRAIN: LayerType.BRAINSTEM,
            LayerType.BRAINSTEM: LayerType.CEREBELLUM,
            LayerType.CEREBELLUM: None
        }
        return fallback_map.get(layer)
    
    def get_layer_status(self, layer: LayerType) -> LayerStatus:
        """获取层级状态"""
        return self._layer_status[layer]
    
    def get_all_status(self) -> Dict:
        """获取所有层级状态"""
        return {
            layer.name: {
                "busy": status.busy,
                "current_task": status.current_task,
                "last_heartbeat": status.last_heartbeat.isoformat() if status.last_heartbeat else None
            }
            for layer, status in self._layer_status.items()
        }
    
    @classmethod
    def get_instance(cls) -> "ThreeLayerCoordinator":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
