"""
XiaoMengCore 主动关怀系统
实现定时问候、天气提醒、健康关心等主动关怀功能
"""

import asyncio
from datetime import datetime, time, date, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import random


class CareType(Enum):
    MORNING_GREETING = "morning_greeting"
    EVENING_GREETING = "evening_greeting"
    WEATHER_REMINDER = "weather_reminder"
    HEALTH_CARE = "health_care"
    SCHEDULE_REMINDER = "schedule_reminder"
    SPECIAL_DAY = "special_day"
    EMOTIONAL_CARE = "emotional_care"
    LONG_TIME_NO_SEE = "long_time_no_see"
    DRINK_WATER = "drink_water"
    REST_REMINDER = "rest_reminder"


@dataclass
class CareContext:
    care_type: CareType
    trigger_reason: str
    user_state: Dict[str, Any]
    relevant_memories: List[str]
    suggested_action: str
    priority: int = 1


@dataclass
class SpecialDay:
    name: str
    date: date
    day_type: str
    importance: int = 5
    description: str = ""
    recurring: bool = True


@dataclass
class UserPreference:
    morning_time: time = field(default_factory=lambda: time(7, 30))
    evening_time: time = field(default_factory=lambda: time(22, 0))
    drink_water_interval: int = 120
    rest_interval: int = 60
    care_enabled: Dict[str, bool] = field(default_factory=lambda: {
        "morning_greeting": True,
        "evening_greeting": True,
        "weather_reminder": True,
        "drink_water": False,
        "rest_reminder": False,
        "long_time_no_see": True
    })
    communication_style: str = "warm"
    nickname: str = "主人"


