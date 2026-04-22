import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aic.dream.lock import DreamLock


class TestDreamLock(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.lock_path = Path(self.test_dir) / ".dream-lock"
        self.session_id = "test_session_123"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_get_state_file_not_exists(self):
        """测试文件不存在时 get_state 返回空字典。"""
        lock = DreamLock(self.lock_path)
        self.assertEqual(lock.get_state(), {})

    def test_get_state_valid_json(self):
        """测试存在有效JSON时 get_state 返回解析后的字典。"""
        lock = DreamLock(self.lock_path)
        valid_data = {"key": "value", "number": 42}
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(json.dumps(valid_data), encoding="utf-8")
        self.assertEqual(lock.get_state(), valid_data)

    def test_get_state_invalid_json(self):
        """测试JSON格式错误时 get_state 捕获异常并返回空字典。"""
        lock = DreamLock(self.lock_path)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text("invalid json content", encoding="utf-8")
        self.assertEqual(lock.get_state(), {})

    def test_acquire_new_lock(self):
        """测试锁不存在时，acquire() 应该成功创建锁并返回 True。"""
        lock = DreamLock(self.lock_path)
        self.assertTrue(lock.acquire(self.session_id))
        self.assertTrue(self.lock_path.exists())

        state = lock.get_state()
        self.assertEqual(state["session_id"], self.session_id)
        self.assertEqual(state["phase"], 0)
        self.assertEqual(state["pid"], os.getpid())
        self.assertIn("started_at", state)
        self.assertEqual(state["orient_data"], {})

    def test_acquire_existing_lock_active(self):
        """测试锁存在且进程活跃时，acquire() 应该返回 False。"""
        lock = DreamLock(self.lock_path)
        self.assertTrue(lock.acquire(self.session_id))

        # Another process tries to acquire
        with patch('os.kill') as mock_kill:
            # Simulate os.kill doing nothing (process is alive)
            mock_kill.return_value = None

            # Change PID in lock file to simulate another process
            state = lock.get_state()
            state["pid"] = 99999
            self.lock_path.write_text(json.dumps(state), encoding="utf-8")

            # Wait a tiny bit to ensure it's not stale
            # Not needed since it's fresh

            lock2 = DreamLock(self.lock_path)
            self.assertFalse(lock2.acquire("another_session"))

            mock_kill.assert_called_once_with(99999, 0)

    def test_acquire_existing_lock_dead_process(self):
        """测试锁存在但进程不存在时，acquire() 应该接管锁并返回 True。"""
        lock = DreamLock(self.lock_path)
        self.assertTrue(lock.acquire(self.session_id))

        with patch('os.kill') as mock_kill:
            # Simulate process not found
            mock_kill.side_effect = ProcessLookupError()

            state = lock.get_state()
            state["pid"] = 99999
            self.lock_path.write_text(json.dumps(state), encoding="utf-8")

            lock2 = DreamLock(self.lock_path)
            self.assertTrue(lock2.acquire("new_session"))

            new_state = lock2.get_state()
            self.assertEqual(new_state["session_id"], "new_session")
            self.assertEqual(new_state["pid"], os.getpid())

    def test_acquire_existing_lock_permission_error_not_stale(self):
        """测试遇到PermissionError但未超时的情况，acquire()应该返回False。"""
        lock = DreamLock(self.lock_path)
        self.assertTrue(lock.acquire(self.session_id))

        with patch('os.kill') as mock_kill:
            # Simulate process exists but no permission
            mock_kill.side_effect = PermissionError()

            state = lock.get_state()
            state["pid"] = 99999
            self.lock_path.write_text(json.dumps(state), encoding="utf-8")

            lock2 = DreamLock(self.lock_path)
            self.assertFalse(lock2.acquire("new_session"))

    def test_acquire_existing_lock_permission_error_stale(self):
        """测试遇到PermissionError且超时的情况，acquire()应该返回True。"""
        lock = DreamLock(self.lock_path)
        self.assertTrue(lock.acquire(self.session_id))

        with patch('os.kill') as mock_kill:
            # Simulate process exists but no permission
            mock_kill.side_effect = PermissionError()

            state = lock.get_state()
            state["pid"] = 99999
            # Make it stale
            state["started_at"] = time.time() - (lock.lock_timeout_h * 3600) - 10
            self.lock_path.write_text(json.dumps(state), encoding="utf-8")

            lock2 = DreamLock(self.lock_path)
            self.assertTrue(lock2.acquire("new_session"))

    def test_acquire_corrupted_lock(self):
        """测试锁文件损坏时，acquire() 应该覆盖并返回 True。"""
        self.lock_path.write_text("not a valid json", encoding="utf-8")

        lock = DreamLock(self.lock_path)
        self.assertTrue(lock.acquire(self.session_id))

        state = lock.get_state()
        self.assertEqual(state["session_id"], self.session_id)

    def test_is_stale(self):
        """测试 is_stale() 基于 started_at 判断。"""
        lock = DreamLock(self.lock_path, lock_timeout_h=1.0)

        # No lock file -> not stale
        self.assertFalse(lock.is_stale())

        self.assertTrue(lock.acquire(self.session_id))

        # Fresh lock -> not stale
        self.assertFalse(lock.is_stale())

        # Modify started_at to make it stale
        state = lock.get_state()
        state["started_at"] = time.time() - 3600 - 10  # > 1 hour ago
        self.lock_path.write_text(json.dumps(state), encoding="utf-8")

        self.assertTrue(lock.is_stale())

    def test_update_state(self):
        """测试 update_state 更新 phase 和 orient_data。"""
        lock = DreamLock(self.lock_path)

        with self.assertRaises(RuntimeError):
            lock.update_state(1)

        self.assertTrue(lock.acquire(self.session_id))
        state = lock.get_state()
        self.assertEqual(state["phase"], 0)
        self.assertEqual(state["orient_data"], {})
        original_started_at = state["started_at"]

        # Test update phase only
        lock.update_state(5)

        new_state = lock.get_state()
        self.assertEqual(new_state["phase"], 5)
        self.assertEqual(new_state["orient_data"], {}) # Should remain unmodified
        self.assertEqual(new_state["session_id"], self.session_id)
        self.assertEqual(new_state["started_at"], original_started_at)

        # Test update phase and orient_data
        orient_data = {"key": "value"}
        lock.update_state(6, orient_data)

        final_state = lock.get_state()
        self.assertEqual(final_state["phase"], 6)
        self.assertEqual(final_state["orient_data"], orient_data)
        self.assertEqual(final_state["session_id"], self.session_id)
        self.assertEqual(final_state["started_at"], original_started_at)

    def test_release(self):
        """测试 release() 删除锁文件，忽略无文件错误。"""
        lock = DreamLock(self.lock_path)

        # Releasing non-existent lock shouldn't raise error
        lock.release()

        self.assertTrue(lock.acquire(self.session_id))
        self.assertTrue(self.lock_path.exists())

        lock.release()
        self.assertFalse(self.lock_path.exists())

if __name__ == '__main__':
    unittest.main()
