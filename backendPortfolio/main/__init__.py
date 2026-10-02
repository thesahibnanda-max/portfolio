"""
Source root of the backend portfolio service.

Layout:
    main/app.py: application entry point (not wired up yet).
    main/config: AppConfig, loaded from main/config/config.yaml.
    main/package/ttl_key_value_store: key-value store with expiring entries,
    behind an interface and a factory.
    main/package/repository: SQLite storage of anonymous sessions (UUIDv7
    ids, deleted session_ttl after creation) and their chats and messages.
    main/package/json_extract: pulls validated JSON out of free-form text.
    main/package/ai/common, main/package/ai/orchestrator,
    main/package/ai/worker: the two-stage AI that routes a question and
    answers it, with prompts embedded as .md files.
    main/package/static: the owner's profile and personality JSON, loaded
    once and served from memory.
    main/package/clients/leetcode, main/package/clients/github,
    main/package/clients/codeforces, main/package/clients/groq: HTTP clients
    for those APIs.
    Each package explains itself in its own __init__.py.

Imports:
    backendPortfolio/ is the project root, so every import starts with
    main, for example from main.config import AppConfig. Run the app and
    the tests from backendPortfolio/.

Tests:
    They live in backendPortfolio/tests and mirror this layout; see
    tests/__init__.py.

Code rules:
    No comments in any file; each package's explanation lives only in its
    __init__.py docstring.
    No functions defined inside functions; helpers are private methods or
    module-level private functions.
    Every setting is a constructor argument backed by config.yaml.
    Each package raises its own exceptions from its exceptions.py.

Runtime:
    Python 3.14t (free-threaded). Every dependency is pure Python or ships
    a cp314t wheel, so the GIL stays disabled; shared objects are either
    immutable or guarded by locks.
"""
