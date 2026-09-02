from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pbkdf2_hash(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return digest.hex()


def _new_password_secret(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    return salt.hex(), _pbkdf2_hash(password, salt)


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    candidate = _pbkdf2_hash(password, salt)
    return hmac.compare_digest(candidate, expected_hash)


@dataclass(slots=True)
class UserRecord:
    id: int
    username: str
    created_at: str
    last_login_at: str | None = None


@dataclass(slots=True)
class ProjectRecord:
    id: int
    user_id: int
    path: str
    created_at: str
    updated_at: str
    last_opened_at: str | None = None


class LocalDatabase:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "chasm.sqlite3"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_opened_at TEXT,
                    UNIQUE(user_id, path)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    task TEXT NOT NULL,
                    project_root TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS session_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    event_index INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, event_index)
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
                    ON sessions(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_session_events_session_index
                    ON session_events(session_id, event_index);
                """
            )
            self._ensure_session_title_column()
            self._conn.commit()

    def _ensure_session_title_column(self) -> None:
        columns = {row["name"] for row in self._fetchall("PRAGMA table_info(sessions)")}
        if "title" not in columns:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN title TEXT NOT NULL DEFAULT ''")

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, tuple(params))
        self._conn.commit()
        return cur

    def _fetchone(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        cur = self._conn.execute(sql, tuple(params))
        return cur.fetchone()

    def _fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        cur = self._conn.execute(sql, tuple(params))
        return list(cur.fetchall())

    def has_users(self) -> bool:
        row = self._fetchone("SELECT 1 FROM users LIMIT 1")
        return row is not None

    def get_user_by_username(self, username: str) -> UserRecord | None:
        row = self._fetchone(
            "SELECT id, username, created_at, last_login_at FROM users WHERE username = ?",
            (username.strip(),),
        )
        if row is None:
            return None
        return UserRecord(
            id=int(row["id"]),
            username=row["username"],
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        )

    def ensure_system_user(self, username: str = "local") -> UserRecord:
        row = self._fetchone(
            "SELECT id, username, created_at, last_login_at FROM users WHERE username = ?",
            (username,),
        )
        if row is not None:
            return UserRecord(
                id=int(row["id"]),
                username=row["username"],
                created_at=row["created_at"],
                last_login_at=row["last_login_at"],
            )
        secret = secrets.token_urlsafe(24)
        return self.create_user(username, secret)

    def create_user(self, username: str, password: str) -> UserRecord:
        username = username.strip()
        if not username:
            raise ValueError("username is required")
        if not password:
            raise ValueError("password is required")
        salt, digest = _new_password_secret(password)
        created_at = utc_now()
        cur = self._execute(
            """
            INSERT INTO users (username, password_salt, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username, salt, digest, created_at),
        )
        return UserRecord(id=int(cur.lastrowid), username=username, created_at=created_at)

    def authenticate(self, username: str, password: str) -> UserRecord | None:
        row = self._fetchone(
            "SELECT id, username, password_salt, password_hash, created_at, last_login_at FROM users WHERE username = ?",
            (username.strip(),),
        )
        if row is None:
            return None
        if not verify_password(password, row["password_salt"], row["password_hash"]):
            return None
        now = utc_now()
        self._execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        return UserRecord(
            id=int(row["id"]),
            username=row["username"],
            created_at=row["created_at"],
            last_login_at=now,
        )

    def create_auth_session(self, user_id: int, ttl_days: int = 30) -> str:
        token = secrets.token_urlsafe(32)
        now = utc_now()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat(timespec="seconds")
        self._execute(
            """
            INSERT INTO auth_sessions (token, user_id, created_at, expires_at, revoked_at, last_seen_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (token, user_id, now, expires_at, now),
        )
        return token

    def get_user_by_token(self, token: str) -> UserRecord | None:
        row = self._fetchone(
            """
            SELECT u.id, u.username, u.created_at, u.last_login_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.revoked_at IS NULL AND s.expires_at > ?
            """,
            (token, utc_now()),
        )
        if row is None:
            return None
        self._execute("UPDATE auth_sessions SET last_seen_at = ? WHERE token = ?", (utc_now(), token))
        return UserRecord(
            id=int(row["id"]),
            username=row["username"],
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        )

    def revoke_auth_session(self, token: str) -> None:
        self._execute("UPDATE auth_sessions SET revoked_at = ? WHERE token = ?", (utc_now(), token))

    def upsert_project(self, user_id: int, path: str) -> ProjectRecord:
        now = utc_now()
        row = self._fetchone("SELECT id FROM projects WHERE user_id = ? AND path = ?", (user_id, path))
        if row is None:
            cur = self._execute(
                """
                INSERT INTO projects (user_id, path, created_at, updated_at, last_opened_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, path, now, now, now),
            )
            project_id = int(cur.lastrowid)
            created_at = now
        else:
            self._execute(
                "UPDATE projects SET updated_at = ?, last_opened_at = ? WHERE id = ?",
                (now, now, row["id"]),
            )
            project_id = int(row["id"])
            created_at = self._fetchone("SELECT created_at FROM projects WHERE id = ?", (project_id,))["created_at"]
        return ProjectRecord(
            id=project_id,
            user_id=user_id,
            path=path,
            created_at=created_at,
            updated_at=now,
            last_opened_at=now,
        )

    def list_projects(self, user_id: int, limit: int = 20) -> list[ProjectRecord]:
        rows = self._fetchall(
            """
            SELECT id, user_id, path, created_at, updated_at, last_opened_at
            FROM projects
            WHERE user_id = ?
            ORDER BY COALESCE(last_opened_at, updated_at) DESC, updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [
            ProjectRecord(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                path=row["path"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                last_opened_at=row["last_opened_at"],
            )
            for row in rows
        ]

    def create_session(
        self,
        user_id: int,
        task: str,
        project_root: str,
        mode: str = "auto",
        title: str = "",
    ) -> dict[str, Any]:
        session_id = secrets.token_hex(6)
        now = utc_now()
        self._execute(
            """
            INSERT INTO sessions (id, user_id, task, project_root, mode, status, created_at, updated_at, result, title)
            VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, '', ?)
            """,
            (session_id, user_id, task, project_root, mode, now, now, title),
        )
        self.append_message(session_id, "user", task)
        return self.get_session(session_id) or {}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT id, user_id, task, project_root, mode, status, created_at, updated_at, result, title
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "user_id": int(row["user_id"]),
            "task": row["task"],
            "project_root": row["project_root"],
            "mode": row["mode"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "result": row["result"],
            "title": row["title"],
            "events": self.get_events(session_id),
            "messages": self.get_messages(session_id),
        }

    def list_sessions(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT id, user_id, task, project_root, mode, status, created_at, updated_at, result, title
            FROM sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [self.get_session(row["id"]) or {} for row in rows]

    def delete_session(self, session_id: str, user_id: int) -> None:
        self._execute("DELETE FROM sessions WHERE id = ? AND user_id = ?", (session_id, user_id))

    def update_session(self, session_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"task", "project_root", "mode", "status", "result", "title"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_session(session_id) or {}
        updates["updated_at"] = utc_now()
        columns = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [session_id]
        self._execute(f"UPDATE sessions SET {columns} WHERE id = ?", params)
        return self.get_session(session_id) or {}

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self._execute(
            """
            INSERT INTO session_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, utc_now()),
        )

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT role, content, created_at
            FROM session_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
        return [{"role": row["role"], "content": row["content"], "created_at": row["created_at"]} for row in rows]

    def append_event(self, session_id: str, event: Any) -> None:
        idx_row = self._fetchone(
            "SELECT COALESCE(MAX(event_index) + 1, 0) AS next_index FROM session_events WHERE session_id = ?",
            (session_id,),
        )
        next_index = int(idx_row["next_index"] if idx_row is not None else 0)
        self._execute(
            """
            INSERT INTO session_events (session_id, event_index, kind, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, next_index, event.kind, json.dumps(event.payload, ensure_ascii=False), utc_now()),
        )

    def get_events(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT kind, payload_json
            FROM session_events
            WHERE session_id = ?
            ORDER BY event_index ASC
            """,
            (session_id,),
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            events.append({"kind": row["kind"], "payload": payload})
        return events

    def get_events_since(self, session_id: str, index: int) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT kind, payload_json
            FROM session_events
            WHERE session_id = ? AND event_index >= ?
            ORDER BY event_index ASC
            """,
            (session_id, index),
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            events.append({"kind": row["kind"], "payload": payload})
        return events

    def import_legacy_sessions(self, legacy_root: Path) -> int:
        legacy_dir = legacy_root / ".chasm" / "sessions"
        if not legacy_dir.exists():
            return 0
        imported = 0
        for path in sorted(legacy_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            session_id = str(payload.get("id") or "")
            if not session_id:
                continue
            if self._fetchone("SELECT 1 FROM sessions WHERE id = ?", (session_id,)) is not None:
                continue
            now = utc_now()
            self._execute(
                """
                INSERT INTO sessions (id, user_id, task, project_root, mode, status, created_at, updated_at, result, title)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    1,
                    payload.get("task", ""),
                    payload.get("project_root", ""),
                    payload.get("mode", "auto"),
                    payload.get("status", "done"),
                    payload.get("created_at", now),
                    payload.get("updated_at", now),
                    payload.get("result", ""),
                    payload.get("title", ""),
                ),
            )
            for message in payload.get("messages", []) or []:
                if isinstance(message, dict):
                    self.append_message(session_id, str(message.get("role", "assistant")), str(message.get("content", "")))
            for idx, event in enumerate(payload.get("events", []) or []):
                if not isinstance(event, dict):
                    continue
                self._execute(
                    """
                    INSERT INTO session_events (session_id, event_index, kind, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        idx,
                        str(event.get("kind", "event")),
                        json.dumps(event.get("payload", {}), ensure_ascii=False),
                        now,
                    ),
                )
            imported += 1
        return imported
