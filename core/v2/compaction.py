"""
XiaoMengCore v2 - 会话压缩系统

参考 OpenClaw 的 compaction 机制：
当会话上下文过长时，自动压缩历史对话为摘要
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import json
import re

from .session import TranscriptEntry, SessionStore


@dataclass
class CompactionResult:
    success: bool
    original_tokens: int
    compressed_tokens: int
    summary: str
    entries_removed: int
    entries_kept: int


@dataclass
class CompactionConfig:
    max_tokens: int = 4000
    target_tokens: int = 2000
    min_entries_to_keep: int = 10
    summary_model: str = "basic"
    keep_recent_messages: int = 5
    keep_tool_results: bool = True
    keep_important_messages: bool = True


class Compactor:
    """
    会话压缩器
    
    当会话上下文超过阈值时，将历史对话压缩为摘要
    """
    
    def __init__(self, llm_client=None, config: CompactionConfig = None):
        self._llm_client = llm_client
        self._config = config or CompactionConfig()
    
    def estimate_tokens(self, text: str) -> int:
        """估算文本 token 数"""
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        return chinese_chars + other_chars // 4
    
    def estimate_entries_tokens(self, entries: List[TranscriptEntry]) -> int:
        """估算条目总 token 数"""
        total = 0
        for entry in entries:
            total += self.estimate_tokens(entry.content)
            if entry.tool_args:
                total += self.estimate_tokens(json.dumps(entry.tool_args))
            if entry.tool_result:
                result_str = str(entry.tool_result)
                if len(result_str) > 500:
                    total += 500
                else:
                    total += self.estimate_tokens(result_str)
        return total
    
    def should_compact(self, entries: List[TranscriptEntry]) -> bool:
        """判断是否需要压缩"""
        total_tokens = self.estimate_entries_tokens(entries)
        return total_tokens > self._config.max_tokens
    
    def select_entries_to_compact(
        self,
        entries: List[TranscriptEntry]
    ) -> tuple[List[TranscriptEntry], List[TranscriptEntry]]:
        """
        选择需要压缩的条目
        
        返回: (需要压缩的条目, 保留的条目)
        """
        if len(entries) <= self._config.min_entries_to_keep:
            return [], entries
        
        recent_entries = entries[-self._config.keep_recent_messages:]
        older_entries = entries[:-self._config.keep_recent_messages]
        
        to_compact = []
        to_keep = list(recent_entries)
        
        for entry in older_entries:
            if self._config.keep_tool_results and entry.tool_name:
                to_keep.insert(0, entry)
            elif self._config.keep_important_messages and entry.metadata.get("important"):
                to_keep.insert(0, entry)
            else:
                to_compact.append(entry)
        
        return to_compact, to_keep
    
    async def generate_summary(
        self,
        entries: List[TranscriptEntry]
    ) -> str:
        """生成对话摘要"""
        if not entries:
            return ""
        
        conversation_text = self._format_entries_for_summary(entries)
        
        if self._llm_client:
            try:
                prompt = f"""请将以下对话历史压缩为简洁的摘要，保留关键信息：

{conversation_text}

摘要要求：
1. 保留重要的事实和决定
2. 保留用户的偏好和需求
3. 保留未完成的任务
4. 使用简洁的语言
5. 不超过 500 字

摘要："""
                
                response = await self._llm_client.chat([
                    {"role": "user", "content": prompt}
                ])
                
                if isinstance(response, dict):
                    return response.get("content", response.get("response", ""))
                return str(response)
            except Exception as e:
                print(f"LLM 摘要生成失败: {e}")
        
        return self._generate_simple_summary(entries)
    
    def _format_entries_for_summary(self, entries: List[TranscriptEntry]) -> str:
        """格式化条目用于摘要"""
        lines = []
        for entry in entries:
            role = "用户" if entry.role == "user" else "助手"
            content = entry.content[:200] + "..." if len(entry.content) > 200 else entry.content
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)
    
    def _generate_simple_summary(self, entries: List[TranscriptEntry]) -> str:
        """生成简单摘要（无 LLM）"""
        user_messages = [e for e in entries if e.role == "user"]
        assistant_messages = [e for e in entries if e.role == "assistant"]
        
        topics = []
        for msg in user_messages[:5]:
            words = msg.content.split()[:10]
            if words:
                topics.append(" ".join(words))
        
        summary = f"对话摘要（{len(user_messages)} 条用户消息，{len(assistant_messages)} 条回复）\n"
        if topics:
            summary += "主要话题：" + "；".join(topics[:3])
        
        return summary
    
    async def compact(
        self,
        entries: List[TranscriptEntry]
    ) -> CompactionResult:
        """
        执行压缩
        
        返回压缩结果
        """
        original_tokens = self.estimate_entries_tokens(entries)
        
        if original_tokens <= self._config.max_tokens:
            return CompactionResult(
                success=False,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                summary="",
                entries_removed=0,
                entries_kept=len(entries)
            )
        
        to_compact, to_keep = self.select_entries_to_compact(entries)
        
        if not to_compact:
            return CompactionResult(
                success=False,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                summary="",
                entries_removed=0,
                entries_kept=len(entries)
            )
        
        summary = await self.generate_summary(to_compact)
        
        summary_entry = TranscriptEntry(
            id=f"summary_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            parent_id=to_compact[-1].id if to_compact else None,
            role="system",
            content=f"[历史对话摘要]\n{summary}",
            metadata={"type": "compaction_summary", "entries_count": len(to_compact)}
        )
        
        final_entries = [summary_entry] + to_keep
        compressed_tokens = self.estimate_entries_tokens(final_entries)
        
        return CompactionResult(
            success=True,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            summary=summary,
            entries_removed=len(to_compact),
            entries_kept=len(to_keep)
        )


class AutoCompactor:
    """
    自动压缩管理器
    
    在会话达到阈值时自动触发压缩
    """
    
    def __init__(
        self,
        session_store: SessionStore,
        compactor: Compactor = None,
        config: CompactionConfig = None
    ):
        self._session_store = session_store
        self._compactor = compactor or Compactor(config=config)
        self._config = config or CompactionConfig()
        self._last_compaction: Dict[str, datetime] = {}
    
    async def check_and_compact(
        self,
        session_key: str,
        force: bool = False
    ) -> Optional[CompactionResult]:
        """
        检查并执行压缩
        
        Args:
            session_key: 会话键
            force: 是否强制压缩
        
        Returns:
            压缩结果，如果不需要压缩则返回 None
        """
        entries = self._session_store.get_transcript(session_key, limit=100)
        
        if not entries:
            return None
        
        if not force and not self._compactor.should_compact(entries):
            return None
        
        result = await self._compactor.compact(entries)
        
        if result.success:
            self._last_compaction[session_key] = datetime.now()
            
            self._session_store.append_transcript(
                session_key=session_key,
                role="system",
                content=f"[自动压缩] 移除了 {result.entries_removed} 条历史消息，"
                        f"Token 从 {result.original_tokens} 减少到 {result.compressed_tokens}"
            )
        
        return result
    
    def get_compaction_status(self, session_key: str) -> Dict[str, Any]:
        """获取压缩状态"""
        entries = self._session_store.get_transcript(session_key, limit=100)
        tokens = self._compactor.estimate_entries_tokens(entries)
        
        return {
            "session_key": session_key,
            "total_entries": len(entries),
            "estimated_tokens": tokens,
            "max_tokens": self._config.max_tokens,
            "needs_compaction": tokens > self._config.max_tokens,
            "last_compaction": self._last_compaction.get(session_key)
        }
