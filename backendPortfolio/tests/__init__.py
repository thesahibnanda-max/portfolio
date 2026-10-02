"""
Test suite for the backend portfolio service.

Running (from backendPortfolio/):
    venv/bin/python -m pytest
        Runs every offline test. HTTP clients are tested against fake
        responses (httpx.MockTransport), so no network is needed.
    venv/bin/python -m pytest -m live
        Runs only the live tests, which call the real LeetCode, Codeforces and
        GitHub APIs. They are skipped by default because they need network
        access and GitHub allows 60 unauthenticated requests an hour.
    GROQ_API_KEYS="gsk_a,gsk_b" venv/bin/python -m pytest
        Also runs the real Groq tests in
        tests/main/package/clients/groq/test_groq_live.py. They check
        GROQ_API_KEYS when the module loads: if it is unset or holds no keys
        they are skipped, otherwise it is split on commas and each test uses
        one key picked at random. They do not need -m live.
    venv/bin/python -m pytest --cov=main --cov-report=term-missing
        Adds a coverage report for the main package.
    Install the test tools first with venv/bin/python -m pip install -e ".[test]".

Layout:
    tests/main mirrors backendPortfolio/main: the tests for
    main/package/repository live in tests/main/package/repository, and so on.
    Every test directory has an empty __init__.py so test files with the same
    name in different folders do not clash.
    tests/conftest.py holds shared fixtures: ttl_factory (closed after each
    test), config_env (sets a fake GROQ_API_KEYS for the test, so
    AppConfig.load works) and http_timeouts.
    tests/support.py holds shared helpers:
        ResponseSpec and RecordingTransport: a fake HTTP transport that
        records every request and answers with preset responses (JSON, text
        or raw bytes such as a Server-Sent Events body), per path or by
        default, or raises a preset transport error.
        ConcurrentRunner: starts N threads at the same moment on one callable
        and collects results and errors, for free-threading race tests.
        wait_until: polls a condition until it is true or a timeout passes.
    tests/main/test_free_threading.py imports every main module and checks
    the GIL is still disabled.

Settings:
    pyproject.toml sets testpaths to tests, puts backendPortfolio/ on the
    import path so tests import main.*, deselects the live marker by default,
    and turns unknown markers into errors.

Rules:
    The same rules as main apply: no comments, no functions defined inside
    functions (helpers are module-level functions, functools.partial or
    methods), and explanations only in __init__.py.
"""
