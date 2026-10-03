import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import timedelta
from functools import partial
from pathlib import Path

import pytest
from pydantic import ValidationError

import main.package.repository.sqlite_chat_repository as repository_module
from main.package.repository import (
    Chat,
    ChatNotFoundError,
    ChatOrigin,
    ChatRepository,
    ChatSummary,
    InvalidRepositoryArgumentError,
    InvalidRepositorySettingError,
    NewMessage,
    RepositoryError,
    RepositoryOperationError,
    Session,
    SessionNotFoundError,
    SqliteChatRepository,
)
from tests.support import ConcurrentRunner, wait_until

SETTINGS = {
    "session_ttl": timedelta(hours=12),
    "sweep_interval": timedelta(minutes=20),
    "busy_timeout": timedelta(seconds=5),
}
USER = NewMessage(role="user", content="What is his rating?")
ASSISTANT = NewMessage(role="assistant", content="It is 1832.")


class FailingDelete:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0

    def __call__(self) -> int:
        with self._lock:
            self.calls += 1
        raise RuntimeError("injected sweep failure")

    def called_twice(self) -> bool:
        return self.calls >= 2


def _repository(path: Path, **overrides: object) -> SqliteChatRepository:
    return SqliteChatRepository(database_path=path, **(SETTINGS | overrides))


def _count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _session_is_gone(path: Path, session_id: str) -> bool:
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?", (session_id,)).fetchone()[0] == 0


def _own_session_workload(repository: SqliteChatRepository, count: int) -> int:
    session = repository.create_session()
    chat = repository.create_chat(session.session_id)
    for index in range(count):
        repository.add_messages(session.session_id, chat.chat_id, [NewMessage(role="user", content=f"m{index}")])
    return len(repository.get_chat(session.session_id, chat.chat_id).messages)


def _append_many(repository: SqliteChatRepository, session_id: str, chat_id: str, count: int) -> int:
    for index in range(count):
        repository.add_messages(session_id, chat_id, [USER, NewMessage(role="assistant", content=f"a{index}")])
    return count


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "data" / "chats.sqlite3"


@pytest.fixture
def repository(database: Path) -> Iterator[SqliteChatRepository]:
    instance = _repository(database)
    yield instance
    instance.close()


@pytest.fixture
def session(repository: SqliteChatRepository) -> Session:
    return repository.create_session()


@pytest.fixture
def chat(repository: SqliteChatRepository, session: Session) -> ChatSummary:
    return repository.create_chat(session.session_id, "Ratings")


def test_implements_the_interface(repository: SqliteChatRepository) -> None:
    assert isinstance(repository, ChatRepository)


def test_creates_the_database_file_and_folder(repository: SqliteChatRepository, database: Path) -> None:
    assert database.is_file()
    assert repository.database_path == database


def test_schema_is_versioned_and_strict(repository: SqliteChatRepository, database: Path) -> None:
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"sessions", "chats", "messages"} <= tables


def test_create_session_returns_uuid7_with_ttl(repository: SqliteChatRepository) -> None:
    session = repository.create_session()

    assert uuid.UUID(session.session_id).version == 7
    assert session.expires_at - session.created_at == timedelta(hours=12)
    assert session.created_at.tzinfo is not None


def test_sessions_are_unique_and_time_ordered(repository: SqliteChatRepository) -> None:
    ids = [repository.create_session().session_id for _ in range(50)]

    assert len(set(ids)) == 50
    assert ids == sorted(ids)


def test_get_session_returns_the_stored_session(repository: SqliteChatRepository, session: Session) -> None:
    assert repository.get_session(session.session_id) == session
    assert repository.get_session(session.session_id.upper()) == session


def test_unknown_session_raises(repository: SqliteChatRepository) -> None:
    with pytest.raises(SessionNotFoundError):
        repository.get_session(str(uuid.uuid7()))


