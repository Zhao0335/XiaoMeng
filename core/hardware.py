"""
XiaoMengCore 硬件控制接口
预留小车、摄像头、语音等硬件控制能力
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio


class DeviceType(Enum):
    """设备类型"""
    MOTOR = "motor"
    CAMERA = "camera"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    DISPLAY = "display"
    SENSOR = "sensor"
    LED = "led"
    SERVO = "servo"


@dataclass
class DeviceState:
    """设备状态"""
    device_id: str
    device_type: DeviceType
    is_connected: bool = False
    is_active: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)
    last_update: Optional[str] = None


class BaseDevice(ABC):
    """设备基类"""
    
    def __init__(self, device_id: str, device_type: DeviceType):
        self.device_id = device_id
        self.device_type = device_type
        self._state = DeviceState(
            device_id=device_id,
            device_type=device_type
        )
        self._callbacks: List[Callable] = []
    
    @abstractmethod
    async def connect(self) -> bool:
        """连接设备"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """断开设备"""
        pass
    
    @abstractmethod
    async def execute_command(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行命令"""
        pass
    
    @property
    def state(self) -> DeviceState:
        """获取设备状态"""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._state.is_connected
    
    def on_state_change(self, callback: Callable):
        """注册状态变化回调"""
        self._callbacks.append(callback)
    
    async def _notify_state_change(self):
        """通知状态变化"""
        for callback in self._callbacks:
            try:
                await callback(self._state)
            except Exception as e:
                print(f"Callback error: {e}")


