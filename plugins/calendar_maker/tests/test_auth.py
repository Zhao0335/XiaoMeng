"""
身份验证模块测试
"""

import pytest
from datetime import datetime, timedelta, UTC

from plugins.calendar_maker.auth import (
    PasswordService,
    LoginAttemptManager,
    SessionManager,
    CalendarAuth,
)


class TestPasswordService:
    """密码服务测试"""

    def test_hash_password_sha256(self):
        password = "test_password_123"
        hashed = PasswordService.hash_password(password, algorithm="sha256")
        assert hashed.startswith("sha256$")
        assert "$" in hashed

    def test_verify_password_sha256_correct(self):
        password = "test_password_123"
        hashed = PasswordService.hash_password(password, algorithm="sha256")
        assert PasswordService.verify(password, hashed) is True

    def test_verify_password_sha256_wrong(self):
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = PasswordService.hash_password(password, algorithm="sha256")
        assert PasswordService.verify(wrong_password, hashed) is False

    def test_verify_password_empty_hash(self):
        assert PasswordService.verify("any_password", "") is False

    def test_verify_password_invalid_format(self):
        assert PasswordService.verify("any_password", "invalid$format") is False


class TestLoginAttemptManager:
    """登录尝试管理测试"""

    def test_record_successful_attempt(self):
        manager = LoginAttemptManager(max_attempts=5, lockout_minutes=30)
        manager.record_attempt("user1", success=True)
        assert manager.is_locked_out("user1") is False
        assert manager.get_remaining_attempts("user1") == 5

    def test_record_failed_attempts(self):
        manager = LoginAttemptManager(max_attempts=3, lockout_minutes=30)
        manager.record_attempt("user1", success=False)
        assert manager.get_remaining_attempts("user1") == 2
        manager.record_attempt("user1", success=False)
        assert manager.get_remaining_attempts("user1") == 1
        manager.record_attempt("user1", success=False)
        assert manager.is_locked_out("user1") is True

    def test_lockout_expires(self):
        manager = LoginAttemptManager(max_attempts=1, lockout_minutes=0)
        manager.record_attempt("user1", success=False)
        assert manager.is_locked_out("user1") is True

    def test_success_clears_attempts(self):
        manager = LoginAttemptManager(max_attempts=5, lockout_minutes=30)
        manager.record_attempt("user1", success=False)
        manager.record_attempt("user1", success=False)
        manager.record_attempt("user1", success=True)
        assert manager.get_remaining_attempts("user1") == 5
        assert manager.is_locked_out("user1") is False


class TestSessionManager:
    """会话管理测试"""

    def test_create_session(self):
        manager = SessionManager(ttl_days=30)
        session_id = manager.create_session("user_123", "testuser")
        assert session_id is not None
        assert len(session_id) > 20

    def test_validate_session(self):
        manager = SessionManager(ttl_days=30)
        session_id = manager.create_session("user_123", "testuser")
        session = manager.validate_session(session_id)
        assert session is not None
        assert session["user_id"] == "user_123"
        assert session["username"] == "testuser"

    def test_validate_invalid_session(self):
        manager = SessionManager(ttl_days=30)
        session = manager.validate_session("invalid_session_id")
        assert session is None

    def test_revoke_session(self):
        manager = SessionManager(ttl_days=30)
        session_id = manager.create_session("user_123", "testuser")
        assert manager.revoke_session(session_id) is True
        assert manager.validate_session(session_id) is None

    def test_extend_session(self):
        manager = SessionManager(ttl_days=30)
        session_id = manager.create_session("user_123", "testuser")
        session1 = manager.validate_session(session_id)
        assert manager.extend_session(session_id) is True
        session2 = manager.validate_session(session_id)
        assert session2["expires_at"] > session1["expires_at"]


class TestCalendarAuth:
    """日历认证管理器测试"""

    def test_register_user(self):
        auth = CalendarAuth()
        result = auth.register_user("testuser", "password123", "user_123")
        assert result is True

    def test_register_duplicate_user(self):
        auth = CalendarAuth()
        auth.register_user("testuser", "password123", "user_123")
        result = auth.register_user("testuser", "password456", "user_456")
        assert result is False

    def test_login_success(self):
        auth = CalendarAuth()
        auth.register_user("testuser", "password123", "user_123")
        session_id, user_id, msg = auth.login("testuser", "password123")
        assert session_id is not None
        assert user_id == "user_123"
        assert "成功" in msg

    def test_login_wrong_password(self):
        auth = CalendarAuth()
        auth.register_user("testuser", "password123", "user_123")
        session_id, user_id, msg = auth.login("testuser", "wrongpassword")
        assert session_id is None
        assert user_id is None
        assert "错误" in msg

    def test_login_nonexistent_user(self):
        auth = CalendarAuth()
        session_id, user_id, msg = auth.login("nonexistent", "password")
        assert session_id is None
        assert "错误" in msg

    def test_logout(self):
        auth = CalendarAuth()
        auth.register_user("testuser", "password123", "user_123")
        session_id, _, _ = auth.login("testuser", "password123")
        assert auth.logout(session_id) is True
        assert auth.validate_session(session_id) is None

    def test_change_password(self):
        auth = CalendarAuth()
        auth.register_user("testuser", "oldpassword", "user_123")
        success, msg = auth.change_password("testuser", "oldpassword", "newpassword")
        assert success is True
        session_id, _, _ = auth.login("testuser", "newpassword")
        assert session_id is not None

    def test_change_password_wrong_old(self):
        auth = CalendarAuth()
        auth.register_user("testuser", "oldpassword", "user_123")
        success, msg = auth.change_password("testuser", "wrongpassword", "newpassword")
        assert success is False