def test_expired_session_is_hidden_before_any_sweep(database: Path) -> None:
    with _repository(database, session_ttl=timedelta(milliseconds=50)) as repository:
        session = repository.create_session()
        chat = repository.create_chat(session.session_id)
        time.sleep(0.1)

        with pytest.raises(SessionNotFoundError):
            repository.get_session(session.session_id)
        with pytest.raises(SessionNotFoundError):
            repository.list_chats(session.session_id)
        with pytest.raises(SessionNotFoundError):
            repository.create_chat(session.session_id)
        with pytest.raises(ChatNotFoundError):
            repository.get_chat(session.session_id, chat.chat_id)
        with pytest.raises(ChatNotFoundError):
            repository.add_messages(session.session_id, chat.chat_id, [USER])

    assert _count(database, "sessions") == 1


def test_create_chat_with_default_and_trimmed_titles(repository: SqliteChatRepository, session: Session) -> None:
    default = repository.create_chat(session.session_id)
    named = repository.create_chat(session.session_id, "  Ratings  ")

    assert default.title == "New chat"
    assert named.title == "Ratings"
    assert uuid.UUID(named.chat_id).version == 7
    assert named.session_id == session.session_id
    assert named.created_at == named.updated_at


@pytest.mark.parametrize("title", ["", "   ", "x" * 201, None, 5])
def test_invalid_titles_are_rejected(repository: SqliteChatRepository, session: Session, title: object) -> None:
    with pytest.raises(InvalidRepositoryArgumentError):
        repository.create_chat(session.session_id, title)


def test_title_of_200_characters_is_accepted(repository: SqliteChatRepository, session: Session) -> None:
    assert len(repository.create_chat(session.session_id, "x" * 200).title) == 200


def test_list_chats_newest_updated_first(repository: SqliteChatRepository, session: Session) -> None:
    first = repository.create_chat(session.session_id, "first")
    second = repository.create_chat(session.session_id, "second")
    repository.add_messages(session.session_id, first.chat_id, [USER])

    assert [chat.title for chat in repository.list_chats(session.session_id)] == ["first", "second"]
    assert second.chat_id in {chat.chat_id for chat in repository.list_chats(session.session_id)}


def test_list_chats_of_a_new_session_is_empty(repository: SqliteChatRepository, session: Session) -> None:
    assert repository.list_chats(session.session_id) == ()


def test_get_chat_returns_messages_in_order(repository: SqliteChatRepository, session: Session, chat: ChatSummary) -> None:
    repository.add_messages(session.session_id, chat.chat_id, [USER, ASSISTANT])
    repository.add_messages(session.session_id, chat.chat_id, [NewMessage(role="user", content="And GitHub?")])
    stored = repository.get_chat(session.session_id, chat.chat_id)

    assert isinstance(stored, Chat)
    assert [(message.role, message.content) for message in stored.messages] == [
        ("user", "What is his rating?"),
        ("assistant", "It is 1832."),
        ("user", "And GitHub?"),
    ]
    assert [message.message_id for message in stored.messages] == sorted(message.message_id for message in stored.messages)


def test_add_messages_bumps_updated_at(repository: SqliteChatRepository, session: Session, chat: ChatSummary) -> None:
    time.sleep(0.002)
    updated = repository.add_messages(session.session_id, chat.chat_id, [USER])

    assert updated.updated_at > chat.updated_at
    assert updated.created_at == chat.created_at


def test_add_messages_is_atomic(repository: SqliteChatRepository, session: Session, chat: ChatSummary, database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER fail_on_boom BEFORE INSERT ON messages WHEN NEW.content = 'boom' "
            "BEGIN SELECT RAISE(ABORT, 'boom rejected'); END"
        )

    with pytest.raises(RepositoryOperationError) as error:
        repository.add_messages(session.session_id, chat.chat_id, [USER, NewMessage(role="assistant", content="boom")])

    assert isinstance(error.value.__cause__, sqlite3.Error)
    assert repository.get_chat(session.session_id, chat.chat_id).messages == ()
    assert repository.get_chat(session.session_id, chat.chat_id).updated_at == chat.updated_at


