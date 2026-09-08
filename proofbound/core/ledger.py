import sqlite3
import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from proofbound.models.action_run import ActionRun, ActionEvent, PlanStep, RiskLevel, ApprovalState, StepStatus, RollbackInfo
from proofbound.models.evidence import Citation, Artifact, ReplaySession
from proofbound.models.memory import MemoryUpdateProposal, MemoryCategory
from proofbound.config import settings

class ActionLedger:
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
            CREATE TABLE IF NOT EXISTS run_claims (run_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS action_runs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                intent TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                approval_state TEXT NOT NULL,
                worker TEXT NOT NULL,
                inputs_hash TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                scopes_json TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                rollback_json TEXT
            );

            CREATE TABLE IF NOT EXISTS action_events (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_index INTEGER,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES action_runs(id)
            );

            CREATE TABLE IF NOT EXISTS citations (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                title TEXT NOT NULL,
                snippet TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                confidence REAL NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES action_runs(id)
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                name TEXT NOT NULL,
                path_or_uri TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                content_preview TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES action_runs(id)
            );

            CREATE TABLE IF NOT EXISTS memory_proposals (
                proposal_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                fact_id TEXT,
                operation TEXT NOT NULL,
                proposed_category TEXT NOT NULL,
                proposed_content TEXT NOT NULL,
                provenance_source TEXT NOT NULL,
                confidence REAL NOT NULL,
                justification TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES action_runs(id)
            );
            """)

    def claim_run(self, run_id: str):
        with self._get_conn() as conn:
            try:
                conn.execute("INSERT INTO run_claims VALUES (?)", (run_id,))
            except sqlite3.IntegrityError:
                raise PermissionError("Run is already executing or requires recovery after an interrupted execution")

    def release_run(self, run_id: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM run_claims WHERE run_id = ?", (run_id,))

    def save_run(self, run: ActionRun):
        with self._get_conn() as conn:
            plan_json = json.dumps([p.model_dump() for p in run.plan_steps], default=str)
            scopes_json = json.dumps(run.requested_scopes)
            rollback_json = json.dumps(run.rollback_or_recovery.model_dump(), default=str) if run.rollback_or_recovery else None
            
            conn.execute("""
            INSERT OR REPLACE INTO action_runs (
                id, user_id, intent, risk_level, approval_state, worker, inputs_hash,
                plan_json, scopes_json, started_at, completed_at, rollback_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run.id, run.user_id, run.intent, run.risk_level.value, run.approval_state.value,
                run.worker, run.inputs_hash, plan_json, scopes_json,
                run.started_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
                rollback_json
            ))

            for event in run.events:
                conn.execute("""
                INSERT OR REPLACE INTO action_events (
                    id, run_id, step_index, event_type, severity, message, payload_hash, payload_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.id, event.run_id, event.step_index, event.event_type, event.severity,
                    event.message, event.payload_hash, json.dumps(event.payload, default=str),
                    event.timestamp.isoformat()
                ))

            for cit in run.citations:
                conn.execute("""
                INSERT OR REPLACE INTO citations (
                    id, run_id, source_type, source_uri, title, snippet, content_hash, confidence, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cit.id, cit.run_id, cit.source_type, cit.source_uri, cit.title, cit.snippet,
                    cit.content_hash, cit.confidence, cit.timestamp.isoformat()
                ))

            for art in run.artifacts:
                conn.execute("""
                INSERT OR REPLACE INTO artifacts (
                    id, run_id, artifact_type, name, path_or_uri, mime_type, size_bytes, content_preview, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    art.id, art.run_id, art.artifact_type, art.name, art.path_or_uri, art.mime_type,
                    art.size_bytes, art.content_preview, art.created_at.isoformat()
                ))

            for mem in run.memory_updates:
                conn.execute("""
                INSERT OR REPLACE INTO memory_proposals (
                    proposal_id, run_id, fact_id, operation, proposed_category, proposed_content,
                    provenance_source, confidence, justification, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mem.proposal_id, mem.run_id, mem.fact_id, mem.operation, mem.proposed_category.value,
                    mem.proposed_content, mem.provenance_source, mem.confidence, mem.justification,
                    mem.status, mem.created_at.isoformat()
                ))

    def get_run(self, run_id: str) -> Optional[ActionRun]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM action_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None
            
            plan_steps = [PlanStep(**p) for p in json.loads(row["plan_json"])]
            scopes = json.loads(row["scopes_json"])
            rollback = RollbackInfo(**json.loads(row["rollback_json"])) if row["rollback_json"] else None

            ev_rows = conn.execute("SELECT * FROM action_events WHERE run_id = ? ORDER BY timestamp ASC", (run_id,)).fetchall()
            events = [
                ActionEvent(
                    id=r["id"],
                    run_id=r["run_id"],
                    step_index=r["step_index"],
                    event_type=r["event_type"],
                    severity=r["severity"],
                    message=r["message"],
                    payload_hash=r["payload_hash"],
                    payload=json.loads(r["payload_json"]),
                    timestamp=datetime.fromisoformat(r["timestamp"])
                ) for r in ev_rows
            ]

            cit_rows = conn.execute("SELECT * FROM citations WHERE run_id = ?", (run_id,)).fetchall()
            citations = [
                Citation(
                    id=r["id"],
                    run_id=r["run_id"],
                    source_type=r["source_type"],
                    source_uri=r["source_uri"],
                    title=r["title"],
                    snippet=r["snippet"],
                    content_hash=r["content_hash"],
                    confidence=r["confidence"],
                    timestamp=datetime.fromisoformat(r["timestamp"])
                ) for r in cit_rows
            ]

            art_rows = conn.execute("SELECT * FROM artifacts WHERE run_id = ?", (run_id,)).fetchall()
            artifacts = [
                Artifact(
                    id=r["id"],
                    run_id=r["run_id"],
                    artifact_type=r["artifact_type"],
                    name=r["name"],
                    path_or_uri=r["path_or_uri"],
                    mime_type=r["mime_type"],
                    size_bytes=r["size_bytes"],
                    content_preview=r["content_preview"],
                    created_at=datetime.fromisoformat(r["created_at"])
                ) for r in art_rows
            ]

            mem_rows = conn.execute("SELECT * FROM memory_proposals WHERE run_id = ?", (run_id,)).fetchall()
            memory_updates = [
                MemoryUpdateProposal(
                    proposal_id=r["proposal_id"],
                    run_id=r["run_id"],
                    fact_id=r["fact_id"],
                    operation=r["operation"],
                    proposed_category=MemoryCategory(r["proposed_category"]),
                    proposed_content=r["proposed_content"],
                    provenance_source=r["provenance_source"],
                    confidence=r["confidence"],
                    justification=r["justification"],
                    status=r["status"],
                    created_at=datetime.fromisoformat(r["created_at"])
                ) for r in mem_rows
            ]

            return ActionRun(
                id=row["id"],
                user_id=row["user_id"],
                intent=row["intent"],
                plan_steps=plan_steps,
                requested_scopes=scopes,
                risk_level=RiskLevel(row["risk_level"]),
                approval_state=ApprovalState(row["approval_state"]),
                worker=row["worker"],
                inputs_hash=row["inputs_hash"],
                events=events,
                artifacts=artifacts,
                citations=citations,
                memory_updates=memory_updates,
                started_at=datetime.fromisoformat(row["started_at"]),
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                rollback_or_recovery=rollback
            )

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute("""
            SELECT id, user_id, intent, risk_level, approval_state, worker, started_at, completed_at
            FROM action_runs ORDER BY started_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def replay_run(self, run_id: str) -> ReplaySession:
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run '{run_id}' not found in ledger")

        divergences = []
        for i, ev in enumerate(run.events):
            if ev.payload and not ev.payload_hash:
                divergences.append(f"Event {ev.id} missing payload hash")
            elif ev.payload:
                expected = hashlib.sha256(json.dumps(ev.payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
                if ev.payload_hash != expected:
                    divergences.append(f"Event {ev.id} payload hash mismatch (got {ev.payload_hash}, expected {expected})")

        total = len(run.events)
        replayed = total - len(divergences)
        match_rate = (replayed / total) if total > 0 else 1.0

        return ReplaySession(
            run_id=run_id,
            total_events=total,
            replayed_events=replayed,
            match_rate=match_rate,
            divergences=divergences,
            is_identical=(len(divergences) == 0)
        )

    def export_markdown(self, run_id: str) -> str:
        run = self.get_run(run_id)
        if not run:
            return f"# ActionRun Not Found: {run_id}"

        lines = [
            f"# Proofbound Verifiable Action Ledger Report",
            f"**Run ID:** `{run.id}`  ",
            f"**Intent:** {run.intent}  ",
            f"**Risk Level:** `{run.risk_level.value}` | **Approval State:** `{run.approval_state.value}`  ",
            f"**Started:** {run.started_at.isoformat()} | **Completed:** {run.completed_at.isoformat() if run.completed_at else 'In Progress'}  ",
            f"**Inputs Hash (SHA-256):** `{run.inputs_hash}`  ",
            "",
            "## 1. Execution Plan",
            "| Step | Title | Tool | Risk | Status |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for step in run.plan_steps:
            lines.append(f"| {step.step_index} | {step.title} | `{step.tool_name}` | `{step.estimated_risk.value}` | `{step.status.value}` |")

        lines.extend([
            "",
            "## 2. Citations & Evidence",
            "| Citation ID | Source | Title / URL | Snippet | Confidence |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for cit in run.citations:
            lines.append(f"| `{cit.id}` | `{cit.source_type}` | [{cit.title}]({cit.source_uri}) | {cit.snippet[:80]}... | {cit.confidence*100:.1f}% |")

        lines.extend([
            "",
            "## 3. Generated Artifacts",
            "| Name | Type | Size | Path / Reference |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for art in run.artifacts:
            lines.append(f"| {art.name} | `{art.artifact_type}` | {art.size_bytes} B | `{art.path_or_uri}` |")

        lines.extend([
            "",
            "## 4. Proposed Memory Mutations",
            "| Proposal ID | Operation | Category | Content | Provenance Source |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for mem in run.memory_updates:
            lines.append(f"| `{mem.proposal_id}` | `{mem.operation}` | `{mem.proposed_category.value}` | {mem.proposed_content} | `{mem.provenance_source}` |")

        lines.extend([
            "",
            "## 5. Event Audit Timeline",
            "| Timestamp | Event Type | Severity | Message |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for ev in run.events:
            lines.append(f"| `{ev.timestamp.strftime('%H:%M:%S.%f')[:-3]}` | `{ev.event_type}` | `{ev.severity}` | {ev.message} |")

        return "\n".join(lines)
