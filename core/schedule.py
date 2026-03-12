"""
XiaoMengCore 日程管理系统
支持日程添加、查询、提醒等功能
"""

from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import re


class ScheduleType(Enum):
    MEETING = "meeting"
    APPOINTMENT = "appointment"
    TASK = "task"
    REMINDER = "reminder"
    EVENT = "event"
    DEADLINE = "deadline"


class SchedulePriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class ScheduleStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"


@dataclass
class ScheduleItem:
    id: str
    title: str
    start_time: datetime
    end_time: Optional[datetime] = None
    schedule_type: ScheduleType = ScheduleType.TASK
    priority: SchedulePriority = SchedulePriority.MEDIUM
    status: ScheduleStatus = ScheduleStatus.PENDING
    description: str = ""
    location: str = ""
    participants: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    reminders: List[int] = field(default_factory=lambda: [30])
    recurring: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "type": self.schedule_type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "description": self.description,
            "location": self.location,
            "participants": self.participants,
            "tags": self.tags,
            "reminders": self.reminders,
            "recurring": self.recurring,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ScheduleItem":
        return cls(
            id=data["id"],
            title=data["title"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            schedule_type=ScheduleType(data.get("type", "task")),
            priority=SchedulePriority(data.get("priority", 2)),
            status=ScheduleStatus(data.get("status", "pending")),
            description=data.get("description", ""),
            location=data.get("location", ""),
            participants=data.get("participants", []),
            tags=data.get("tags", []),
            reminders=data.get("reminders", [30]),
            recurring=data.get("recurring"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()
        )


class ScheduleManager:
    """
    日程管理器
    
    功能：
    1. 添加/删除/修改日程
    2. 查询日程（按日期、类型、标签）
    3. 日程提醒
    4. 重复日程
    5. 日程冲突检测
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self._schedules: Dict[str, ScheduleItem] = {}
        self._storage_path = storage_path
        self._reminder_callbacks: List[Any] = []
        
        if storage_path:
            self._load_from_file()
    
    def _generate_id(self) -> str:
        import uuid
        return f"sch_{uuid.uuid4().hex[:8]}"
    
    def add_schedule(
        self,
        title: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        schedule_type: ScheduleType = ScheduleType.TASK,
        priority: SchedulePriority = SchedulePriority.MEDIUM,
        description: str = "",
        location: str = "",
        participants: List[str] = None,
        tags: List[str] = None,
        reminders: List[int] = None,
        recurring: str = None
    ) -> ScheduleItem:
        
        schedule_id = self._generate_id()
        
        schedule = ScheduleItem(
            id=schedule_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            schedule_type=schedule_type,
            priority=priority,
            description=description,
            location=location,
            participants=participants or [],
            tags=tags or [],
            reminders=reminders or [30],
            recurring=recurring
        )
        
        self._schedules[schedule_id] = schedule
        self._save_to_file()
        
        return schedule
    
    def get_schedule(self, schedule_id: str) -> Optional[ScheduleItem]:
        return self._schedules.get(schedule_id)
    
    def update_schedule(self, schedule_id: str, **kwargs) -> Optional[ScheduleItem]:
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return None
        
        for key, value in kwargs.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)
        
        schedule.updated_at = datetime.now()
        self._save_to_file()
        
        return schedule
    
    def delete_schedule(self, schedule_id: str) -> bool:
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]
            self._save_to_file()
            return True
        return False
    
    def get_schedules_by_date(self, target_date: date) -> List[ScheduleItem]:
        schedules = []
        for schedule in self._schedules.values():
            if schedule.start_time.date() == target_date:
                schedules.append(schedule)
        return sorted(schedules, key=lambda s: s.start_time)
    
    def get_schedules_by_range(self, start_date: date, end_date: date) -> List[ScheduleItem]:
        schedules = []
        for schedule in self._schedules.values():
            schedule_date = schedule.start_time.date()
            if start_date <= schedule_date <= end_date:
                schedules.append(schedule)
        return sorted(schedules, key=lambda s: s.start_time)
    
    def get_today_schedules(self) -> List[ScheduleItem]:
        return self.get_schedules_by_date(date.today())
    
    def get_upcoming_schedules(self, hours: int = 24) -> List[ScheduleItem]:
        now = datetime.now()
        end_time = now + timedelta(hours=hours)
        
        schedules = []
        for schedule in self._schedules.values():
            if now <= schedule.start_time <= end_time:
                schedules.append(schedule)
        
        return sorted(schedules, key=lambda s: s.start_time)
    
    def get_schedules_by_type(self, schedule_type: ScheduleType) -> List[ScheduleItem]:
        return [
            s for s in self._schedules.values()
            if s.schedule_type == schedule_type
        ]
    
    def get_schedules_by_tag(self, tag: str) -> List[ScheduleItem]:
        return [
            s for s in self._schedules.values()
            if tag in s.tags
        ]
    
    def check_conflicts(self, new_schedule: ScheduleItem) -> List[ScheduleItem]:
        conflicts = []
        
        for schedule in self._schedules.values():
            if schedule.id == new_schedule.id:
                continue
            
            if new_schedule.end_time:
                if (schedule.start_time < new_schedule.end_time and
                    (schedule.end_time is None or schedule.end_time > new_schedule.start_time)):
                    conflicts.append(schedule)
            elif schedule.end_time:
                if schedule.start_time <= new_schedule.start_time < schedule.end_time:
                    conflicts.append(schedule)
        
        return conflicts
    
    def mark_completed(self, schedule_id: str) -> Optional[ScheduleItem]:
        return self.update_schedule(schedule_id, status=ScheduleStatus.COMPLETED)
    
    def mark_cancelled(self, schedule_id: str) -> Optional[ScheduleItem]:
        return self.update_schedule(schedule_id, status=ScheduleStatus.CANCELLED)
    
    def get_pending_reminders(self) -> List[tuple]:
        now = datetime.now()
        reminders = []
        
        for schedule in self._schedules.values():
            if schedule.status != ScheduleStatus.PENDING:
                continue
            
            for minutes_before in schedule.reminders:
                reminder_time = schedule.start_time - timedelta(minutes=minutes_before)
                
                if now <= reminder_time <= now + timedelta(minutes=1):
                    reminders.append((schedule, minutes_before))
        
        return reminders
    
    def parse_natural_time(self, text: str) -> Optional[datetime]:
        now = datetime.now()
        
        patterns = {
            r"今天(\d+)点(\d+)?分?": lambda m: now.replace(
                hour=int(m.group(1)), 
                minute=int(m.group(2)) if m.group(2) else 0
            ),
            r"明天(\d+)点(\d+)?分?": lambda m: (now + timedelta(days=1)).replace(
                hour=int(m.group(1)),
                minute=int(m.group(2)) if m.group(2) else 0
            ),
            r"后天(\d+)点(\d+)?分?": lambda m: (now + timedelta(days=2)).replace(
                hour=int(m.group(1)),
                minute=int(m.group(2)) if m.group(2) else 0
            ),
            r"下周([一二三四五六日])(\d+)点": self._parse_next_week,
            r"(\d+)月(\d+)日(\d+)点(\d+)?分?": lambda m: datetime(
                now.year, int(m.group(1)), int(m.group(2)),
                int(m.group(3)), int(m.group(4)) if m.group(4) else 0
            ),
        }
        
        for pattern, parser in patterns.items():
            match = re.search(pattern, text)
            if match:
                try:
                    return parser(match)
                except:
                    continue
        
        return None
    
    def _parse_next_week(self, match) -> datetime:
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}
        target_weekday = weekday_map.get(match.group(1), 0)
        hour = int(match.group(2))
        
        now = datetime.now()
        days_ahead = target_weekday - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        
        return (now + timedelta(days=days_ahead)).replace(hour=hour, minute=0)
    
    def get_schedule_summary(self, target_date: Optional[date] = None) -> Dict:
        target = target_date or date.today()
        schedules = self.get_schedules_by_date(target)
        
        return {
            "date": target.isoformat(),
            "total": len(schedules),
            "by_type": {
                t.value: len([s for s in schedules if s.schedule_type == t])
                for t in ScheduleType
            },
            "by_priority": {
                p.value: len([s for s in schedules if s.priority == p])
                for p in SchedulePriority
            },
            "completed": len([s for s in schedules if s.status == ScheduleStatus.COMPLETED]),
            "pending": len([s for s in schedules if s.status == ScheduleStatus.PENDING])
        }
    
    def _save_to_file(self):
        if not self._storage_path:
            return
        
        try:
            data = {
                "schedules": [s.to_dict() for s in self._schedules.values()]
            }
            with open(self._storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Save schedules failed: {e}")
    
    def _load_from_file(self):
        if not self._storage_path:
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for schedule_data in data.get("schedules", []):
                schedule = ScheduleItem.from_dict(schedule_data)
                self._schedules[schedule.id] = schedule
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Load schedules failed: {e}")
    
    def to_dict(self) -> Dict:
        return {
            "schedules": [s.to_dict() for s in self._schedules.values()]
        }
