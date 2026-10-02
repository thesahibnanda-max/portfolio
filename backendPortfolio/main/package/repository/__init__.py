"""
Storage for anonymous visitor sessions and their chats, in SQLite.

Exports:
    ChatRepository: the interface (an ABC), so another database can be added
    later without changing callers.
    SqliteChatRepository: the SQLite implementation.
    Session, ChatSummary, Chat, StoredMessage, NewMessage and the MessageRole
    alias: the DTOs.
    RepositoryError and its subclasses: the errors described under Errors.

Session model:
    Visitors are anonymous. The first call creates a session with
    create_session(), which returns a UUIDv7 session id (time ordered, with
    74 random bits, so ids cannot be guessed). The client sends that id on
    every later call. The server stores the session's own created_at and
    expires_at = created_at + session_ttl, so a client cannot extend a
    session by crafting an id. When a session expires, it and all its chats
    and messages are gone.

Construction:
    SqliteChatRepository(*, database_path, session_ttl, sweep_interval, busy_timeout)
    database_path: str or os.PathLike of the SQLite file; its folder is
    created if needed. From main.config.AppConfig.repository.database_path.
    session_ttl: positive timedelta a session lives, from
    AppConfig.repository.session_ttl (default 12 hours). It is the single
    source of the session lifetime.
    sweep_interval: positive timedelta between background deletions of
    expired sessions (default 20 minutes).
    busy_timeout: positive timedelta SQLite waits for another writer before
    failing (default 5 seconds).
    Every setting is keyword-only and validated; a bad one raises
    InvalidRepositorySettingError. The constructor applies schema.sql and
    starts the sweeper; call close() when done, or use it as a context
    manager.

Methods (all ids are UUIDv7 strings; anything else raises
InvalidRepositoryArgumentError):
    create_session() -> Session
    get_session(session_id) -> Session: SessionNotFoundError if the session
    does not exist or has expired.
    create_chat(session_id, title="New chat") -> ChatSummary
    list_chats(session_id) -> tuple[ChatSummary, ...]: most recently updated
    first.
    get_chat(session_id, chat_id) -> Chat: the chat with its messages, oldest
    first.
    rename_chat(session_id, chat_id, title) -> ChatSummary
    add_messages(session_id, chat_id, messages) -> Chat: appends every
    NewMessage and bumps updated_at in one transaction, so a user message
    and its answer are saved together or not at all.
    delete_chat(session_id, chat_id) -> None
    delete_expired_sessions() -> int: deletes every expired session (and, by
    cascade, its chats and messages) and returns how many were deleted.
    create_chat and list_chats raise SessionNotFoundError for a missing or
    expired session. Titles are trimmed and must be 1 to 200 characters;
    messages must be a non-empty sequence of NewMessage.

Ownership:
    Every chat operation matches both the chat id and the session id. A chat
    that belongs to another session, a chat that does not exist and a chat
    of an expired session all raise ChatNotFoundError, so a visitor cannot
    learn which chat ids exist.

Expiry:
    Every read and write only sees sessions whose expires_at is still in the
    future, so a session disappears the moment it expires, even before any
    cleanup. A daemon thread calls delete_expired_sessions() every
    sweep_interval to remove the rows; it logs and survives any error.

Schema (schema.sql, embedded in this package, PRAGMA user_version 1):
    sessions (session_id, created_at, expires_at), chats (chat_id,
    session_id, title, created_at, updated_at) and messages (message_id,
    chat_id, role "user" or "assistant", content, created_at), with foreign
    keys ON DELETE CASCADE and STRICT column types. Times are integer UTC
    microseconds since the epoch; the DTOs expose timezone-aware datetimes.
    A database written by a newer schema version is refused.

Connections and transactions:
    Each operation opens its own short-lived connection, so no connection is
    ever shared between threads. Connections enable foreign keys and
    synchronous=NORMAL, the database uses WAL journaling so reads never wait
    for writers, and writes start with BEGIN IMMEDIATE so concurrent writers
    queue (up to busy_timeout) instead of deadlocking. Any SQLite failure
    rolls the transaction back and raises RepositoryOperationError with the
    original error chained as __cause__.

Errors (all in exceptions.py, all subclasses of RepositoryError):
    InvalidRepositorySettingError: a constructor setting is invalid.
    InvalidRepositoryArgumentError: an id, title or message list is invalid.
    SessionNotFoundError: the session does not exist or has expired.
    ChatNotFoundError: the chat is not in this live session.
    RepositoryOperationError: SQLite failed, or the file cannot be opened.
    Catch RepositoryError to handle every failure at once.

Thread safety:
    One SqliteChatRepository can be shared by every thread on the
    free-threaded Python 3.14t build: it holds only immutable settings and
    the sweeper, and every call uses its own connection.

Example:
    with SqliteChatRepository(**config.repository.model_dump()) as repository:
        session = repository.create_session()
        chat = repository.create_chat(session.session_id)
        repository.add_messages(
            session.session_id,
            chat.chat_id,
            [NewMessage(role="user", content="Hi"), NewMessage(role="assistant", content="Hello!")],
        )
"""

from .chat_repository import ChatRepository
from .dto import Chat, ChatSummary, MessageRole, NewMessage, Session, StoredMessage
from .exceptions import (
    ChatNotFoundError,
    InvalidRepositoryArgumentError,
    InvalidRepositorySettingError,
    RepositoryError,
    RepositoryOperationError,
    SessionNotFoundError,
)
from .sqlite_chat_repository import SqliteChatRepository

__all__ = [
    "ChatRepository",
    "SqliteChatRepository",
    "Session",
    "ChatSummary",
    "Chat",
    "StoredMessage",
    "NewMessage",
    "MessageRole",
    "RepositoryError",
    "InvalidRepositorySettingError",
    "InvalidRepositoryArgumentError",
    "SessionNotFoundError",
    "ChatNotFoundError",
    "RepositoryOperationError",
]
