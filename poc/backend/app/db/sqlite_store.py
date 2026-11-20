"""SQLite persistence store (SQLAlchemy 2.x + WAL + non-blocking writer thread)."""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from app.core.logging import get_logger

logger = get_logger("app.db.sqlite_store")

_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS cameras (
        id TEXT PRIMARY KEY,
        channel INTEGER NOT NULL,
        name TEXT NOT NULL,
        zone_name TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        subtype INTEGER NOT NULL DEFAULT 0,
        mode TEXT NOT NULL DEFAULT 'mjpeg',
        feature_type TEXT NOT NULL DEFAULT 'zone_presence',
        grace_seconds REAL NOT NULL DEFAULT 2.0,
        warning_seconds REAL NOT NULL DEFAULT 10.0,
        enabled INTEGER NOT NULL DEFAULT 1,
        zone_json TEXT NOT NULL DEFAULT '[]',
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cam_id TEXT NOT NULL,
        started_at REAL NOT NULL,
        ended_at REAL,
        duration_s REAL NOT NULL DEFAULT 0.0,
        peak_state TEXT NOT NULL DEFAULT 'alert'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_alert_events_cam_time ON alert_events (cam_id, started_at)",
    """
    CREATE TABLE IF NOT EXISTS runtime_snapshots (
        cam_id TEXT PRIMARY KEY,
        alert_count INTEGER NOT NULL DEFAULT 0,
        total_alert_seconds REAL NOT NULL DEFAULT 0.0,
        session_started_at REAL NOT NULL,
        timeline_json TEXT NOT NULL DEFAULT '[]',
        saved_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
]


class SqliteStore:
    """Thread-safe SQLite store with WAL mode and async writer queue for AI runtime."""

    def __init__(self, db_path: Path, retention_days: int = 90) -> None:
        self.db_path = db_path
        self.retention_days = max(1, retention_days)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine: Engine = create_engine(
            f"sqlite:///{self.db_path}",
            future=True,
            connect_args={"check_same_thread": False, "timeout": 5.0},
        )

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn: Any, _conn_record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        with self.engine.begin() as conn:
            for stmt in _DDL_STATEMENTS:
                conn.execute(text(stmt))

        self._write_queue: queue.Queue[tuple[str, Any] | None] = queue.Queue(maxsize=256)
        self._stop_event = threading.Event()
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="sqlite-writer",
            daemon=True,
        )
        self._writer_thread.start()
        self.enqueue_prune_old_events()

    def close(self) -> None:
        self._stop_event.set()
        try:
            self._write_queue.put_nowait(None)
        except queue.Full:
            pass
        if self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)
        self.engine.dispose()

    def _enqueue(self, op: str, payload: Any) -> None:
        if self._stop_event.is_set():
            return
        try:
            self._write_queue.put_nowait((op, payload))
        except queue.Full:
            logger.warning("SQLite writer queue full; dropping op=%s", op)

    def enqueue_runtime_snapshots(self, snapshots: list[dict[str, Any]]) -> None:
        if snapshots:
            self._enqueue("snapshots", snapshots)

    def enqueue_alert_event(
        self,
        cam_id: str,
        started_at: float,
        ended_at: float | None = None,
        duration_s: float = 0.0,
        peak_state: str = "alert",
    ) -> None:
        self._enqueue(
            "alert_event",
            {
                "cam_id": cam_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_s": duration_s,
                "peak_state": peak_state,
            },
        )

    def enqueue_prune_old_events(self) -> None:
        cutoff = time.time() - (self.retention_days * 86400)
        self._enqueue("prune", cutoff)

    def load_recent_snapshots(self, max_age_sec: float = 1800.0) -> dict[str, dict[str, Any]]:
        cutoff = time.time() - max_age_sec
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT cam_id, alert_count, total_alert_seconds, session_started_at, "
                    "timeline_json, saved_at FROM runtime_snapshots WHERE saved_at >= :cutoff"
                ),
                {"cutoff": cutoff},
            ).mappings().all()
        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            try:
                timeline = json.loads(r["timeline_json"] or "[]")
            except json.JSONDecodeError:
                timeline = []
            result[str(r["cam_id"])] = {
                "alert_count": int(r["alert_count"]),
                "total_alert_seconds": float(r["total_alert_seconds"]),
                "session_started_at": float(r["session_started_at"]),
                "timeline": timeline if isinstance(timeline, list) else [],
                "saved_at": float(r["saved_at"]),
            }
        return result

    def query_alert_events(
        self,
        cam_id: str,
        from_ts: float | None = None,
        to_ts: float | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = ["cam_id = :cam_id"]
        params: dict[str, Any] = {"cam_id": cam_id, "limit": max(1, min(1000, limit))}
        if from_ts is not None:
            clauses.append("started_at >= :from_ts")
            params["from_ts"] = from_ts
        if to_ts is not None:
            clauses.append("started_at <= :to_ts")
            params["to_ts"] = to_ts
        where_sql = " AND ".join(clauses)
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"SELECT id, cam_id, started_at, ended_at, duration_s, peak_state "
                    f"FROM alert_events WHERE {where_sql} ORDER BY started_at DESC LIMIT :limit"
                ),
                params,
            ).mappings().all()
        return [dict(r) for r in rows]

    def _writer_loop(self) -> None:
        while True:
            item = self._write_queue.get()
            if item is None:
                break
            op, payload = item
            try:
                if op == "snapshots":
                    self._write_snapshots(payload)
                elif op == "alert_event":
                    self._write_alert_event(payload)
                elif op == "prune":
                    self._prune_events(float(payload))
            except Exception as exc:  # noqa: BLE001
                logger.warning("SQLite writer error op=%s: %s", op, exc)
            finally:
                self._write_queue.task_done()

    def _write_snapshots(self, snapshots: list[dict[str, Any]]) -> None:
        with self.engine.begin() as conn:
            for snap in snapshots:
                conn.execute(
                    text(
                        """
                        INSERT INTO runtime_snapshots (
                            cam_id, alert_count, total_alert_seconds, session_started_at, timeline_json, saved_at
                        ) VALUES (
                            :cam_id, :alert_count, :total_alert_seconds, :session_started_at, :timeline_json, :saved_at
                        )
                        ON CONFLICT(cam_id) DO UPDATE SET
                            alert_count = excluded.alert_count,
                            total_alert_seconds = excluded.total_alert_seconds,
                            session_started_at = excluded.session_started_at,
                            timeline_json = excluded.timeline_json,
                            saved_at = excluded.saved_at
                        """
                    ),
                    {
                        "cam_id": snap["cam_id"],
                        "alert_count": int(snap["alert_count"]),
                        "total_alert_seconds": float(snap["total_alert_seconds"]),
                        "session_started_at": float(snap["session_started_at"]),
                        "timeline_json": json.dumps(snap.get("timeline", []), ensure_ascii=False),
                        "saved_at": float(snap["saved_at"]),
                    },
                )

    def _write_alert_event(self, ev: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO alert_events (cam_id, started_at, ended_at, duration_s, peak_state)
                    VALUES (:cam_id, :started_at, :ended_at, :duration_s, :peak_state)
                    """
                ),
                ev,
            )

    def _prune_events(self, cutoff: float) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM alert_events WHERE started_at < :cutoff"),
                {"cutoff": cutoff},
            )