@pytest.mark.parametrize("messages", [[], (), "hello", None, [{"role": "user", "content": "x"}], [USER, "text"]])
def test_invalid_message_lists_are_rejected(repository: SqliteChatRepository, session: Session, chat: ChatSummary, messages: object) -> None:
    with pytest.raises(InvalidRepositoryArgumentError):
        repository.add_messages(session.session_id, chat.chat_id, messages)


@pytest.mark.parametrize("fields", [{"role": "system", "content": "x"}, {"role": "user", "content": ""}, {"role": "user", "content": "  "}])
def test_invalid_new_messages_are_rejected(fields: dict) -> None:
    with pytest.raises(ValidationError):
        NewMessage(**fields)


def test_rename_chat(repository: SqliteChatRepository, session: Session, chat: ChatSummary) -> None:
    time.sleep(0.002)
    renamed = repository.rename_chat(session.session_id, chat.chat_id, "  Codeforces  ")

    assert renamed.title == "Codeforces"
    assert renamed.updated_at > chat.updated_at
    assert repository.get_chat(session.session_id, chat.chat_id).title == "Codeforces"


def test_delete_chat_removes_it_and_its_messages(repository: SqliteChatRepository, session: Session, chat: ChatSummary, database: Path) -> None:
    repository.add_messages(session.session_id, chat.chat_id, [USER, ASSISTANT])
    repository.delete_chat(session.session_id, chat.chat_id)

    with pytest.raises(ChatNotFoundError):
        repository.get_chat(session.session_id, chat.chat_id)
    assert _count(database, "messages") == 0


@pytest.mark.parametrize("operation", ["get", "rename", "add", "delete"])
def test_other_sessions_cannot_touch_a_chat(repository: SqliteChatRepository, session: Session, chat: ChatSummary, operation: str) -> None:
    repository.add_messages(session.session_id, chat.chat_id, [USER])
    intruder = repository.create_session().session_id
    calls = {
        "get": partial(repository.get_chat, intruder, chat.chat_id),
        "rename": partial(repository.rename_chat, intruder, chat.chat_id, "hijacked"),
        "add": partial(repository.add_messages, intruder, chat.chat_id, [ASSISTANT]),
        "delete": partial(repository.delete_chat, intruder, chat.chat_id),
    }

    with pytest.raises(ChatNotFoundError):
        calls[operation]()

    untouched = repository.get_chat(session.session_id, chat.chat_id)
    assert untouched.title == "Ratings"
    assert len(untouched.messages) == 1
    assert repository.list_chats(intruder) == ()


def test_unknown_chat_raises(repository: SqliteChatRepository, session: Session) -> None:
    with pytest.raises(ChatNotFoundError):
        repository.get_chat(session.session_id, str(uuid.uuid7()))


@pytest.mark.parametrize("bad_id", ["", "not-a-uuid", str(uuid.uuid4()), None, 7, "01a0f8ec-157d-7565-abbb"])
def test_ids_must_be_uuid7(repository: SqliteChatRepository, session: Session, bad_id: object) -> None:
    with pytest.raises(InvalidRepositoryArgumentError):
        repository.get_session(bad_id)
    with pytest.raises(InvalidRepositoryArgumentError):
        repository.get_chat(session.session_id, bad_id)


def test_delete_expired_sessions_removes_only_expired_rows(database: Path) -> None:
    with _repository(database, session_ttl=timedelta(milliseconds=80)) as short:
        expired = short.create_session()
        chat = short.create_chat(expired.session_id)
        short.add_messages(expired.session_id, chat.chat_id, [USER, ASSISTANT])
    time.sleep(0.12)

    with _repository(database) as repository:
        live = repository.create_session()
        live_chat = repository.create_chat(live.session_id)
        repository.add_messages(live.session_id, live_chat.chat_id, [USER])

        assert repository.delete_expired_sessions() == 1
        assert repository.delete_expired_sessions() == 0
        assert len(repository.get_chat(live.session_id, live_chat.chat_id).messages) == 1

    assert (_count(database, "sessions"), _count(database, "chats"), _count(database, "messages")) == (1, 1, 1)


