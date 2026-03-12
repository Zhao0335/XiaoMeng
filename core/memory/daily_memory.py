"""
每日记忆管理器 - 完全兼容 OpenClaw memory/YYYY-MM-DD.md 格式

OpenClaw 每日记忆机制：
- 文件命名：memory/YYYY-MM-DD.md
- 追加模式：每次对话的重要信息追加到当天文件
- 混合检索：向量搜索 + BM25 关键词搜索
- 记忆刷新：上下文达到阈值时自动提取关键信息写入

参考：
- OpenClaw memory.ts
- OpenClaw memory-search.ts
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from pathlib import Path
import re
import json


@dataclass
class DailyMemoryEntry:
    """每日记忆条目"""
    timestamp: datetime
    content: str
    tags: List[str] = field(default_factory=list)
    importance: int = 1  # 1-5, 5 最重要
    
    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        time_str = self.timestamp.strftime("%H:%M")
        if self.tags:
            tags_str = " ".join([f"#{t}" for t in self.tags])
            return f"- [{time_str}] {self.content} {tags_str}"
        return f"- [{time_str}] {self.content}"
    
    @classmethod
    def from_markdown(cls, line: str, date_str: str) -> Optional["DailyMemoryEntry"]:
        """从 Markdown 行解析"""
        pattern = r"- \[(\d{2}:\d{2})\] (.+?)(?:\s+(#[\w#\s]+))?$"
        match = re.match(pattern, line.strip())
        if not match:
            return None
        
        time_str, content, tags_str = match.groups()
        timestamp = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        
        tags = []
        if tags_str:
            tags = re.findall(r"#(\w+)", tags_str)
        
        return cls(
            timestamp=timestamp,
            content=content,
            tags=tags
        )


class DailyMemoryManager:
    """
    每日记忆管理器
    
    完全兼容 OpenClaw 的 memory/YYYY-MM-DD.md 格式
    
    功能：
    1. 自动创建当日记忆文件
    2. 追加模式写入记忆
    3. 读取指定日期的记忆
    4. 搜索历史记忆
    """
    
    def __init__(self, memory_dir: str):
        self._memory_dir = Path(memory_dir)
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        
        self._current_date = date.today()
        self._current_file = self._get_file_path(self._current_date)
    
    def _get_file_path(self, target_date: date) -> Path:
        """获取指定日期的文件路径"""
        return self._memory_dir / f"{target_date.strftime('%Y-%m-%d')}.md"
    
    def _ensure_file_exists(self, file_path: Path, target_date: date):
        """确保文件存在，不存在则创建"""
        if not file_path.exists():
            header = f"# 每日记忆 - {target_date.strftime('%Y年%m月%d日')}\n\n"
            file_path.write_text(header, encoding='utf-8')
    
    def add_entry(
        self, 
        content: str, 
        tags: List[str] = None,
        importance: int = 1
    ) -> DailyMemoryEntry:
        """
        添加记忆条目
        
        Args:
            content: 记忆内容
            tags: 标签列表
            importance: 重要性 1-5
        
        Returns:
            创建的记忆条目
        """
        today = date.today()
        if today != self._current_date:
            self._current_date = today
            self._current_file = self._get_file_path(today)
        
        self._ensure_file_exists(self._current_file, today)
        
        entry = DailyMemoryEntry(
            timestamp=datetime.now(),
            content=content,
            tags=tags or [],
            importance=importance
        )
        
        with open(self._current_file, 'a', encoding='utf-8') as f:
            f.write(entry.to_markdown() + "\n")
        
        return entry
    
    def get_today_memories(self) -> List[DailyMemoryEntry]:
        """获取今日所有记忆"""
        return self.get_date_memories(date.today())
    
    def get_date_memories(self, target_date: date) -> List[DailyMemoryEntry]:
        """获取指定日期的所有记忆"""
        file_path = self._get_file_path(target_date)
        if not file_path.exists():
            return []
        
        entries = []
        date_str = target_date.strftime("%Y-%m-%d")
        
        content = file_path.read_text(encoding='utf-8')
        for line in content.split('\n'):
            if line.strip().startswith('- ['):
                entry = DailyMemoryEntry.from_markdown(line, date_str)
                if entry:
                    entries.append(entry)
        
        return entries
    
    def get_recent_memories(self, days: int = 7) -> List[DailyMemoryEntry]:
        """获取最近 N 天的记忆"""
        all_entries = []
        today = date.today()
        
        for i in range(days):
            target_date = date.fromordinal(today.toordinal() - i)
            entries = self.get_date_memories(target_date)
            all_entries.extend(entries)
        
        return all_entries
    
    def search_memories(
        self, 
        query: str, 
        days: int = 30,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索记忆（简单关键词匹配）
        
        注：完整的混合检索在 HybridMemorySearch 中实现
        """
        results = []
        query_lower = query.lower()
        today = date.today()
        
        for i in range(days):
            target_date = date.fromordinal(today.toordinal() - i)
            entries = self.get_date_memories(target_date)
            
            for entry in entries:
                if query_lower in entry.content.lower():
                    results.append({
                        "content": entry.content,
                        "timestamp": entry.timestamp.isoformat(),
                        "date": target_date.strftime("%Y-%m-%d"),
                        "tags": entry.tags,
                        "importance": entry.importance,
                        "source": "daily_memory"
                    })
        
        results.sort(key=lambda x: x["importance"], reverse=True)
        return results[:limit]
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        md_files = list(self._memory_dir.glob("*.md"))
        
        total_entries = 0
        for md_file in md_files:
            content = md_file.read_text(encoding='utf-8')
            total_entries += len([l for l in content.split('\n') if l.strip().startswith('- [')])
        
        return {
            "total_days": len(md_files),
            "total_entries": total_entries,
            "memory_dir": str(self._memory_dir),
            "latest_file": md_files[-1].name if md_files else None
        }
    
    def flush_context_to_memory(
        self, 
        context_summary: str,
        key_points: List[str] = None
    ):
        """
        将上下文摘要刷新到记忆
        
        参考 OpenClaw 的 memory flush 机制：
        当上下文接近限制时，自动提取关键信息写入每日记忆
        """
        if key_points:
            for point in key_points:
                self.add_entry(point, tags=["flush", "auto"])
        elif context_summary:
            self.add_entry(context_summary, tags=["flush", "summary"])
