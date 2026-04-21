import unittest
import os
import tempfile
import time
from unittest.mock import patch
from datetime import datetime

import aic.kairos as kairos

class TestKairos(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

        # We need to mock os.path.expanduser to point to our temp dir
        self.mock_expanduser = patch('os.path.expanduser', side_effect=lambda path: path.replace("~", self.temp_dir.name)).start()

    def tearDown(self):
        self.mock_expanduser.stop()
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def test_log_event_and_read_today(self):
        # File should not exist initially
        logs = kairos.read_today()
        self.assertEqual(logs, [])

        # Log an event
        kairos.log_event("test_event", "session_123", {"key": "value"})

        # Read the event back
        logs = kairos.read_today()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["event"], "test_event")
        self.assertEqual(logs[0]["session_id"], "session_123")
        self.assertEqual(logs[0]["payload"], {"key": "value"})

        # Verify ts is present and time is not
        self.assertIn("ts", logs[0])
        self.assertNotIn("time", logs[0])

        # Verify ts is a float and roughly equal to current time
        self.assertIsInstance(logs[0]["ts"], float)
        self.assertTrue(logs[0]["ts"] > time.time() - 5)

    def test_multiple_events(self):
        # Log multiple events
        kairos.log_event("event_1", "session_123", {"num": 1})
        kairos.log_event("event_2", "session_123", {"num": 2})
        kairos.log_event("event_3", "session_123", {"num": 3})

        # Read events
        logs = kairos.read_today()
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0]["event"], "event_1")
        self.assertEqual(logs[1]["event"], "event_2")
        self.assertEqual(logs[2]["event"], "event_3")

    def test_read_today_file_not_found(self):
        # Read without writing any logs
        logs = kairos.read_today()
        self.assertEqual(logs, [])

if __name__ == '__main__':
    unittest.main()
