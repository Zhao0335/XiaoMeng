"""
账号管理模块测试
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import json

from plugins.calendar_maker.config import CalendarMakerConfig, CalendarBackendConfig
from plugins.calendar_maker.account_manager import AccountManager


class TestAccountManager:
    """账号管理器测试"""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def config(self):
        return CalendarMakerConfig(
            backend=CalendarBackendConfig(
                backend_url="http://localhost:5522",
                timeout=30.0,
                retry_count=3,
            ),
            default_account=None,
            enabled=True,
        )

    @pytest.fixture
    def account_manager(self, config, temp_dir):
        return AccountManager(config=config, data_dir=temp_dir)

    def test_list_accounts_empty(self, account_manager):
        accounts = account_manager.list_accounts()
        assert accounts == []

    def test_current_account_none(self, account_manager):
        assert account_manager.current_account is None

    def test_is_logged_in_false(self, account_manager):
        assert account_manager.is_logged_in is False

    @pytest.mark.asyncio
    async def test_login_with_calendar_backend_account(self, config, temp_dir):
        """测试直接使用 calendar_backend 的账号登录"""
        manager = AccountManager(config=config, data_dir=temp_dir)
        
        with patch.object(manager._client, 'login', new_callable=AsyncMock) as mock_login:
            mock_login.return_value = (True, "登录成功")
            manager._client._session_id = "test_session"
            manager._client._username = "testuser"
            
            success, msg = await manager.login_account(
                username="testuser",
                password="password123",
            )
            assert success is True
            assert manager.current_account == "testuser"
            mock_login.assert_called_once_with("testuser", "password123")

    @pytest.mark.asyncio
    async def test_login_with_account_name(self, config, temp_dir):
        """测试登录并保存别名"""
        manager = AccountManager(config=config, data_dir=temp_dir)
        
        with patch.object(manager._client, 'login', new_callable=AsyncMock) as mock_login:
            mock_login.return_value = (True, "登录成功")
            manager._client._session_id = "test_session"
            manager._client._username = "realuser"
            
            success, msg = await manager.login_account(
                username="realuser",
                password="password123",
                account_name="my_account",
            )
            assert success is True
            assert manager.current_account == "my_account"
            assert "my_account" in manager._accounts
            assert manager._accounts["my_account"]["username"] == "realuser"

    @pytest.mark.asyncio
    async def test_login_with_saved_alias(self, config, temp_dir):
        """测试使用已保存的别名登录"""
        manager = AccountManager(config=config, data_dir=temp_dir)
        
        manager._accounts["my_account"] = {
            "username": "realuser",
            "created_at": "2024-01-01",
        }
        manager._save_accounts()
        
        with patch.object(manager._client, 'login', new_callable=AsyncMock) as mock_login:
            mock_login.return_value = (True, "登录成功")
            manager._client._session_id = "test_session"
            manager._client._username = "realuser"
            
            success, msg = await manager.login_account(
                username="my_account",
                password="password123",
            )
            assert success is True
            mock_login.assert_called_once_with("realuser", "password123")

    @pytest.mark.asyncio
    async def test_switch_account(self, config, temp_dir):
        """测试切换账号"""
        manager = AccountManager(config=config, data_dir=temp_dir)
        
        with patch.object(manager._client, 'login', new_callable=AsyncMock) as mock_login:
            mock_login.return_value = (True, "登录成功")
            manager._client._session_id = "test_session"
            manager._client._username = "user2"
            
            success, msg = await manager.switch_account(
                username="user2",
                password="password2",
            )
            assert success is True

    @pytest.mark.asyncio
    async def test_register_account(self, config, temp_dir):
        """测试注册新账号"""
        manager = AccountManager(config=config, data_dir=temp_dir)
        
        with patch.object(manager._client, 'register', new_callable=AsyncMock) as mock_reg, \
             patch.object(manager._client, 'login', new_callable=AsyncMock) as mock_login:
            mock_reg.return_value = (True, "注册成功")
            mock_login.return_value = (True, "登录成功")
            manager._client._session_id = "test_session"
            manager._client._username = "newuser"
            
            success, msg = await manager.register_account(
                account_name="my_account",
                username="newuser",
                password="password123",
            )
            assert success is True
            assert "my_account" in manager._accounts
            assert manager._accounts["my_account"]["username"] == "newuser"

    def test_logout(self, config, temp_dir):
        manager = AccountManager(config=config, data_dir=temp_dir)
        manager._current_account = "test_account"
        manager._accounts["test_account"] = {"username": "testuser"}
        
        success, msg = manager.logout()
        assert success is True
        assert manager.current_account is None

    def test_logout_no_account(self, account_manager):
        success, msg = account_manager.logout()
        assert success is False

    def test_delete_account(self, config, temp_dir):
        manager = AccountManager(config=config, data_dir=temp_dir)
        manager._accounts["test_account"] = {"username": "testuser"}
        manager._save_accounts()
        
        success, msg = manager.delete_account("test_account")
        assert success is True
        assert "test_account" not in manager._accounts

    @pytest.mark.asyncio
    async def test_add_event_not_logged_in(self, account_manager):
        success, msg, result = await account_manager.add_event(
            title="测试事件",
            date="2024-01-15",
            time="14:00"
        )
        assert success is False
        assert "未登录" in msg

    @pytest.mark.asyncio
    async def test_add_todo_not_logged_in(self, account_manager):
        success, msg, result = await account_manager.add_todo(
            title="测试待办",
            deadline="2024-01-20"
        )
        assert success is False
        assert "未登录" in msg

    @pytest.mark.asyncio
    async def test_get_events_not_logged_in(self, account_manager):
        events = await account_manager.get_events()
        assert events == []

    @pytest.mark.asyncio
    async def test_get_todos_not_logged_in(self, account_manager):
        todos = await account_manager.get_todos()
        assert todos == []

    @pytest.mark.asyncio
    async def test_health_check(self, account_manager):
        with patch.object(account_manager._client, 'health_check', new_callable=AsyncMock) as mock:
            mock.return_value = True
            result = await account_manager.health_check()
            assert result is True
