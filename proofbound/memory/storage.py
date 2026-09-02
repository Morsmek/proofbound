import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from proofbound.models.memory import (
    ProvenanceFact,
    MemoryCategory,
    MemoryStatus,
    MemoryRevision,
)
from proofbound.config import settings

class MemoryStorage:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_facts (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                provenance_run_id TEXT NOT NULL,
                provenance_source TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_revisions (
                revision_id TEXT PRIMARY KEY,
                fact_id TEXT NOT NULL,
                author TEXT NOT NULL,
                previous_content TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (fact_id) REFERENCES memory_facts(id)
            );
            """)

    def save_fact(self, fact: ProvenanceFact):
        with self._get_conn() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO memory_facts (
                id, category, content, provenance_run_id, provenance_source,
                confidence, status, tags_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fact.id, fact.category.value, fact.content, fact.provenance_run_id,
                fact.provenance_source, fact.confidence, fact.status.value,
                json.dumps(fact.tags), fact.created_at.isoformat(), fact.updated_at.isoformat()
            ))

            for rev in fact.revisions:
                conn.execute("""
                INSERT OR REPLACE INTO memory_revisions (
                    revision_id, fact_id, author, previous_content, reason, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    rev.revision_id, fact.id, rev.author, rev.previous_content,
                    rev.reason, rev.timestamp.isoformat()
                ))

    def get_fact(self, fact_id: str) -> Optional[ProvenanceFact]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM memory_facts WHERE id = ?", (fact_id,)).fetchone()
            if not row:
                return None
            
            rev_rows = conn.execute(
                "SELECT * FROM memory_revisions WHERE fact_id = ? ORDER BY timestamp ASC", (fact_id,)
            ).fetchall()
            revisions = [
                MemoryRevision(
                    revision_id=r["revision_id"],
                    author=r["author"],
                    previous_content=r["previous_content"],
                    reason=r["reason"],
                    timestamp=datetime.fromisoformat(r["timestamp"])
                ) for r in rev_rows
            ]

            return ProvenanceFact(
                id=row["id"],
                category=MemoryCategory(row["category"]),
                content=row["content"],
                provenance_run_id=row["provenance_run_id"],
                provenance_source=row["provenance_source"],
                confidence=row["confidence"],
                status=MemoryStatus(row["status"]),
                tags=json.loads(row["tags_json"]),
                revisions=revisions,
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"])
            )

    def list_facts(self, include_archived: bool = False) -> List[ProvenanceFact]:
        with self._get_conn() as conn:
            query = "SELECT id FROM memory_facts" if include_archived else "SELECT id FROM memory_facts WHERE status != 'archived'"
            rows = conn.execute(query + " ORDER BY updated_at DESC").fetchall()
            facts = []
            for r in rows:
                fact = self.get_fact(r["id"])
                if fact:
                    facts.append(fact)
            return facts

    def delete_fact(self, fact_id: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM memory_revisions WHERE fact_id = ?", (fact_id,))
            res = conn.execute("DELETE FROM memory_facts WHERE id = ?", (fact_id,))
            return res.rowcount > 0
