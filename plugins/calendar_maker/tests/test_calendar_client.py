"""
日历客户端测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from plugins.calendar_maker.calendar_client import (
    CalendarClient,
    Event,
    Todo,
    CalendarClientError,
    AuthenticationError,
    ConnectionError,
)


class TestEvent:
    """Event 数据类测试"""

    def test_event_creation(self):
        event = Event(
            title="项目会议",
            date="2024-01-15",
            time="14:00",
            location="会议室A",
            notes="带笔记本"
        )
        assert event.title == "项目会议"
        assert event.date == "2024-01-15"
        assert event.time == "14:00"

    def test_event_to_dict(self):
        event = Event(
            title="项目会议",
            date="2024-01-15",
            time="14:00"
        )
        result = event.to_dict()
        assert result["title"] == "项目会议"
        assert result["date"] == "2024-01-15"
        assert result["time"] == "14:00"

    def test_event_to_dict_minimal(self):
        event = Event(title="简单事件")
        result = event.to_dict()
        assert result == {"title": "简单事件"}


class TestTodo:
    """Todo 数据类测试"""

    def test_todo_creation(self):
        todo = Todo(
            title="完成报告",
            deadline="2024-01-20",
            priority="high",
            notes="重要"
        )
        assert todo.title == "完成报告"
        assert todo.priority == "high"

    def test_todo_to_dict(self):
        todo = Todo(
            title="完成报告",
            deadline="2024-01-20",
            priority="high"
        )
        result = todo.to_dict()
        assert result["title"] == "完成报告"
        assert result["priority"] == "high"
        assert result["deadline"] == "2024-01-20"

    def test_todo_default_priority(self):
        todo = Todo(title="简单待办")
        assert todo.priority == "medium"


class TestCalendarClient:
    """日历客户端测试"""

    def test_client_creation(self):
        client = CalendarClient(
            base_url="http://localhost:5522",
            timeout=30.0,
            retry_count=3
        )
        assert client.is_authenticated is False
        assert client.current_user is None

    def test_set_session(self):
        client = CalendarClient()
        client.set_session("session_123", "testuser")
        assert client.is_authenticated is True
        assert client.current_user == "testuser"
        assert client.session_id == "session_123"

    def test_logout(self):
        client = CalendarClient()
        client.set_session("session_123", "testuser")
        client.logout()
        assert client.is_authenticated is False
        assert client.current_user is None
        assert client.session_id is None

    def test_format_event_text(self):
        event = Event(
            title="会议",
            date="2024-01-15",
            time="14:00",
            location="会议室A",
            notes="重要"
        )
        text = CalendarClient._format_event_text(event)
        assert "会议" in text
        assert "2024-01-15" in text
        assert "14:00" in text
        assert "会议室A" in text

    def test_format_todo_text(self):
        todo = Todo(
            title="报告",
            deadline="2024-01-20",
            priority="high"
        )
        text = CalendarClient._format_todo_text(todo)
        assert "报告" in text
        assert "2024-01-20" in text
        assert "high" in text


class TestCalendarClientAsync:
    """日历客户端异步测试"""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        client = CalendarClient(base_url="http://localhost:5522")
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "ok", "model": "test", "ollama": True}
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        client = CalendarClient(base_url="http://localhost:5522")
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("Connection failed")
            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_login_success(self):
        client = CalendarClient(base_url="http://localhost:5522")
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "session_id": "session_123",
                "username": "testuser",
                "expires_at": "2024-02-01T00:00:00"
            }
            success, msg = await client.login("testuser", "password")
            assert success is True
            assert client.is_authenticated is True

    @pytest.mark.asyncio
    async def test_add_event_not_authenticated(self):
        client = CalendarClient()
        event = Event(title="测试事件")
        
        with pytest.raises(AuthenticationError):
            await client.add_event(event)

    @pytest.mark.asyncio
    async def test_add_todo_not_authenticated(self):
        client = CalendarClient()
        todo = Todo(title="测试待办")
        
        with pytest.raises(AuthenticationError):
            await client.add_todo(todo)
