import unittest
import time
from aic.memory.types import Memory
from aic.memory.store import MemoryStore

class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(":memory:")

    def test_add_and_get(self):
        mem = Memory(content="Test content", type="user")
        self.store.add(mem)

        retrieved = self.store.get(mem.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, mem.id)
        self.assertEqual(retrieved.content, "Test content")
        self.assertEqual(retrieved.type, "user")
        self.assertEqual(retrieved.is_archived, 0)
        self.assertEqual(retrieved.is_processed, 0)

    def test_get_nonexistent(self):
        self.assertIsNone(self.store.get("nonexistent"))

    def test_soft_delete(self):
        mem1 = Memory(content="Old info", type="project")
        self.store.add(mem1)
        mem2 = Memory(content="New info", type="project")
        self.store.add(mem2)

        self.store.soft_delete(mem1.id, superseded_by=mem2.id)

        retrieved = self.store.get(mem1.id)
        self.assertEqual(retrieved.is_archived, 1)
        self.assertEqual(retrieved.superseded_by, mem2.id)

    def test_soft_delete_superseded_by_nonexistent(self):
        mem = Memory(content="Info", type="project")
        self.store.add(mem)

        with self.assertRaises(ValueError):
            self.store.soft_delete(mem.id, superseded_by="missing_id")

    def test_soft_delete_self_reference(self):
        mem = Memory(content="Info", type="project")
        self.store.add(mem)

        with self.assertRaises(ValueError):
            self.store.soft_delete(mem.id, superseded_by=mem.id)

    def test_count_unprocessed(self):
        # 1: unprocessed, unarchived
        m1 = Memory(content="m1", type="user")
        self.store.add(m1)

        # 2: processed, unarchived
        m2 = Memory(content="m2", type="user", is_processed=1)
        self.store.add(m2)

        # 3: unprocessed, archived
        m3 = Memory(content="m3", type="user", is_archived=1)
        self.store.add(m3)

        self.assertEqual(self.store.count_unprocessed(), 1)

    def test_mark_processed(self):
        m1 = Memory(content="m1", type="user")
        self.store.add(m1)
        m2 = Memory(content="m2", type="user")
        self.store.add(m2)

        self.assertEqual(self.store.count_unprocessed(), 2)

        self.store.mark_processed([m1.id])
        self.assertEqual(self.store.count_unprocessed(), 1)

        retrieved1 = self.store.get(m1.id)
        self.assertEqual(retrieved1.is_processed, 1)

    def test_prefix_match(self):
        m1 = Memory(content="m1", type="user", id="abcd1234efgh")
        self.store.add(m1)
        m2 = Memory(content="m2", type="user", id="abxy9876zxcv")
        self.store.add(m2)
        m3 = Memory(content="m3", type="user", id="bbcd1234efgh")
        self.store.add(m3)

        matches_ab = self.store.prefix_match("ab")
        self.assertEqual(len(matches_ab), 2)
        match_ids = [m.id for m in matches_ab]
        self.assertIn("abcd1234efgh", match_ids)
        self.assertIn("abxy9876zxcv", match_ids)

        matches_abcd = self.store.prefix_match("abcd")
        self.assertEqual(len(matches_abcd), 1)
        self.assertEqual(matches_abcd[0].id, "abcd1234efgh")

    def test_list(self):
        m1 = Memory(content="user mem", type="user")
        self.store.add(m1)
        m2 = Memory(content="project mem", type="project")
        self.store.add(m2)
        m3 = Memory(content="archived user mem", type="user", is_archived=1)
        self.store.add(m3)

        # list all unarchived
        all_unarchived = self.store.list()
        self.assertEqual(len(all_unarchived), 2)

        # list all including archived
        all_included = self.store.list(include_archived=True)
        self.assertEqual(len(all_included), 3)

        # list specific type
        user_mems = self.store.list(type="user")
        self.assertEqual(len(user_mems), 1)
        self.assertEqual(user_mems[0].id, m1.id)

        user_mems_all = self.store.list(type="user", include_archived=True)
        self.assertEqual(len(user_mems_all), 2)

    def test_update_weight(self):
        m = Memory(content="test", type="user", weight=1.0)
        self.store.add(m)
        self.store.update_weight(m.id, 0.5)
        retrieved = self.store.get(m.id)
        self.assertEqual(retrieved.weight, 1.5)

if __name__ == '__main__':
    unittest.main()
