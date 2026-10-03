"""
Typed, validated and immutable application config loaded from config.yaml.

Exports:
    AppConfig: the root config, loaded with AppConfig.load().
    load_local_env, LOCAL_ENV_FILE: optional .env loading for local
    development, described under Local development.
    ServerConfig (with CorsConfig), TTLKeyValueStoreConfig, HttpClientConfig, LeetcodeConfig,
    CodeforcesConfig, GitHubConfig, GroqConfig, LLMConfig (with
    LLMModelConfig), OrchestratorConfig, RepositoryConfig, DataServiceConfig
    (with PlatformAccountConfig), ChatConfig, ContextConfig, RateLimitConfig
    (with RateLimitRuleConfig): the sections of AppConfig.
    ConfigError and its subclasses: the errors described under Errors.

Usage:
    config = AppConfig.load()
    config.repository.session_ttl == timedelta(hours=12)
    config.ttl_key_value_store.sweep_intervals[TTLKeyValueStoreImpl.IN_MEMORY]

    AppConfig.load(path) reads another file. With no path it reads the
    config.yaml next to this package, so it works from any working directory.

Sections and fields (defaults are written in config.yaml):
    app: the HTTP server, read by main.package.handler and gunicorn.conf.py.
        host: non-empty bind address. Default "0.0.0.0".
        port: int from 1 to 65535. Default 8080.
        workers: int of at least 1, gunicorn worker processes. Default 1:
        the rate limiter, data cache and Groq key rotation live in memory,
        so more workers would each keep their own counters. One process
        already uses every core, because sync handlers run in parallel on
        the free-threaded build.
        thread_pool_size: int of at least 1, the AnyIO threadpool size the
        sync handlers run on. Default 64.
        timeout: Duration gunicorn lets a request run, long enough for a
        streamed answer. Default "180s".
        graceful_timeout: Duration to finish in-flight requests on shutdown.
        Default "30s".
        keepalive: Duration an idle keep-alive connection stays open.
        Default "5s".
        max_body_bytes: int of at least 1, the largest request body.
        Default 262144 (256 KiB).
        trust_forwarded_for: bool, read the client IP from the first
        X-Forwarded-For entry. Default true, because the server runs behind
        Caddy, which overwrites the header; set false when exposed directly.
        cors: allow_origins (non-empty list, "*" for any) and max_age (a
        Duration of whole seconds that browsers cache a preflight). Defaults
        ["*"] and "1h".
    ttl_key_value_store:
        sweep_intervals: map from TTLKeyValueStoreImpl value to Duration.
        Default {in_memory: "20m"}.
    http_client: timeouts shared by the LeetCode, Codeforces and GitHub
    clients, passed to each client's constructor under the same names.
        connect_timeout: Duration. Default "10s".
        read_timeout: Duration. Default "60s".
        write_timeout: Duration. Default "60s".
        pool_timeout: Duration to wait for a free pooled connection.
        Default "10s".
    leetcode:
        base_url: URL. Default "https://leetcode.com".
    codeforces:
        base_url: URL. Default "https://codeforces.com".
    github:
        base_url: URL. Default "https://api.github.com".
        api_version: non-empty X-GitHub-Api-Version value. Default
        "2022-11-28".
        per_page: int from 1 to 100, the page size for list calls.
        Default 100.

    groq:
        base_url: URL. Default "https://api.groq.com".
        api_keys: read from the GROQ_API_KEYS environment variable, which has
        no default. It holds one or more keys separated by commas, for
        example "gsk_a,gsk_b"; spaces around each key and empty entries are
        dropped, and at least one key must remain. Each key is a SecretStr,
        so it never shows in a repr, log or error message; pass them to
        GroqClient with [key.get_secret_value() for key in config.groq.api_keys].

    llm: the Groq models and sampling used by main.package.ai.
        models: non-empty list, unique by model_id. Each entry has model_id,
        weight (int of at least 1; the chance of picking it is its weight
        over the total), an optional reasoning_effort sent to Groq, and
        supports_strict_json_schema (default false), true only for models
        on which Groq can enforce a strict JSON Schema.
        Defaults, both Groq production models with strict JSON Schema:
        openai/gpt-oss-20b 60 and openai/gpt-oss-120b 40, each with
        reasoning_effort medium. gpt-oss models accept reasoning_effort low,
        medium or high only.
        temperature_range: [min, max] within 0..2 with min <= max. Default
        [0.8, 1.4].
        top_p_range: [min, max] within 0..1 with min <= max. Default
        [0.9, 1.0].
        max_completion_tokens: int of at least 1. Default 2048.
        Build the selector with
        ModelSelector(models=[LLMModel(**m.model_dump()) for m in llm.models],
        temperature_range=llm.temperature_range, top_p_range=llm.top_p_range).
    orchestrator: fixed sampling for routing calls.
        temperature: 0..2. Default 0.0.
        top_p: 0..1. Default 1.0.
    repository: the SQLite store of anonymous sessions and their chats.
        database_path: non-empty path of the SQLite file, relative to the
        working directory unless absolute. Default
        "data/backend_portfolio.sqlite3"; the folder is created if needed.
        session_ttl: Duration a session and all its chats live, counted from
        when the session is created. Default "12h". This is the single source
        of the session lifetime: pass it to the repository and to anything
        that tells the client when its session ends.
        sweep_interval: Duration between background deletions of expired
        sessions. Default "20m". Expired sessions are already hidden from
        every read, so this only controls how soon their rows are removed.
        busy_timeout: Duration SQLite waits for another writer to finish
        before failing. Default "5s".

    data_service: main.package.service.data.DataService settings.
        cache_impl: which TTLKeyValueStoreImpl caches the details, by value.
        Default in_memory; a future redis implementation is selected here.
        max_workers: int of at least 1, the thread pool size. Default 8.
        leetcode_accounts, codeforces_accounts, github_accounts: non-empty
        lists of {username, cache_ttl} with unique usernames, in display
        order; the first LeetCode account is the primary one. cache_ttl is a
        Duration. Defaults: LeetCode imsahibnanda 1h; Codeforces
        shisukenohara 80m; GitHub thesahibnanda-max 45m and thesahibnanda
        120m.
        profile_photo_links: list of photo URLs.
        leetcode_profile_url_format, codeforces_profile_url_format:
        str.format templates using exactly {base_url} and {username}.
        Defaults "{base_url}/u/{username}/" and "{base_url}/profile/{username}".
        Build the service's accounts with
        [PlatformAccount(**account.model_dump()) for account in config.data_service.github_accounts].

    chat: main.package.service.chat.ChatService limits and fallbacks.
        max_message_chars: int of at least 1, the longest visitor message
        accepted after trimming. Default 4000.
        max_history_messages: int of at least 1, how many earlier messages
        the AI sees. Default 20.
        max_history_chars: int of at least 1, the character budget for those
        messages (the oldest are dropped first). Default 12000.
        max_messages_per_chat: int of at least 2; a chat that would grow past
        it is full. Default 200.
        fallback_messages: one non-blank reply for each QueryScope other than
        IN_SCOPE (NOT_RELATED_TO_PORTFOLIO, PROMPT_INJECTION, UNSAFE), sent
        instead of an AI answer when the orchestrator flags a message.
    context: main.package.service.context settings.
        max_workers: int of at least 1, the aggregator's pool size. Default 5.
        max_github_repositories: top repositories by stars shown per GitHub
        account. Default 5.
        max_rating_changes: most recent Codeforces contests shown per handle.
        Default 5.
    rate_limit: main.package.ratelimiter.RateLimiter settings.
        storage_uri: non-empty limits storage URI. Default "memory://"; a
        shared "redis://host:6379" is a config change once redis is
        installed.
        key_prefix: non-empty namespace of every counter key. Default
        "rate_limit".
        rules: non-empty map from api name ([a-z0-9_]+) to exactly one
        {limit, window} per RateLimitScope value (ip, session, global).
        limit is an int of at least 1; window is a Duration of whole
        seconds. Defaults, per "1m" unless noted: create_session 10/10/300,
        chat_read 30/30/900, chat_write 30/30/900, chat_message 5/5/60
        (send and stream share it, since both call Groq), details
        30/30/900, and contact 3 per "1h" per IP and per session with 50
        per "24h" overall. The per-visitor limits match the Java service;
        the global budgets are larger so one visitor cannot block everyone.
        Build the limiter with
        RateLimiter(storage_uri=rl.storage_uri, key_prefix=rl.key_prefix,
        rules={api: {scope: RateLimitRule(**rule.model_dump()) for scope, rule in rules.items()} for api, rules in rl.rules.items()}).

    mail: main.package.mail.Mailer settings.
        recipient_mail: the one address every mail is sent to, read from
        the RECIPIENT_MAIL environment variable (no default).
        sender_name: non-blank display name on From. Default
        "Sahib Nanda · Portfolio".
        timeout: Duration for connecting and each SMTP command. Default
        "15s".
        accounts: non-empty list, unique by username, tried in a random
        order per mail with failover. Each entry has host, port (1 to 65535), security
        (starttls or ssl), username (the sending address) and password (a
        SecretStr). Default: one smtp.gmail.com:587 STARTTLS account whose
        username and password come from the MAIL_ACCOUNT_1_USERNAME and
        MAIL_ACCOUNT_1_PASSWORD environment variables (no defaults; for
        Gmail use an app password). Add accounts as further entries with
        their own variables, such as MAIL_ACCOUNT_2_USERNAME.

    contact: main.package.service.contact.ContactService settings.
        subject_prefix: non-blank text put before the visitor's subject.
        Default "[Portfolio]".
        max_subject_chars: int of at least 1. Default 150.
        max_message_chars: int of at least 1. Default 5000.
        check_email_deliverability: bool, whether the visitor's email domain
        must pass a DNS mail check (MX, or A/AAAA fallback). Default true; a
        DNS timeout still lets the address through.
        email_dns_timeout: Duration for that DNS lookup. Default "3s".
        The contact endpoint's rate limit is rate_limit.rules.contact
        (defaults: 3 per hour per IP and per session, 50 per day overall).

URL:
    An http or https URL with a host and no query or fragment, for example
    "https://api.github.com". A trailing slash is allowed; the clients
    remove it.

Duration:
    A string parsed by pytimeparse2, such as "90s", "15m", "12h", "2d",
    "1h30m" or "1.5h", or a plain number of seconds. It must be positive.

Environment variables:
    Only secrets come from the environment: GROQ_API_KEYS, RECIPIENT_MAIL and
    the MAIL_ACCOUNT_<n>_USERNAME / MAIL_ACCOUNT_<n>_PASSWORD pairs. They have
    no defaults, so a missing one fails startup. Everything else has a
    default in the YAML. Write them as "${NAME}" in double quotes: envyaml
    replaces them in the file's text before the YAML is parsed, so quoting
    keeps a value from changing the YAML structure. envyaml also accepts
    $NAME and "${NAME|default}". Setting ENVYAML_STRICT_DISABLE turns off the
    missing-variable check; do not set it in production.
    AppConfig.load() reads only the real process environment; it never reads
    a .env file itself.

Local development (.env):
    load_local_env(path=LOCAL_ENV_FILE) -> bool loads backendPortfolio/.env
    (the path is fixed, not relative to the working directory) into the
    process environment with python-dotenv, and returns whether a file was
    loaded. It never overrides a variable that is already set, so exported
    variables, deployment secrets and test fixtures always win. A missing
    file is a no-op, which is how production runs: the platform sets real
    environment variables and no .env exists. main.app.create_app() and
    gunicorn.conf.py call it before AppConfig.load(). The file is
    gitignored, and blank values in it are treated as set, so only list the
    variables you mean to provide.

Errors (all in exceptions.py, all subclasses of ConfigError):
    ConfigFileNotFoundError: the config file does not exist.
    MissingEnvironmentVariableError: a ${NAME} in the file is not set.
    InvalidConfigError: the file is not valid YAML, or a value fails
    validation (wrong type, out of range, bad duration, unknown impl, bad
    URL, missing or unknown field). The message
    lists every failing field by path, without input values, so secrets are
    never printed. The original error is chained as __cause__.
    Catch ConfigError to handle every config failure at once.
    Unknown top-level sections are ignored, because envyaml mixes the
    environment into the same mapping; unknown fields inside a section are
    rejected.

Thread safety:
    Every model is frozen, so an AppConfig can be shared across threads
    without locks on the free-threaded Python 3.14t build. load() keeps no
    shared state and can run from several threads at once.

Dependencies (all keep the GIL disabled on Python 3.14t):
    envyaml (pure Python) for ${NAME} substitution and loading,
    PyYAML 6.0.3 (cp314t wheel) underneath it,
    pydantic v2 with pydantic-core (cp314t wheel) for validation,
    pytimeparse2 (pure Python) for durations.
"""