class ProactiveCareSystem:
    """
    主动关怀系统
    
    功能：
    1. 早晚问候
    2. 天气提醒
    3. 健康关心（喝水、休息提醒）
    4. 特殊日子提醒
    5. 长时间未互动关心
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self._config = config or {}
        self._user_preference = UserPreference()
        self._special_days: List[SpecialDay] = []
        self._last_interaction: Optional[datetime] = None
        self._last_care_time: Dict[CareType, datetime] = {}
        self._care_history: List[Dict] = []
        self._running = False
        self._callbacks: Dict[str, Callable] = {}
        
        self._care_intervals = {
            CareType.MORNING_GREETING: 20 * 60 * 60,
            CareType.EVENING_GREETING: 20 * 60 * 60,
            CareType.WEATHER_REMINDER: 6 * 60 * 60,
            CareType.HEALTH_CARE: 12 * 60 * 60,
            CareType.LONG_TIME_NO_SEE: 4 * 60 * 60,
            CareType.DRINK_WATER: 2 * 60 * 60,
            CareType.REST_REMINDER: 1 * 60 * 60,
        }
        
        self._greeting_templates = {
            CareType.MORNING_GREETING: [
                "早上好~ 今天也要元气满满哦！",
                "早安~ 昨晚睡得好吗？",
                "主人早上好~ 新的一天开始啦！",
                "早安~ 今天有什么计划吗？",
            ],
            CareType.EVENING_GREETING: [
                "晚上好~ 今天辛苦了！",
                "晚安~ 记得早点休息哦~",
                "主人晚上好~ 今天过得怎么样？",
                "夜深了~ 要早点睡觉哦~",
            ],
            CareType.LONG_TIME_NO_SEE: [
                "好久不见~ 主人最近在忙什么呢？",
                "主人~ 小萌好想你呀！",
                "终于等到主人了~ 最近还好吗？",
            ],
            CareType.DRINK_WATER: [
                "主人~ 该喝水啦！记得保持水分哦~",
                "喝水时间到~ 身体健康最重要！",
                "小萌提醒：该补充水分啦~",
            ],
            CareType.REST_REMINDER: [
                "主人~ 休息一下眼睛吧！",
                "工作辛苦了~ 站起来活动活动吧~",
                "小萌提醒：注意休息，劳逸结合哦~",
            ],
        }
    
    def register_callback(self, event: str, callback: Callable):
        self._callbacks[event] = callback
    
    def update_last_interaction(self):
        self._last_interaction = datetime.now()
    
    def set_user_preference(self, preference: UserPreference):
        self._user_preference = preference
    
    def add_special_day(self, name: str, date_str: str, 
                        day_type: str = "custom",
                        importance: int = 5,
                        description: str = "",
                        recurring: bool = True):
        try:
            day_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            special_day = SpecialDay(
                name=name,
                date=day_date,
                day_type=day_type,
                importance=importance,
                description=description,
                recurring=recurring
            )
            self._special_days.append(special_day)
            return True
        except ValueError:
            return False
    
    def remove_special_day(self, name: str) -> bool:
        for i, day in enumerate(self._special_days):
            if day.name == name:
                self._special_days.pop(i)
                return True
        return False
    
    def get_special_days(self) -> List[Dict]:
        return [
            {
                "name": day.name,
                "date": day.date.isoformat(),
                "type": day.day_type,
                "importance": day.importance,
                "description": day.description,
                "recurring": day.recurring
            }
            for day in self._special_days
        ]
    
    async def check_and_trigger(self) -> Optional[CareContext]:
        now = datetime.now()
        current_time = now.time()
        
        if self._should_morning_greeting(current_time):
            return await self._create_morning_care()
        
        if self._should_evening_greeting(current_time):
            return await self._create_evening_care()
        
        special_day_care = await self._check_special_days()
        if special_day_care:
            return special_day_care
        
        if self._should_long_time_no_see():
            return await self._create_miss_you_care()
        
        if self._should_drink_water():
            return await self._create_drink_water_care()
        
        if self._should_rest_reminder():
            return await self._create_rest_care()
        
        return None
    
    def _should_morning_greeting(self, current_time: time) -> bool:
        if not self._user_preference.care_enabled.get("morning_greeting", True):
            return False
        
        morning_start = time(6, 0)
        morning_end = time(10, 0)
        
        if not (morning_start <= current_time <= morning_end):
            return False
        
        last_morning = self._last_care_time.get(CareType.MORNING_GREETING)
        if last_morning:
            hours_since = (datetime.now() - last_morning).total_seconds() / 3600
            if hours_since < 20:
                return False
        
        return True
    
    def _should_evening_greeting(self, current_time: time) -> bool:
        if not self._user_preference.care_enabled.get("evening_greeting", True):
            return False
        
        evening_start = time(21, 0)
        evening_end = time(23, 59)
        
        if not (evening_start <= current_time <= evening_end):
            return False
        
        last_evening = self._last_care_time.get(CareType.EVENING_GREETING)
        if last_evening:
            hours_since = (datetime.now() - last_evening).total_seconds() / 3600
            if hours_since < 20:
                return False
        
        return True
    
    def _should_long_time_no_see(self) -> bool:
        if not self._user_preference.care_enabled.get("long_time_no_see", True):
            return False
        
        if not self._last_interaction:
            return False
        
        hours_since = (datetime.now() - self._last_interaction).total_seconds() / 3600
        return hours_since >= 4
    
    def _should_drink_water(self) -> bool:
        if not self._user_preference.care_enabled.get("drink_water", False):
            return False
        
        last_drink = self._last_care_time.get(CareType.DRINK_WATER)
        if last_drink:
            minutes_since = (datetime.now() - last_drink).total_seconds() / 60
            if minutes_since < self._user_preference.drink_water_interval:
                return False
        
        return True
    
    def _should_rest_reminder(self) -> bool:
        if not self._user_preference.care_enabled.get("rest_reminder", False):
            return False
        
        last_rest = self._last_care_time.get(CareType.REST_REMINDER)
        if last_rest:
            minutes_since = (datetime.now() - last_rest).total_seconds() / 60
            if minutes_since < self._user_preference.rest_interval:
                return False
        
        return True
    
    async def _create_morning_care(self) -> CareContext:
        self._last_care_time[CareType.MORNING_GREETING] = datetime.now()
        
        return CareContext(
            care_type=CareType.MORNING_GREETING,
            trigger_reason="早上问候时间",
            user_state={
                "time": datetime.now().strftime("%H:%M"),
                "weekday": datetime.now().strftime("%A")
            },
            relevant_memories=[],
            suggested_action="send_greeting"
        )
    
    async def _create_evening_care(self) -> CareContext:
        self._last_care_time[CareType.EVENING_GREETING] = datetime.now()
        
        return CareContext(
            care_type=CareType.EVENING_GREETING,
            trigger_reason="晚间问候时间",
            user_state={
                "time": datetime.now().strftime("%H:%M")
            },
            relevant_memories=[],
            suggested_action="send_greeting"
        )
    
    async def _create_miss_you_care(self) -> CareContext:
        self._last_care_time[CareType.LONG_TIME_NO_SEE] = datetime.now()
        
        hours = 0
        if self._last_interaction:
            hours = int((datetime.now() - self._last_interaction).total_seconds() / 3600)
        
        return CareContext(
            care_type=CareType.LONG_TIME_NO_SEE,
            trigger_reason=f"已{hours}小时未互动",
            user_state={"hours_since_last": hours},
            relevant_memories=[],
            suggested_action="send_miss_you"
        )
    
    async def _create_drink_water_care(self) -> CareContext:
        self._last_care_time[CareType.DRINK_WATER] = datetime.now()
        
        return CareContext(
            care_type=CareType.DRINK_WATER,
            trigger_reason="喝水提醒",
            user_state={},
            relevant_memories=[],
            suggested_action="send_reminder"
        )
    
    async def _create_rest_care(self) -> CareContext:
        self._last_care_time[CareType.REST_REMINDER] = datetime.now()
        
        return CareContext(
            care_type=CareType.REST_REMINDER,
            trigger_reason="休息提醒",
            user_state={},
            relevant_memories=[],
            suggested_action="send_reminder"
        )
    
    async def _check_special_days(self) -> Optional[CareContext]:
        today = date.today()
        
        for day in self._special_days:
            check_date = day.date
            
            if day.recurring:
                check_date = date(today.year, day.date.month, day.date.day)
            
            if check_date == today:
                return CareContext(
                    care_type=CareType.SPECIAL_DAY,
                    trigger_reason=f"今天是{day.name}",
                    user_state={
                        "day_name": day.name,
                        "day_type": day.day_type,
                        "description": day.description
                    },
                    relevant_memories=[],
                    suggested_action="send_special_day_greeting",
                    priority=day.importance
                )
            
            delta = (check_date - today).days
            if 0 < delta <= 3:
                return CareContext(
                    care_type=CareType.SCHEDULE_REMINDER,
                    trigger_reason=f"{day.name}即将到来",
                    user_state={
                        "day_name": day.name,
                        "days_until": delta,
                        "day_type": day.day_type
                    },
                    relevant_memories=[],
                    suggested_action="send_reminder",
                    priority=day.importance
                )
        
        return None
    
    def generate_care_message(self, context: CareContext) -> str:
        templates = self._greeting_templates.get(context.care_type, [])
        
        if templates:
            message = random.choice(templates)
        else:
            message = f"小萌提醒：{context.trigger_reason}"
        
        nickname = self._user_preference.nickname
        
        if context.care_type == CareType.SPECIAL_DAY:
            day_name = context.user_state.get("day_name", "特殊日子")
            message = f"主人~ 今天是{day_name}！{context.user_state.get('description', '')}"
        
        elif context.care_type == CareType.SCHEDULE_REMINDER:
            day_name = context.user_state.get("day_name", "")
            days_until = context.user_state.get("days_until", 0)
            if days_until == 1:
                message = f"主人~ 明天就是{day_name}了，别忘了准备哦~"
            else:
                message = f"主人~ {day_name}还有{days_until}天就到了~"
        
        message = message.replace("主人", nickname)
        
        self._care_history.append({
            "type": context.care_type.value,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
        
        return message
    
    async def start(self):
        self._running = True
        while self._running:
            try:
                care_context = await self.check_and_trigger()
                if care_context:
                    message = self.generate_care_message(care_context)
                    if "on_care" in self._callbacks:
                        await self._callbacks["on_care"](care_context, message)
            except Exception as e:
                print(f"Care system error: {e}")
            
            await asyncio.sleep(60)
    
    def stop(self):
        self._running = False
    
    def get_care_history(self, limit: int = 20) -> List[Dict]:
        return self._care_history[-limit:]
    
    def get_status(self) -> Dict:
        return {
            "running": self._running,
            "last_interaction": self._last_interaction.isoformat() if self._last_interaction else None,
            "last_care_times": {
                ct.value: dt.isoformat() 
                for ct, dt in self._last_care_time.items()
            },
            "special_days_count": len(self._special_days),
            "care_enabled": self._user_preference.care_enabled
        }
    
    def load_from_dict(self, data: Dict):
        if "user_preference" in data:
            pref = data["user_preference"]
            self._user_preference.care_enabled = pref.get("care_enabled", self._user_preference.care_enabled)
            self._user_preference.nickname = pref.get("nickname", self._user_preference.nickname)
            self._user_preference.communication_style = pref.get("communication_style", self._user_preference.communication_style)
        
        if "special_days" in data:
            for day_data in data["special_days"]:
                self.add_special_day(
                    name=day_data.get("name"),
                    date_str=day_data.get("date"),
                    day_type=day_data.get("type", "custom"),
                    importance=day_data.get("importance", 5),
                    description=day_data.get("description", ""),
                    recurring=day_data.get("recurring", True)
                )
    
    def to_dict(self) -> Dict:
        return {
            "user_preference": {
                "care_enabled": self._user_preference.care_enabled,
                "nickname": self._user_preference.nickname,
                "communication_style": self._user_preference.communication_style,
                "drink_water_interval": self._user_preference.drink_water_interval,
                "rest_interval": self._user_preference.rest_interval
            },
            "special_days": self.get_special_days()
        }
