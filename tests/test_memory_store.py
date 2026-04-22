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

    def test_last_accessed_at_updated_on_get(self):
        m = Memory(content="test access", type="user")
        self.store.add(m)
        before_get = time.time()

        # slight delay to ensure time diff
        time.sleep(0.01)

        retrieved = self.store.get(m.id)
        self.assertIsNotNone(retrieved.last_accessed_at)
        self.assertGreaterEqual(retrieved.last_accessed_at, before_get)

    def test_last_accessed_at_increases_on_multiple_gets(self):
        m = Memory(content="test access multiple", type="user")
        self.store.add(m)

        retrieved1 = self.store.get(m.id)
        time.sleep(0.01)
        retrieved2 = self.store.get(m.id)

        self.assertIsNotNone(retrieved1.last_accessed_at)
        self.assertIsNotNone(retrieved2.last_accessed_at)
        self.assertGreaterEqual(retrieved2.last_accessed_at, retrieved1.last_accessed_at)

    def test_list_by_type(self):
        mem1 = Memory(id="1", content="a", type="user", source="test", session_id="s1")
        mem2 = Memory(id="2", content="b", type="user", source="test", session_id="s1")
        mem3 = Memory(id="3", content="c", type="feedback", source="test", session_id="s1")
        self.store.add(mem1)
        self.store.add(mem2)
        self.store.add(mem3)
        self.store.archive("2")
        res = self.store.list_by_type("user")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, "1")

    def test_list_by_type_order_by_valid(self):
        mem1 = Memory(id="1", content="a", type="user", weight=1.0)
        mem2 = Memory(id="2", content="b", type="user", weight=2.0)
        self.store.add(mem1)
        self.store.add(mem2)

        res = self.store.list_by_type("user", order_by="weight DESC, id ASC")
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].id, "2")
        self.assertEqual(res[1].id, "1")

    def test_list_by_type_order_by_invalid(self):
        mem1 = Memory(id="1", content="a", type="user")
        self.store.add(mem1)

        invalid_orders = [
            "weight DROP TABLE memories",
            "invalid_column ASC",
            "id ASC DESC",
            "weight; DELETE FROM memories"
        ]

        for invalid_order in invalid_orders:
            with self.assertRaises(ValueError):
                self.store.list_by_type("user", order_by=invalid_order)

    def test_list_unprocessed(self):
        mem1 = Memory(id="1", content="a", type="user", source="test", session_id="s1")
        mem2 = Memory(id="2", content="b", type="user", source="test", session_id="s2")
        mem3 = Memory(id="3", content="c", type="user", source="test", session_id="s1")
        self.store.add(mem1)
        self.store.add(mem2)
        self.store.add(mem3)
        self.store.mark_processed(["3"])
        res = self.store.list_unprocessed(exclude_session_id="s1")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, "2")
        res_all = self.store.list_unprocessed()
        self.assertEqual(len(res_all), 2)

if __name__ == '__main__':
    unittest.main()