def test_sweeper_deletes_expired_sessions_by_itself(database: Path) -> None:
    with _repository(database, session_ttl=timedelta(milliseconds=30), sweep_interval=timedelta(milliseconds=30)) as repository:
        session = repository.create_session()
        repository.create_chat(session.session_id)

        assert wait_until(partial(_session_is_gone, database, session.session_id))

    assert _count(database, "chats") == 0


def test_sweeper_survives_and_logs_errors(database: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    failing = FailingDelete()
    with _repository(database, sweep_interval=timedelta(milliseconds=20)) as repository:
        monkeypatch.setattr(repository, "delete_expired_sessions", failing)
        with caplog.at_level(logging.ERROR):
            assert wait_until(failing.called_twice)
        assert repository._sweeper.is_alive()

    assert "Failed to delete expired sessions" in caplog.text


def test_close_stops_the_sweeper_and_is_safe_twice(database: Path) -> None:
    repository = _repository(database)
    repository.close()
    repository.close()

    assert not repository._sweeper.is_alive()


def test_data_survives_reopening_the_file(database: Path) -> None:
    with _repository(database) as first:
        session = first.create_session()
        chat = first.create_chat(session.session_id, "Kept")
        first.add_messages(session.session_id, chat.chat_id, [USER, ASSISTANT])

    with _repository(database) as second:
        stored = second.get_chat(session.session_id, chat.chat_id)

    assert stored.title == "Kept"
    assert len(stored.messages) == 2


_VERSION_ONE_SCHEMA = """
CREATE TABLE sessions (session_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL) STRICT;
CREATE TABLE chats (
    chat_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions (session_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
) STRICT;
PRAGMA user_version = 1;
"""


def _version_one_database(database: Path, session_id: str, chat_id: str) -> None:
    database.parent.mkdir(parents=True)
    far_future = 2**62
    with sqlite3.connect(database) as connection:
        connection.executescript(_VERSION_ONE_SCHEMA)
        connection.execute("INSERT INTO sessions VALUES (?, 1, ?)", (session_id, far_future))
        connection.execute("INSERT INTO chats VALUES (?, ?, 'Old chat', 1, 1)", (chat_id, session_id))


def test_create_chat_records_its_origin(repository: SqliteChatRepository, session: Session) -> None:
    default = repository.create_chat(session.session_id)
    cli = repository.create_chat(session.session_id, "Terminal", ChatOrigin.CLI)

    assert default.origin is ChatOrigin.CHAT
    assert cli.origin is ChatOrigin.CLI
    assert [chat.origin for chat in repository.list_chats(session.session_id)] == [ChatOrigin.CLI, ChatOrigin.CHAT]
    assert repository.get_chat(session.session_id, cli.chat_id).origin is ChatOrigin.CLI
    assert repository.rename_chat(session.session_id, cli.chat_id, "Renamed").origin is ChatOrigin.CLI


@pytest.mark.parametrize("origin", ["cli", None, 1])
def test_create_chat_rejects_a_non_enum_origin(repository: SqliteChatRepository, session: Session, origin: object) -> None:
    with pytest.raises(InvalidRepositoryArgumentError, match="origin"):
        repository.create_chat(session.session_id, "Terminal", origin)


def test_origin_column_rejects_unknown_values(repository: SqliteChatRepository, chat: ChatSummary, database: Path) -> None:
    with sqlite3.connect(database) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE chats SET origin = 'web' WHERE chat_id = ?", (chat.chat_id,))


def test_version_one_database_is_upgraded_in_place(database: Path) -> None:
    session_id, chat_id = str(uuid.uuid7()), str(uuid.uuid7())
    _version_one_database(database, session_id, chat_id)

    for _ in range(2):
        with _repository(database) as upgraded:
            old = upgraded.get_chat(session_id, chat_id)
            new = upgraded.create_chat(session_id, "Terminal", ChatOrigin.CLI)
            assert (old.title, old.origin) == ("Old chat", ChatOrigin.CHAT)
            assert new.origin is ChatOrigin.CLI

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_newer_schema_version_is_refused(database: Path) -> None:
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(RepositoryOperationError, match="newer"):
        _repository(database)


def test_unopenable_path_raises(tmp_path: Path) -> None:
    folder = tmp_path / "is_a_directory"
    folder.mkdir()

    with pytest.raises(RepositoryOperationError) as error:
        _repository(folder)

    assert isinstance(error.value.__cause__, sqlite3.Error)


def test_unwritable_parent_raises(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")

    with pytest.raises(RepositoryOperationError) as error:
        _repository(blocker / "db.sqlite3")

    assert isinstance(error.value.__cause__, OSError)


def test_corrupt_database_raises_on_initialise(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"this is not a sqlite database at all" * 200)

    with pytest.raises(RepositoryOperationError) as error:
        _repository(path)

    assert isinstance(error.value.__cause__, sqlite3.Error)


def test_connection_failures_are_wrapped(repository: SqliteChatRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repository, "_connect", partial(_raise_operational_error, "disk gone"))

    with pytest.raises(RepositoryOperationError) as error:
        repository.create_session()

    assert isinstance(error.value.__cause__, sqlite3.OperationalError)


def _raise_operational_error(message: str) -> None:
    raise sqlite3.OperationalError(message)


def test_failed_rollback_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        repository_module.SqliteChatRepository._rollback(BrokenRollback())

    assert "Failed to roll back" in caplog.text


class BrokenRollback:
    in_transaction = True

    def execute(self, sql: str) -> None:
        raise sqlite3.OperationalError("rollback failed")


def test_rollback_without_open_transaction_does_nothing() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)

    repository_module.SqliteChatRepository._rollback(connection)

    connection.close()


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_path": ""},
        {"database_path": None},
        {"database_path": 5},
        {"session_ttl": timedelta(0)},
        {"session_ttl": 43200},
        {"sweep_interval": timedelta(seconds=-1)},
        {"busy_timeout": None},
    ],
)
def test_invalid_settings_are_rejected(tmp_path: Path, overrides: dict) -> None:
    settings = {"database_path": tmp_path / "db.sqlite3"} | SETTINGS | overrides

    with pytest.raises(InvalidRepositorySettingError):
        SqliteChatRepository(**settings)