from .app_config import (
    AppConfig,
    ChatConfig,
    CodeforcesConfig,
    ContactConfig,
    CorsConfig,
    ContextConfig,
    DataServiceConfig,
    GitHubConfig,
    GroqConfig,
    HttpClientConfig,
    LLMConfig,
    LLMModelConfig,
    LeetcodeConfig,
    MailConfig,
    OrchestratorConfig,
    PlatformAccountConfig,
    RateLimitConfig,
    RateLimitRuleConfig,
    RepositoryConfig,
    ServerConfig,
    SmtpAccountConfig,
    TTLKeyValueStoreConfig,
)
from .environment import LOCAL_ENV_FILE, load_local_env
from .exceptions import (
    ConfigError,
    ConfigFileNotFoundError,
    InvalidConfigError,
    MissingEnvironmentVariableError,
)

__all__ = [
    "AppConfig",
    "ServerConfig",
    "CorsConfig",
    "TTLKeyValueStoreConfig",
    "HttpClientConfig",
    "LeetcodeConfig",
    "CodeforcesConfig",
    "GitHubConfig",
    "GroqConfig",
    "LLMConfig",
    "LLMModelConfig",
    "OrchestratorConfig",
    "RepositoryConfig",
    "DataServiceConfig",
    "ChatConfig",
    "ContextConfig",
    "PlatformAccountConfig",
    "RateLimitConfig",
    "RateLimitRuleConfig",
    "MailConfig",
    "ContactConfig",
    "SmtpAccountConfig",
    "load_local_env",
    "LOCAL_ENV_FILE",
    "ConfigError",
    "ConfigFileNotFoundError",
    "MissingEnvironmentVariableError",
    "InvalidConfigError",
]