class MotorController(BaseDevice):
    """
    电机控制器
    
    用于控制小车运动
    """
    
    def __init__(self, device_id: str = "motor_main"):
        super().__init__(device_id, DeviceType.MOTOR)
        self._speed = 0
        self._direction = "stop"
    
    async def connect(self) -> bool:
        """连接电机"""
        try:
            self._state.is_connected = True
            self._state.is_active = True
            await self._notify_state_change()
            return True
        except Exception as e:
            print(f"Motor connect error: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """断开电机"""
        try:
            await self.stop()
            self._state.is_connected = False
            self._state.is_active = False
            await self._notify_state_change()
            return True
        except Exception as e:
            return False
    
    async def execute_command(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行电机命令"""
        params = params or {}
        
        commands = {
            "forward": self.forward,
            "backward": self.backward,
            "left": self.turn_left,
            "right": self.turn_right,
            "stop": self.stop,
            "set_speed": self.set_speed
        }
        
        if command in commands:
            return await commands[command](**params)
        
        return {"success": False, "error": f"未知命令: {command}"}
    
    async def forward(self, speed: int = 50) -> Dict[str, Any]:
        """前进"""
        self._speed = speed
        self._direction = "forward"
        self._state.properties["speed"] = speed
        self._state.properties["direction"] = "forward"
        await self._notify_state_change()
        return {"success": True, "action": "forward", "speed": speed}
    
    async def backward(self, speed: int = 50) -> Dict[str, Any]:
        """后退"""
        self._speed = speed
        self._direction = "backward"
        self._state.properties["speed"] = speed
        self._state.properties["direction"] = "backward"
        await self._notify_state_change()
        return {"success": True, "action": "backward", "speed": speed}
    
    async def turn_left(self, speed: int = 30) -> Dict[str, Any]:
        """左转"""
        self._speed = speed
        self._direction = "left"
        self._state.properties["speed"] = speed
        self._state.properties["direction"] = "left"
        await self._notify_state_change()
        return {"success": True, "action": "turn_left", "speed": speed}
    
    async def turn_right(self, speed: int = 30) -> Dict[str, Any]:
        """右转"""
        self._speed = speed
        self._direction = "right"
        self._state.properties["speed"] = speed
        self._state.properties["direction"] = "right"
        await self._notify_state_change()
        return {"success": True, "action": "turn_right", "speed": speed}
    
    async def stop(self) -> Dict[str, Any]:
        """停止"""
        self._speed = 0
        self._direction = "stop"
        self._state.properties["speed"] = 0
        self._state.properties["direction"] = "stop"
        await self._notify_state_change()
        return {"success": True, "action": "stop"}
    
    async def set_speed(self, speed: int) -> Dict[str, Any]:
        """设置速度"""
        self._speed = max(0, min(100, speed))
        self._state.properties["speed"] = self._speed
        await self._notify_state_change()
        return {"success": True, "speed": self._speed}


class CameraController(BaseDevice):
    """
    摄像头控制器
    """
    
    def __init__(self, device_id: str = "camera_main", camera_index: int = 0):
        super().__init__(device_id, DeviceType.CAMERA)
        self._camera_index = camera_index
        self._capture = None
    
    async def connect(self) -> bool:
        """连接摄像头"""
        try:
            import cv2
            self._capture = cv2.VideoCapture(self._camera_index)
            if self._capture.isOpened():
                self._state.is_connected = True
                self._state.is_active = True
                await self._notify_state_change()
                return True
            return False
        except ImportError:
            print("需要安装 opencv-python: pip install opencv-python")
            return False
        except Exception as e:
            print(f"Camera connect error: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """断开摄像头"""
        try:
            if self._capture:
                self._capture.release()
            self._state.is_connected = False
            self._state.is_active = False
            await self._notify_state_change()
            return True
        except Exception as e:
            return False
    
    async def execute_command(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行摄像头命令"""
        params = params or {}
        
        commands = {
            "capture": self.capture,
            "start_stream": self.start_stream,
            "stop_stream": self.stop_stream
        }
        
        if command in commands:
            return await commands[command](**params)
        
        return {"success": False, "error": f"未知命令: {command}"}
    
    async def capture(self, save_path: str = None) -> Dict[str, Any]:
        """拍照"""
        if not self._capture or not self._state.is_connected:
            return {"success": False, "error": "摄像头未连接"}
        
        try:
            import cv2
            ret, frame = self._capture.read()
            if ret:
                if save_path:
                    cv2.imwrite(save_path, frame)
                    return {"success": True, "path": save_path}
                else:
                    return {"success": True, "message": "拍照成功"}
            return {"success": False, "error": "拍照失败"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def start_stream(self) -> Dict[str, Any]:
        """开始视频流"""
        self._state.properties["streaming"] = True
        await self._notify_state_change()
        return {"success": True, "message": "视频流已启动"}
    
    async def stop_stream(self) -> Dict[str, Any]:
        """停止视频流"""
        self._state.properties["streaming"] = False
        await self._notify_state_change()
        return {"success": True, "message": "视频流已停止"}


class DisplayController(BaseDevice):
    """
    显示器控制器
    
    用于控制小车上的表情显示
    """
    
    def __init__(self, device_id: str = "display_main"):
        super().__init__(device_id, DeviceType.DISPLAY)
        self._current_emotion = "neutral"
        self._current_text = ""
    
    async def connect(self) -> bool:
        """连接显示器"""
        self._state.is_connected = True
        self._state.is_active = True
        await self._notify_state_change()
        return True
    
    async def disconnect(self) -> bool:
        """断开显示器"""
        self._state.is_connected = False
        self._state.is_active = False
        await self._notify_state_change()
        return True
    
    async def execute_command(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行显示命令"""
        params = params or {}
        
        commands = {
            "show_emotion": self.show_emotion,
            "show_text": self.show_text,
            "clear": self.clear
        }
        
        if command in commands:
            return await commands[command](**params)
        
        return {"success": False, "error": f"未知命令: {command}"}
    
    async def show_emotion(self, emotion: str) -> Dict[str, Any]:
        """显示表情"""
        valid_emotions = ["happy", "sad", "angry", "neutral", "excited", "shy", "caring"]
        if emotion not in valid_emotions:
            return {"success": False, "error": f"无效表情: {emotion}"}
        
        self._current_emotion = emotion
        self._state.properties["emotion"] = emotion
        await self._notify_state_change()
        return {"success": True, "emotion": emotion}
    
    async def show_text(self, text: str, duration: int = 3000) -> Dict[str, Any]:
        """显示文字"""
        self._current_text = text
        self._state.properties["text"] = text
        await self._notify_state_change()
        
        if duration > 0:
            asyncio.create_task(self._clear_after(duration))
        
        return {"success": True, "text": text}
    
    async def _clear_after(self, ms: int):
        """延时清除"""
        await asyncio.sleep(ms / 1000)
        self._current_text = ""
    
    async def clear(self) -> Dict[str, Any]:
        """清除显示"""
        self._current_emotion = "neutral"
        self._current_text = ""
        self._state.properties["emotion"] = "neutral"
        self._state.properties["text"] = ""
        await self._notify_state_change()
        return {"success": True, "message": "已清除"}


class HardwareManager:
    """
    硬件管理器
    
    统一管理所有硬件设备
    """
    
    _instance: Optional["HardwareManager"] = None
    
    def __init__(self):
        self._devices: Dict[str, BaseDevice] = {}
        self._initialized = False
    
    async def initialize(self):
        """初始化硬件管理器"""
        if self._initialized:
            return
        
        self._initialized = True
    
    def register_device(self, device: BaseDevice):
        """注册设备"""
        self._devices[device.device_id] = device
    
    def get_device(self, device_id: str) -> Optional[BaseDevice]:
        """获取设备"""
        return self._devices.get(device_id)
    
    def get_devices_by_type(self, device_type: DeviceType) -> List[BaseDevice]:
        """按类型获取设备"""
        return [d for d in self._devices.values() if d.device_type == device_type]
    
    def get_all_devices(self) -> List[BaseDevice]:
        """获取所有设备"""
        return list(self._devices.values())
    
    async def connect_all(self):
        """连接所有设备"""
        for device in self._devices.values():
            await device.connect()
    
    async def disconnect_all(self):
        """断开所有设备"""
        for device in self._devices.values():
            await device.disconnect()
    
    async def execute(self, device_id: str, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行设备命令"""
        device = self._devices.get(device_id)
        if not device:
            return {"success": False, "error": f"设备不存在: {device_id}"}
        
        if not device.is_connected:
            return {"success": False, "error": f"设备未连接: {device_id}"}
        
        return await device.execute_command(command, params)
    
    def get_device_states(self) -> Dict[str, DeviceState]:
        """获取所有设备状态"""
        return {d.device_id: d.state for d in self._devices.values()}
    
    @classmethod
    def get_instance(cls) -> "HardwareManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class HardwareTool:
    """硬件控制工具 - 供 AI 调用"""
    
    @staticmethod
    def get_tools_schema() -> List[Dict]:
        """获取硬件工具 schema"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "hardware_control",
                    "description": "控制硬件设备（小车、摄像头、显示器等）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "设备ID（如 motor_main, camera_main, display_main）"
                            },
                            "command": {
                                "type": "string",
                                "description": "命令（如 forward, backward, stop, capture, show_emotion）"
                            },
                            "params": {
                                "type": "object",
                                "description": "命令参数"
                            }
                        },
                        "required": ["device_id", "command"]
                    }
                }
            }
        ]
    
    @staticmethod
    async def execute(user, device_id: str, command: str, params: Dict = None) -> Dict:
        """执行硬件控制"""
        from models import UserLevel
        
        if user.level != UserLevel.OWNER:
            return {"success": False, "error": "只有主人能控制硬件"}
        
        hw_manager = HardwareManager.get_instance()
        return await hw_manager.execute(device_id, command, params)
