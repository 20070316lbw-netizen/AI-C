import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
from aic.session import Session

class TestSession(unittest.TestCase):
    def setUp(self):
        self.config = {"provider": "deepseek"}
        # Create a temporary directory to avoid reading real .aic/CONTEXT.md
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def test_session_init(self):
        session = Session(self.config)
        self.assertTrue(isinstance(session.session_id(), str))
        self.assertEqual(len(session.session_id()), 36) # UUID length
        self.assertEqual(session.get_messages(), [])
        self.assertEqual(session.list_context_files(), [])

    @patch("aic.session.Path.expanduser")
    def test_auto_load_contexts(self, mock_expanduser):
        # Setup mock global context
        global_ctx_path = Path(self.temp_dir.name) / "GLOBAL_CONTEXT.md"
        global_ctx_path.write_text("global context content")
        mock_expanduser.return_value = global_ctx_path

        # Setup real project context
        os.makedirs(".aic", exist_ok=True)
        project_ctx_path = Path(".aic/CONTEXT.md")
        project_ctx_path.write_text("project context content")

        session = Session(self.config)
        messages = session.get_messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("global context content", messages[0]["content"])
        self.assertIn("project context content", messages[0]["content"])
        self.assertIn("\n\n---\n\n", messages[0]["content"])

    def test_add_messages(self):
        session = Session(self.config)
        session.add_user("hello")
        session.add_assistant("world")

        messages = session.get_messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], {"role": "user", "content": "hello"})
        self.assertEqual(messages[1], {"role": "assistant", "content": "world"})

    def test_add_context_file(self):
        session = Session(self.config)

        test_file = Path("test_file.py")
        test_file.write_text("print('hello')")

        session.add_context_file("test_file.py")

        files = session.list_context_files()
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith("test_file.py"))

        # Adding same file again should not duplicate
        session.add_context_file("test_file.py")
        self.assertEqual(len(session.list_context_files()), 1)

        messages = session.get_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("--- File:", messages[0]["content"])
        self.assertIn("test_file.py", messages[0]["content"])
        self.assertIn("print('hello')", messages[0]["content"])

    def test_clear_and_reset(self):
        session = Session(self.config)
        session.add_user("hello")

        test_file = Path("test_file.py")
        test_file.write_text("print('hello')")
        session.add_context_file("test_file.py")

        self.assertEqual(len(session.get_messages()), 2) # system + user

        session.clear()
        self.assertEqual(len(session.get_messages()), 1) # system only, user cleared
        self.assertEqual(len(session.list_context_files()), 1)

        session.add_user("world")
        session.reset()
        self.assertEqual(len(session.get_messages()), 0) # all cleared
        self.assertEqual(len(session.list_context_files()), 0)

if __name__ == '__main__':
    unittest.main()
