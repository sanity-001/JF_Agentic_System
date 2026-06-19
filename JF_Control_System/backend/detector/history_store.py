import aiosqlite
from typing import Optional, List, Dict, Any


class HistoryStore:
    def __init__(self, db_path: str = "acquisition_history.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def init(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS acquisitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                params_json TEXT NOT NULL,
                fpath TEXT,
                filename TEXT,
                frames INTEGER,
                period TEXT,
                exptime TEXT,
                duration_ms INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'success',
                error_message TEXT,
                raw_paths TEXT DEFAULT NULL
            )
        """)
        # migrate existing DBs that lack raw_paths column
        try:
            await self._conn.execute("ALTER TABLE acquisitions ADD COLUMN raw_paths TEXT DEFAULT NULL")
        except Exception:
            pass
        await self._conn.commit()

    async def _ensure_init(self):
        if self._conn is None:
            await self.init()

    async def add(self, record: Dict[str, Any]) -> int:
        await self._ensure_init()
        cursor = await self._conn.execute(
            """INSERT INTO acquisitions
               (timestamp, params_json, fpath, filename, frames, period, exptime,
                duration_ms, status, error_message, raw_paths)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record["timestamp"], record["params_json"], record.get("fpath"),
             record.get("filename", ""),
             record.get("frames"), record.get("period"), record.get("exptime"),
             record.get("duration_ms", 0), record["status"],
             record.get("error_message"),
             record.get("raw_paths"))
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get(self, record_id: int) -> Optional[Dict[str, Any]]:
        await self._ensure_init()
        cursor = await self._conn.execute(
            "SELECT * FROM acquisitions WHERE id = ?", (record_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        await self._ensure_init()
        cursor = await self._conn.execute(
            "SELECT * FROM acquisitions ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def count(self) -> int:
        await self._ensure_init()
        cursor = await self._conn.execute("SELECT COUNT(*) FROM acquisitions")
        row = await cursor.fetchone()
        return row[0]

    async def close(self):
        if self._conn:
            await self._conn.close()
