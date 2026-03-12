"""
XiaoMengCore 待办事项系统
支持任务管理、优先级、进度跟踪等功能
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import uuid


class TodoPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class TodoStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class TodoCategory(Enum):
    WORK = "work"
    PERSONAL = "personal"
    STUDY = "study"
    HEALTH = "health"
    FINANCE = "finance"
    SHOPPING = "shopping"
    OTHER = "other"


@dataclass
class TodoItem:
    id: str
    title: str
    description: str = ""
    priority: TodoPriority = TodoPriority.MEDIUM
    status: TodoStatus = TodoStatus.PENDING
    category: TodoCategory = TodoCategory.OTHER
    due_date: Optional[date] = None
    due_time: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    reminder: Optional[datetime] = None
    notes: str = ""
    progress: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "category": self.category.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "due_time": self.due_time,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
            "subtasks": self.subtasks,
            "parent_id": self.parent_id,
            "estimated_minutes": self.estimated_minutes,
            "actual_minutes": self.actual_minutes,
            "reminder": self.reminder.isoformat() if self.reminder else None,
            "notes": self.notes,
            "progress": self.progress
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TodoItem":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            priority=TodoPriority(data.get("priority", 2)),
            status=TodoStatus(data.get("status", "pending")),
            category=TodoCategory(data.get("category", "other")),
            due_date=date.fromisoformat(data["due_date"]) if data.get("due_date") else None,
            due_time=data.get("due_time"),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            tags=data.get("tags", []),
            subtasks=data.get("subtasks", []),
            parent_id=data.get("parent_id"),
            estimated_minutes=data.get("estimated_minutes"),
            actual_minutes=data.get("actual_minutes"),
            reminder=datetime.fromisoformat(data["reminder"]) if data.get("reminder") else None,
            notes=data.get("notes", ""),
            progress=data.get("progress", 0)
        )
    
    def is_overdue(self) -> bool:
        if self.due_date and self.status not in [TodoStatus.COMPLETED, TodoStatus.CANCELLED]:
            return date.today() > self.due_date
        return False
    
    def days_until_due(self) -> Optional[int]:
        if self.due_date:
            return (self.due_date - date.today()).days
        return None


class TodoManager:
    """
    待办事项管理器
    
    功能：
    1. 添加/删除/修改待办事项
    2. 按优先级、状态、分类筛选
    3. 子任务管理
    4. 进度跟踪
    5. 到期提醒
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self._todos: Dict[str, TodoItem] = {}
        self._storage_path = storage_path
        
        if storage_path:
            self._load_from_file()
    
    def _generate_id(self) -> str:
        return f"todo_{uuid.uuid4().hex[:8]}"
    
    def add_todo(
        self,
        title: str,
        description: str = "",
        priority: TodoPriority = TodoPriority.MEDIUM,
        category: TodoCategory = TodoCategory.OTHER,
        due_date: Optional[date] = None,
        due_time: Optional[str] = None,
        tags: List[str] = None,
        estimated_minutes: Optional[int] = None,
        parent_id: Optional[str] = None,
        reminder: Optional[datetime] = None
    ) -> TodoItem:
        
        todo_id = self._generate_id()
        
        todo = TodoItem(
            id=todo_id,
            title=title,
            description=description,
            priority=priority,
            category=category,
            due_date=due_date,
            due_time=due_time,
            tags=tags or [],
            estimated_minutes=estimated_minutes,
            parent_id=parent_id,
            reminder=reminder
        )
        
        self._todos[todo_id] = todo
        
        if parent_id and parent_id in self._todos:
            parent = self._todos[parent_id]
            if todo_id not in parent.subtasks:
                parent.subtasks.append(todo_id)
        
        self._save_to_file()
        
        return todo
    
    def get_todo(self, todo_id: str) -> Optional[TodoItem]:
        return self._todos.get(todo_id)
    
    def update_todo(self, todo_id: str, **kwargs) -> Optional[TodoItem]:
        todo = self._todos.get(todo_id)
        if not todo:
            return None
        
        for key, value in kwargs.items():
            if hasattr(todo, key):
                setattr(todo, key, value)
        
        todo.updated_at = datetime.now()
        self._save_to_file()
        
        return todo
    
    def delete_todo(self, todo_id: str, delete_subtasks: bool = True) -> bool:
        if todo_id not in self._todos:
            return False
        
        todo = self._todos[todo_id]
        
        if todo.parent_id and todo.parent_id in self._todos:
            parent = self._todos[todo.parent_id]
            if todo_id in parent.subtasks:
                parent.subtasks.remove(todo_id)
        
        if delete_subtasks:
            for subtask_id in todo.subtasks[:]:
                self.delete_todo(subtask_id, True)
        
        del self._todos[todo_id]
        self._save_to_file()
        
        return True
    
    def complete_todo(self, todo_id: str) -> Optional[TodoItem]:
        todo = self.update_todo(
            todo_id,
            status=TodoStatus.COMPLETED,
            completed_at=datetime.now(),
            progress=100
        )
        
        if todo and todo.parent_id:
            self._update_parent_progress(todo.parent_id)
        
        return todo
    
    def _update_parent_progress(self, parent_id: str):
        parent = self._todos.get(parent_id)
        if not parent or not parent.subtasks:
            return
        
        completed = sum(
            1 for sid in parent.subtasks
            if self._todos.get(sid, TodoItem(id="", title="")).status == TodoStatus.COMPLETED
        )
        
        parent.progress = int(completed / len(parent.subtasks) * 100)
        parent.updated_at = datetime.now()
        
        if parent.progress == 100:
            parent.status = TodoStatus.COMPLETED
            parent.completed_at = datetime.now()
        
        self._save_to_file()
    
    def set_progress(self, todo_id: str, progress: int) -> Optional[TodoItem]:
        progress = max(0, min(100, progress))
        
        updates = {"progress": progress}
        
        if progress == 100:
            updates["status"] = TodoStatus.COMPLETED
            updates["completed_at"] = datetime.now()
        elif progress > 0:
            updates["status"] = TodoStatus.IN_PROGRESS
        
        return self.update_todo(todo_id, **updates)
    
    def get_all_todos(self) -> List[TodoItem]:
        return list(self._todos.values())
    
    def get_pending_todos(self) -> List[TodoItem]:
        return [
            t for t in self._todos.values()
            if t.status == TodoStatus.PENDING
        ]
    
    def get_completed_todos(self) -> List[TodoItem]:
        return [
            t for t in self._todos.values()
            if t.status == TodoStatus.COMPLETED
        ]
    
    def get_overdue_todos(self) -> List[TodoItem]:
        return [
            t for t in self._todos.values()
            if t.is_overdue()
        ]
    
    def get_todos_by_priority(self, priority: TodoPriority) -> List[TodoItem]:
        return [
            t for t in self._todos.values()
            if t.priority == priority
        ]
    
    def get_todos_by_category(self, category: TodoCategory) -> List[TodoItem]:
        return [
            t for t in self._todos.values()
            if t.category == category
        ]
    
    def get_todos_by_due_date(self, target_date: date) -> List[TodoItem]:
        return [
            t for t in self._todos.values()
            if t.due_date == target_date
        ]
    
    def get_todos_due_soon(self, days: int = 3) -> List[TodoItem]:
        today = date.today()
        end_date = today + timedelta(days=days)
        
        return [
            t for t in self._todos.values()
            if t.due_date and today <= t.due_date <= end_date
            and t.status not in [TodoStatus.COMPLETED, TodoStatus.CANCELLED]
        ]
    
    def get_todos_by_tag(self, tag: str) -> List[TodoItem]:
        return [
            t for t in self._todos.values()
            if tag in t.tags
        ]
    
    def get_root_todos(self) -> List[TodoItem]:
        return [
            t for t in self._todos.values()
            if not t.parent_id
        ]
    
    def get_subtasks(self, todo_id: str) -> List[TodoItem]:
        todo = self._todos.get(todo_id)
        if not todo:
            return []
        
        return [
            self._todos[sid]
            for sid in todo.subtasks
            if sid in self._todos
        ]
    
    def get_statistics(self) -> Dict:
        todos = list(self._todos.values())
        
        return {
            "total": len(todos),
            "completed": len([t for t in todos if t.status == TodoStatus.COMPLETED]),
            "pending": len([t for t in todos if t.status == TodoStatus.PENDING]),
            "in_progress": len([t for t in todos if t.status == TodoStatus.IN_PROGRESS]),
            "overdue": len([t for t in todos if t.is_overdue()]),
            "by_priority": {
                p.name: len([t for t in todos if t.priority == p])
                for p in TodoPriority
            },
            "by_category": {
                c.name: len([t for t in todos if t.category == c])
                for c in TodoCategory
            },
            "completion_rate": (
                len([t for t in todos if t.status == TodoStatus.COMPLETED]) / len(todos) * 100
                if todos else 0
            )
        }
    
    def search_todos(self, keyword: str) -> List[TodoItem]:
        keyword = keyword.lower()
        return [
            t for t in self._todos.values()
            if keyword in t.title.lower() or keyword in t.description.lower()
        ]
    
    def sort_todos(self, todos: List[TodoItem], 
                   by: str = "priority", 
                   reverse: bool = True) -> List[TodoItem]:
        sort_keys = {
            "priority": lambda t: t.priority.value,
            "due_date": lambda t: t.due_date or date.max,
            "created": lambda t: t.created_at,
            "title": lambda t: t.title.lower(),
            "progress": lambda t: t.progress
        }
        
        if by in sort_keys:
            return sorted(todos, key=sort_keys[by], reverse=reverse)
        return todos
    
    def get_prioritized_list(self) -> List[TodoItem]:
        pending = self.get_pending_todos()
        
        overdue = [t for t in pending if t.is_overdue()]
        due_soon = [t for t in pending if not t.is_overdue() and t.days_until_due() is not None and t.days_until_due() <= 3]
        high_priority = [t for t in pending if t not in overdue and t not in due_soon and t.priority.value >= 3]
        others = [t for t in pending if t not in overdue and t not in due_soon and t not in high_priority]
        
        overdue = self.sort_todos(overdue, "priority")
        due_soon = self.sort_todos(due_soon, "due_date", reverse=False)
        high_priority = self.sort_todos(high_priority, "priority")
        others = self.sort_todos(others, "priority")
        
        return overdue + due_soon + high_priority + others
    
    def _save_to_file(self):
        if not self._storage_path:
            return
        
        try:
            data = {
                "todos": [t.to_dict() for t in self._todos.values()]
            }
            with open(self._storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Save todos failed: {e}")
    
    def _load_from_file(self):
        if not self._storage_path:
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for todo_data in data.get("todos", []):
                todo = TodoItem.from_dict(todo_data)
                self._todos[todo.id] = todo
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Load todos failed: {e}")
    
    def to_dict(self) -> Dict:
        return {
            "todos": [t.to_dict() for t in self._todos.values()]
        }
