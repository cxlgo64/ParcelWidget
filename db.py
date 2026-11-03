"""SQLite 存储：所有单号、最新状态、归档标记。"""
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS shipments (
    number        TEXT PRIMARY KEY,
    carrier       TEXT,
    title         TEXT,             -- 邮件主题 / 手动备注
    source        TEXT,             -- 'email' / 'manual'
    status        TEXT,             -- 最新一条物流信息
    location      TEXT,
    event_time    TEXT,
    delivered     INTEGER DEFAULT 0,
    archived      INTEGER DEFAULT 0,
    error         TEXT,
    added_at      REAL,
    checked_at    REAL,
    archived_at   REAL
);
"""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def _exec(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def add(self, number, carrier, title="", source="email"):
        """新单号返回 True；已存在（包括已归档）返回 False，不会重复添加。"""
        cur = self._exec(
            "INSERT OR IGNORE INTO shipments(number, carrier, title, source, added_at) "
            "VALUES (?,?,?,?,?)",
            (number, carrier, title, source, time.time()),
        )
        return cur.rowcount > 0

    def update_status(self, number, status, location, event_time, delivered, error=None):
        self._exec(
            "UPDATE shipments SET status=?, location=?, event_time=?, delivered=?, "
            "error=?, checked_at=? WHERE number=?",
            (status, location, event_time, int(delivered), error, time.time(), number),
        )

    def set_error(self, number, error):
        self._exec(
            "UPDATE shipments SET error=?, checked_at=?, "
            "status = CASE WHEN lower(status) LIKE '%no information%' THEN NULL ELSE status END "
            "WHERE number=?",
            (error, time.time(), number),
        )

    def archive(self, number):
        self._exec(
            "UPDATE shipments SET archived=1, archived_at=? WHERE number=?",
            (time.time(), number),
        )

    def unarchive(self, number):
        self._exec("UPDATE shipments SET archived=0 WHERE number=?", (number,))

    def delete(self, number):
        self._exec("DELETE FROM shipments WHERE number=?", (number,))

    def set_title(self, number, title):
        self._exec("UPDATE shipments SET title=? WHERE number=?", (title, number))

    def active(self):
        # 已送达（等你确认）的排最前，其余按最近加入排序
        rows = self._exec(
            "SELECT * FROM shipments WHERE archived=0 "
            "ORDER BY delivered DESC, added_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def archived(self, limit=50):
        rows = self._exec(
            "SELECT * FROM shipments WHERE archived=1 ORDER BY archived_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def to_check(self):
        rows = self._exec(
            "SELECT number, carrier FROM shipments WHERE archived=0 AND delivered=0"
        ).fetchall()
        return [dict(r) for r in rows]