def test_settings_are_keyword_only(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        SqliteChatRepository(tmp_path / "db.sqlite3", *SETTINGS.values())


def test_parallel_sessions_each_keep_their_messages(repository: SqliteChatRepository, database: Path) -> None:
    runner = ConcurrentRunner(partial(_own_session_workload, repository, 20)).run()

    assert runner.errors == []
    assert runner.results == [20] * 16
    assert (_count(database, "sessions"), _count(database, "messages")) == (16, 320)


def test_parallel_appends_to_one_chat_are_all_stored(repository: SqliteChatRepository, session: Session, chat: ChatSummary) -> None:
    runner = ConcurrentRunner(partial(_append_many, repository, session.session_id, chat.chat_id, 10)).run()
    messages = repository.get_chat(session.session_id, chat.chat_id).messages
    ids = [message.message_id for message in messages]

    assert runner.errors == []
    assert len(messages) == 16 * 10 * 2
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


@pytest.mark.parametrize(
    "error_type",
    [InvalidRepositorySettingError, InvalidRepositoryArgumentError, SessionNotFoundError, ChatNotFoundError, RepositoryOperationError],
)
def test_errors_share_the_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, RepositoryError)


def test_schema_that_fails_to_apply_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    broken_schema = tmp_path / "broken.sql"
    broken_schema.write_text("CREATE TABLE oops (;")
    monkeypatch.setattr(repository_module, "_SCHEMA_PATH", broken_schema)

    with pytest.raises(RepositoryOperationError, match="initialise") as error:
        _repository(tmp_path / "db.sqlite3")

    assert isinstance(error.value.__cause__, sqlite3.Error)


def test_schema_file_is_embedded_in_the_package() -> None:
    assert repository_module._SCHEMA_PATH.read_text().count("CREATE TABLE IF NOT EXISTS") == 3
