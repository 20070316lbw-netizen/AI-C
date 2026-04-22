import sqlite3
import threading
import os
import time
from dataclasses import asdict
from typing import Optional, List

from aic.memory.types import Memory, MemoryType

class MemoryStore:
    def __init__(self, db_path: str = "~/.aic/memory.db"):
        if db_path == ":memory:":
            self.db_path = db_path
        else:
            self.db_path = os.path.expanduser(db_path)
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    source TEXT,
                    session_id TEXT,
                    is_archived INTEGER DEFAULT 0,
                    is_processed INTEGER DEFAULT 0,
                    superseded_by TEXT,
                    meta TEXT,
                    version INTEGER DEFAULT 1,
                    last_accessed_at REAL
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_unprocessed
                ON memories(is_processed, is_archived)
            ''')
            self.conn.commit()

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        d = dict(row)
        return Memory(**d)

    def add(self, memory: Memory) -> str:
        with self.lock:
            cursor = self.conn.cursor()
            d = asdict(memory)
            columns = ', '.join(d.keys())
            placeholders = ', '.join(['?'] * len(d))
            values = tuple(d.values())

            cursor.execute(f'''
                INSERT INTO memories ({columns})
                VALUES ({placeholders})
            ''', values)
            self.conn.commit()
            return memory.id

    def get(self, id: str) -> Optional[Memory]:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM memories WHERE id = ?', (id,))
            row = cursor.fetchone()
            if row:
                now = time.time()
                cursor.execute('UPDATE memories SET last_accessed_at = ? WHERE id = ?', (now, id))
                self.conn.commit()
                mem = self._row_to_memory(row)
                mem.last_accessed_at = now
                return mem
            return None

    def list(self, type: Optional[MemoryType] = None, include_archived: bool = False) -> List[Memory]:
        with self.lock:
            cursor = self.conn.cursor()
            query = 'SELECT * FROM memories'
            conditions = []
            params = []

            if type is not None:
                conditions.append('type = ?')
                params.append(type)

            if not include_archived:
                conditions.append('is_archived = 0')

            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            if not rows:
                return []

            now = time.time()
            mems = []
            for row in rows:
                mem = self._row_to_memory(row)
                mem.last_accessed_at = now
                mems.append(mem)

            ids = [(now, mem.id) for mem in mems]
            cursor.executemany('UPDATE memories SET last_accessed_at = ? WHERE id = ?', ids)
            self.conn.commit()

            return mems

    def archive(self, id: str) -> None:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE memories
                SET is_archived = 1
                WHERE id = ?
            ''', (id,))
            self.conn.commit()

    def archive_many(self, ids: List[str]) -> None:
        if not ids:
            return
        with self.lock:
            cursor = self.conn.cursor()
            for i in range(0, len(ids), 500):
                chunk = ids[i:i+500]
                placeholders = ','.join(['?'] * len(chunk))
                cursor.execute(f'''
                    UPDATE memories
                    SET is_archived = 1
                    WHERE id IN ({placeholders})
                ''', tuple(chunk))
            self.conn.commit()

    def list_by_type(self, type: str, order_by: Optional[str] = None) -> List[Memory]:
        with self.lock:
            cursor = self.conn.cursor()
            query = 'SELECT * FROM memories WHERE type = ? AND is_archived = 0'
            if order_by:
                # order_by is safe in this context, just append it
                query += f' ORDER BY {order_by}'

            cursor.execute(query, (type,))
            rows = cursor.fetchall()
            if not rows:
                return []

            now = time.time()
            mems = []
            for row in rows:
                mem = self._row_to_memory(row)
                mem.last_accessed_at = now
                mems.append(mem)

            ids = [(now, mem.id) for mem in mems]
            cursor.executemany('UPDATE memories SET last_accessed_at = ? WHERE id = ?', ids)
            self.conn.commit()

            return mems

    def list_unprocessed(self, exclude_session_id: Optional[str] = None) -> List[Memory]:
        with self.lock:
            cursor = self.conn.cursor()
            query = 'SELECT * FROM memories WHERE is_processed = 0 AND is_archived = 0'
            params = []
            if exclude_session_id:
                query += ' AND (session_id != ? OR session_id IS NULL)'
                params.append(exclude_session_id)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            if not rows:
                return []

            now = time.time()
            mems = []
            for row in rows:
                mem = self._row_to_memory(row)
                mem.last_accessed_at = now
                mems.append(mem)

            ids = [(now, mem.id) for mem in mems]
            cursor.executemany('UPDATE memories SET last_accessed_at = ? WHERE id = ?', ids)
            self.conn.commit()

            return mems

    def soft_delete(self, id: str, superseded_by: Optional[str] = None) -> None:
        if id == superseded_by:
            raise ValueError("superseded_by cannot be the same as id")

        with self.lock:
            cursor = self.conn.cursor()

            if superseded_by is not None:
                cursor.execute('SELECT 1 FROM memories WHERE id = ?', (superseded_by,))
                if not cursor.fetchone():
                    raise ValueError(f"Target superseded_by id {superseded_by} does not exist")

            cursor.execute('''
                UPDATE memories
                SET is_archived = 1, superseded_by = ?
                WHERE id = ?
            ''', (superseded_by, id))
            self.conn.commit()

    def update_weight(self, id: str, delta: float) -> None:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE memories
                SET weight = weight + ?
                WHERE id = ?
            ''', (delta, id))
            self.conn.commit()

    def count_unprocessed(self) -> int:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM memories
                WHERE is_processed = 0 AND is_archived = 0
            ''')
            return cursor.fetchone()[0]

    def count_distinct_sessions(self) -> int:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT COUNT(DISTINCT session_id) FROM memories
                WHERE is_processed = 0 AND is_archived = 0 AND session_id IS NOT NULL
            ''')
            return cursor.fetchone()[0]

    def mark_processed(self, ids: List[str]) -> None:
        if not ids:
            return
        with self.lock:
            cursor = self.conn.cursor()
            placeholders = ','.join(['?'] * len(ids))
            cursor.execute(f'''
                UPDATE memories
                SET is_processed = 1
                WHERE id IN ({placeholders})
            ''', tuple(ids))
            self.conn.commit()

    def prefix_match(self, prefix: str) -> List[Memory]:
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM memories
                WHERE id LIKE ?
            ''', (f"{prefix}%",))
            rows = cursor.fetchall()
            if not rows:
                return []

            now = time.time()
            mems = []
            for row in rows:
                mem = self._row_to_memory(row)
                mem.last_accessed_at = now
                mems.append(mem)

            ids = [(now, mem.id) for mem in mems]
            cursor.executemany('UPDATE memories SET last_accessed_at = ? WHERE id = ?', ids)
            self.conn.commit()

            return mems
