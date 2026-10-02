import logging
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Self

from main.package.repository.chat_repository import ChatRepository
from main.package.repository.dto import Chat, ChatSummary, NewMessage, Session, StoredMessage
from main.package.repository.exceptions import (
    ChatNotFoundError,
    InvalidRepositoryArgumentError,
    InvalidRepositorySettingError,
    RepositoryOperationError,
    SessionNotFoundError,
)

_logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_SCHEMA_VERSION = 1
_UUID_VERSION = 7
_DEFAULT_TITLE = "New chat"
_MAX_TITLE_LENGTH = 200
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_MICROSECOND = timedelta(microseconds=1)

_LIVE_CHAT_SQL = (
    "SELECT c.chat_id, c.session_id, c.title, c.created_at, c.updated_at "
    "FROM chats AS c JOIN sessions AS s ON s.session_id = c.session_id "
    "WHERE c.chat_id = ? AND c.session_id = ? AND s.expires_at > ?"
)


def _now_us() -> int:
    return time.time_ns() // 1000


def _to_datetime(microseconds: int) -> datetime:
    return _EPOCH + timedelta(microseconds=microseconds)


def _to_microseconds(duration: timedelta) -> int:
    return duration // _ONE_MICROSECOND


class SqliteChatRepository(ChatRepository):
    def __init__(
        self,
        *,
        database_path: str | os.PathLike[str],
        session_ttl: timedelta,
        sweep_interval: timedelta,
        busy_timeout: timedelta,
    ) -> None:
        self._database_path = self._require_path(database_path)
        self._session_ttl_us = _to_microseconds(self._require_positive("session_ttl", session_ttl))
        self._sweep_interval_seconds = self._require_positive("sweep_interval", sweep_interval).total_seconds()
        self._busy_timeout_seconds = self._require_positive("busy_timeout", busy_timeout).total_seconds()

        self._initialise_database()

        self._stop_sweeper = threading.Event()
        self._sweeper = threading.Thread(target=self._run_sweeper, name="sqlite-chat-repository-sweeper", daemon=True)
        self._sweeper.start()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def create_session(self) -> Session:
        session_id = str(uuid.uuid7())
        created_at = _now_us()
        expires_at = created_at + self._session_ttl_us

        with self._transaction(write=True) as connection:
            connection.execute(
                "INSERT INTO sessions (session_id, created_at, expires_at) VALUES (?, ?, ?)",
                (session_id, created_at, expires_at),
            )

        return Session(session_id=session_id, created_at=_to_datetime(created_at), expires_at=_to_datetime(expires_at))

    def get_session(self, session_id: str) -> Session:
        session_id = self._require_uuid7("session_id", session_id)

        with self._transaction(write=False) as connection:
            row = self._live_session_row(connection, session_id, _now_us())

        return Session(session_id=row[0], created_at=_to_datetime(row[1]), expires_at=_to_datetime(row[2]))

    def create_chat(self, session_id: str, title: str = _DEFAULT_TITLE) -> ChatSummary:
        session_id = self._require_uuid7("session_id", session_id)
        title = self._require_title(title)
        chat_id = str(uuid.uuid7())
        now = _now_us()

        with self._transaction(write=True) as connection:
            self._live_session_row(connection, session_id, now)
            connection.execute(
                "INSERT INTO chats (chat_id, session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, session_id, title, now, now),
            )

        return ChatSummary(
            chat_id=chat_id,
            session_id=session_id,
            title=title,
            created_at=_to_datetime(now),
            updated_at=_to_datetime(now),
        )

    def list_chats(self, session_id: str) -> tuple[ChatSummary, ...]:
        session_id = self._require_uuid7("session_id", session_id)
        now = _now_us()

        with self._transaction(write=False) as connection:
            self._live_session_row(connection, session_id, now)
            rows = connection.execute(
                "SELECT chat_id, session_id, title, created_at, updated_at FROM chats "
                "WHERE session_id = ? ORDER BY updated_at DESC, chat_id DESC",
                (session_id,),
            ).fetchall()

        return tuple(self._summary(row) for row in rows)

    def get_chat(self, session_id: str, chat_id: str) -> Chat:
        session_id = self._require_uuid7("session_id", session_id)
        chat_id = self._require_uuid7("chat_id", chat_id)

        with self._transaction(write=False) as connection:
            return self._read_chat(connection, session_id, chat_id, _now_us())

    def rename_chat(self, session_id: str, chat_id: str, title: str) -> ChatSummary:
        session_id = self._require_uuid7("session_id", session_id)
        chat_id = self._require_uuid7("chat_id", chat_id)
        title = self._require_title(title)
        now = _now_us()

        with self._transaction(write=True) as connection:
            self._live_chat_row(connection, session_id, chat_id, now)
            connection.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE chat_id = ?",
                (title, now, chat_id),
            )
            return self._summary(self._live_chat_row(connection, session_id, chat_id, now))

    def add_messages(self, session_id: str, chat_id: str, messages: Sequence[NewMessage]) -> Chat:
        session_id = self._require_uuid7("session_id", session_id)
        chat_id = self._require_uuid7("chat_id", chat_id)
        messages = self._require_messages(messages)
        now = _now_us()

        with self._transaction(write=True) as connection:
            self._live_chat_row(connection, session_id, chat_id, now)
            connection.executemany(
                "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                [(chat_id, message.role, message.content, now) for message in messages],
            )
            connection.execute("UPDATE chats SET updated_at = ? WHERE chat_id = ?", (now, chat_id))
            return self._read_chat(connection, session_id, chat_id, now)

    def delete_chat(self, session_id: str, chat_id: str) -> None:
        session_id = self._require_uuid7("session_id", session_id)
        chat_id = self._require_uuid7("chat_id", chat_id)
        now = _now_us()

        with self._transaction(write=True) as connection:
            self._live_chat_row(connection, session_id, chat_id, now)
            connection.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))

    def delete_expired_sessions(self) -> int:
        with self._transaction(write=True) as connection:
            return connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (_now_us(),)).rowcount

    def close(self) -> None:
        self._stop_sweeper.set()
        self._sweeper.join()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=self._busy_timeout_seconds, isolation_level=None)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def _transaction(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        try:
            connection = self._connect()
        except sqlite3.Error as error:
            raise RepositoryOperationError(f"Could not open SQLite database {self._database_path}") from error

        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except sqlite3.Error as error:
            self._rollback(connection)
            raise RepositoryOperationError("SQLite operation failed") from error
        except BaseException:
            self._rollback(connection)
            raise
        finally:
            connection.close()

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        if not connection.in_transaction:
            return

        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            _logger.exception("Failed to roll back a SQLite transaction")

    def _initialise_database(self) -> None:
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            schema = _SCHEMA_PATH.read_text()
            connection = self._connect()
        except (OSError, sqlite3.Error) as error:
            raise RepositoryOperationError(f"Could not open SQLite database {self._database_path}") from error

        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > _SCHEMA_VERSION:
                raise RepositoryOperationError(
                    f"Database schema version {version} is newer than supported version {_SCHEMA_VERSION}"
                )
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(schema)
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        except sqlite3.Error as error:
            raise RepositoryOperationError(f"Could not initialise SQLite database {self._database_path}") from error
        finally:
            connection.close()

    def _run_sweeper(self) -> None:
        while not self._stop_sweeper.wait(self._sweep_interval_seconds):
            try:
                self.delete_expired_sessions()
            except Exception:
                _logger.exception("Failed to delete expired sessions from the SQLite chat repository")

    @staticmethod
    def _live_session_row(connection: sqlite3.Connection, session_id: str, now: int) -> tuple:
        row = connection.execute(
            "SELECT session_id, created_at, expires_at FROM sessions WHERE session_id = ? AND expires_at > ?",
            (session_id, now),
        ).fetchone()
        if row is None:
            raise SessionNotFoundError(f"Session {session_id} does not exist or has expired")

        return row

    @staticmethod
    def _live_chat_row(connection: sqlite3.Connection, session_id: str, chat_id: str, now: int) -> tuple:
        row = connection.execute(_LIVE_CHAT_SQL, (chat_id, session_id, now)).fetchone()
        if row is None:
            raise ChatNotFoundError(f"Chat {chat_id} was not found")

        return row

    def _read_chat(self, connection: sqlite3.Connection, session_id: str, chat_id: str, now: int) -> Chat:
        summary = self._summary(self._live_chat_row(connection, session_id, chat_id, now))
        rows = connection.execute(
            "SELECT message_id, role, content, created_at FROM messages WHERE chat_id = ? ORDER BY message_id",
            (chat_id,),
        ).fetchall()
        messages = tuple(
            StoredMessage(message_id=row[0], role=row[1], content=row[2], created_at=_to_datetime(row[3]))
            for row in rows
        )

        return Chat(**summary.model_dump(), messages=messages)

    @staticmethod
    def _summary(row: tuple) -> ChatSummary:
        return ChatSummary(
            chat_id=row[0],
            session_id=row[1],
            title=row[2],
            created_at=_to_datetime(row[3]),
            updated_at=_to_datetime(row[4]),
        )

    @staticmethod
    def _require_uuid7(name: str, value: str) -> str:
        if not isinstance(value, str):
            raise InvalidRepositoryArgumentError(f"{name} must be a UUIDv7 string")

        try:
            parsed = uuid.UUID(value)
        except ValueError as error:
            raise InvalidRepositoryArgumentError(f"{name} must be a UUIDv7 string") from error

        if parsed.version != _UUID_VERSION:
            raise InvalidRepositoryArgumentError(f"{name} must be a UUIDv7 string")

        return str(parsed)

    @staticmethod
    def _require_title(title: str) -> str:
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= _MAX_TITLE_LENGTH:
            raise InvalidRepositoryArgumentError(f"title must be 1 to {_MAX_TITLE_LENGTH} characters")

        return title.strip()

    @staticmethod
    def _require_messages(messages: Sequence[NewMessage]) -> tuple[NewMessage, ...]:
        if isinstance(messages, str) or not isinstance(messages, Sequence) or not messages:
            raise InvalidRepositoryArgumentError("messages must be a non-empty sequence of NewMessage")

        if not all(isinstance(message, NewMessage) for message in messages):
            raise InvalidRepositoryArgumentError("every message must be a NewMessage")

        return tuple(messages)

    @staticmethod
    def _require_path(database_path: str | os.PathLike[str]) -> Path:
        if not isinstance(database_path, str | os.PathLike) or not os.fspath(database_path):
            raise InvalidRepositorySettingError("database_path must be a non-empty path")

        return Path(database_path)

    @staticmethod
    def _require_positive(name: str, value: timedelta) -> timedelta:
        if not isinstance(value, timedelta) or value <= timedelta(0):
            raise InvalidRepositorySettingError(f"{name} must be a positive timedelta")

        return value
