"""SQLite checkpoints and one saved plan per request; no external publishing."""

from __future__ import annotations

import json
import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path

from .domain import canonical, digest


class BusyError(RuntimeError):
    pass


@contextmanager
def execution_lock(path):
    """OS releases this lock on process exit; leftover lock files are harmless."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise BusyError("同一个数据库正在执行其他任务，请稍后重试") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS runs (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS plans (request_id TEXT PRIMARY KEY, plan_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL)")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def get_run(self, request_id: str):
        row = self.db.execute("SELECT fingerprint, state FROM runs WHERE request_id = ?", (request_id,)).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def checkpoint(self, state: dict, fingerprint: str):
        self.db.execute("INSERT INTO runs VALUES (?, ?, ?) ON CONFLICT(request_id) DO UPDATE SET state=excluded.state", (state["request_id"], fingerprint, canonical(state)))

    def get_plan(self, request_id: str):
        row = self.db.execute("SELECT body FROM plans WHERE request_id = ?", (request_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_plan(self, request_id: str, body: dict):
        existing = self.get_plan(request_id)
        if existing:
            return existing
        body = {**body, "plan_id": "P-" + digest(request_id)[:16], "request_id": request_id}
        self.db.execute("INSERT INTO plans VALUES (?, ?, ?)", (request_id, body["plan_id"], canonical(body)))
        return body
