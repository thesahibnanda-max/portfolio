from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import main.config
from main.config import (
    AppConfig,
    ChatConfig,
    CodeforcesConfig,
    ContactConfig,
    ContextConfig,
    CorsConfig,
    ConfigError,
    DataServiceConfig,
    ConfigFileNotFoundError,
    GitHubConfig,
    GroqConfig,
    HttpClientConfig,
    LLMConfig,
    InvalidConfigError,
    LeetcodeConfig,
    MailConfig,
    MissingEnvironmentVariableError,
    OrchestratorConfig,
    PlatformAccountConfig,
    RateLimitConfig,
    RateLimitRuleConfig,
    RepositoryConfig,
    ServerConfig,
    SmtpAccountConfig,
    TTLKeyValueStoreConfig,
)
from main.package.ai.common import LLMModel, ModelSelector
from main.package.ai.orchestrator import Orchestrator, QueryScope
from main.package.ai.worker import Worker
from main.package.clients.codeforces import CodeforcesClient
from main.package.clients.github import GitHubClient
from main.package.clients.groq import GroqClient
from main.package.clients.leetcode import LeetcodeClient
from main.package.mail import Mailer, SmtpAccount, SmtpSecurity
from main.package.ratelimiter import RateLimiter, RateLimitExceededError, RateLimitRule, RateLimitScope
from main.package.repository import SqliteChatRepository
from main.package.static import StaticLoader
from main.package.ttl_key_value_store import TTLKeyValueStoreFactory, TTLKeyValueStoreImpl
from tests.conftest import (
    FAKE_MAIL_PASSWORD,
    FAKE_MAIL_PASSWORD_2,
    FAKE_MAIL_USERNAME,
    FAKE_MAIL_USERNAME_2,
    FAKE_RECIPIENT_MAIL,
)
from tests.support import ConcurrentRunner

CONFIG_YAML = Path(main.config.__file__).with_name("config.yaml").read_text()


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def _load_variant(tmp_path: Path, old: str, new: str) -> AppConfig:
    assert old in CONFIG_YAML
    return AppConfig.load(_write(tmp_path, CONFIG_YAML.replace(old, new, 1)))


def test_defaults_load_with_correct_types(config_env: str) -> None:
    config = AppConfig.load()

    assert config.app == ServerConfig(
        host="0.0.0.0",
        port=8080,
        workers=1,
        thread_pool_size=64,
        timeout=timedelta(seconds=180),
        graceful_timeout=timedelta(seconds=30),
        keepalive=timedelta(seconds=5),
        max_body_bytes=262144,
        trust_forwarded_for=True,
        cors=CorsConfig(allow_origins=("*",), max_age=timedelta(hours=1)),
    )
    assert config.ttl_key_value_store == TTLKeyValueStoreConfig(
        sweep_intervals={TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=20)}
    )
    assert config.http_client == HttpClientConfig(
        connect_timeout=timedelta(seconds=10),
        read_timeout=timedelta(seconds=60),
        write_timeout=timedelta(seconds=60),
        pool_timeout=timedelta(seconds=10),
    )
    assert config.leetcode == LeetcodeConfig(base_url="https://leetcode.com")
    assert config.codeforces == CodeforcesConfig(base_url="https://codeforces.com")
    assert config.github == GitHubConfig(base_url="https://api.github.com", api_version="2022-11-28", per_page=100)
    assert config.repository == RepositoryConfig(
        database_path="data/backend_portfolio.sqlite3",
        session_ttl=timedelta(hours=12),
        sweep_interval=timedelta(minutes=20),
        busy_timeout=timedelta(seconds=5),
    )


def test_ttl_store_impl_keys_are_the_enum(config_env: str) -> None:
    assert list(AppConfig.load().ttl_key_value_store.sweep_intervals) == [TTLKeyValueStoreImpl.IN_MEMORY]


def test_config_is_frozen(config_env: str) -> None:
    config = AppConfig.load()

    with pytest.raises(ValidationError):
        config.app.port = 1


def test_groq_keys_are_hidden_from_repr(config_env: str) -> None:
    config = AppConfig.load()

    assert all(key not in repr(config) for key in config_env.split(","))


def test_loads_from_any_working_directory(config_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = AppConfig.load()
    monkeypatch.chdir(tmp_path)

    assert AppConfig.load() == expected


def test_load_accepts_explicit_path(config_env: str, tmp_path: Path) -> None:
    assert AppConfig.load(_write(tmp_path, CONFIG_YAML)) == AppConfig.load()
    assert AppConfig.load(str(_write(tmp_path, CONFIG_YAML))) == AppConfig.load()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("900", timedelta(seconds=900)),
        ('"1h30m"', timedelta(hours=1, minutes=30)),
        ('"1.5h"', timedelta(hours=1, minutes=30)),
        ('"90s"', timedelta(seconds=90)),
        ('"2d"', timedelta(days=2)),
        ("0.5", timedelta(milliseconds=500)),
    ],
)
def test_duration_formats(config_env: str, tmp_path: Path, value: str, expected: timedelta) -> None:
    config = _load_variant(tmp_path, 'session_ttl: "12h"', f"session_ttl: {value}")

    assert config.repository.session_ttl == expected


def test_trailing_slash_in_url_is_allowed(config_env: str, tmp_path: Path) -> None:
    config = _load_variant(tmp_path, '"https://leetcode.com"', '"https://leetcode.com/"')

    assert config.leetcode.base_url == "https://leetcode.com/"


def test_missing_environment_variable_raises(config_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEYS")

    with pytest.raises(MissingEnvironmentVariableError, match="GROQ_API_KEYS"):
        AppConfig.load()


def test_missing_file_raises(config_env: str, tmp_path: Path) -> None:
    with pytest.raises(ConfigFileNotFoundError) as error:
        AppConfig.load(tmp_path / "missing.yaml")

    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_broken_yaml_raises(config_env: str, tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigError, match="not valid YAML"):
        AppConfig.load(_write(tmp_path, "app: [unclosed"))


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ('session_ttl: "12h"', 'session_ttl: "soon"', "repository.session_ttl"),
        ('session_ttl: "12h"', 'session_ttl: "-5m"', "repository.session_ttl"),
        ('session_ttl: "12h"', "session_ttl: true", "repository.session_ttl"),
        ('sweep_interval: "20m"', 'sweep_interval: "0s"', "repository.sweep_interval"),
        ('busy_timeout: "5s"', 'busy_timeout: "nope"', "repository.busy_timeout"),
        ('database_path: "data/backend_portfolio.sqlite3"', 'database_path: ""', "repository.database_path"),
        ('in_memory: "20m"', 'in_memory: "0s"', "ttl_key_value_store.sweep_intervals"),
        ('in_memory: "20m"', 'redis: "20m"', "ttl_key_value_store.sweep_intervals"),
        ("port: 8080", "port: 0", "app.port"),
        ("port: 8080", "port: 70000", "app.port"),
        ('"https://leetcode.com"', '"leetcode.com"', "leetcode.base_url"),
        ('"https://codeforces.com"', '"ftp://codeforces.com"', "codeforces.base_url"),
        ('"https://api.github.com"', '"https://api.github.com?x=1"', "github.base_url"),
        ('"https://api.github.com"', '"https://"', "github.base_url"),
        ('pool_timeout: "10s"', 'pool_timeout: "0s"', "http_client.pool_timeout"),
        ("per_page: 100", "per_page: 101", "github.per_page"),
        ("per_page: 100", "per_page: 0", "github.per_page"),
        ('api_version: "2022-11-28"', 'api_version: ""', "github.api_version"),
        ("  port: 8080", "  port: 8080\n  unknown_field: x", "app.unknown_field"),
    ],
)
def test_invalid_values_raise_with_field_path(config_env, tmp_path, old: str, new: str, field: str) -> None:
    with pytest.raises(InvalidConfigError, match=field.replace(".", r"\.")) as error:
        _load_variant(tmp_path, old, new)

    assert isinstance(error.value.__cause__, ValidationError)
    assert all(key not in str(error.value) for key in config_env.split(","))


def test_missing_section_raises(config_env: str, tmp_path: Path) -> None:
    text = CONFIG_YAML.split("\ngithub:")[0]

    with pytest.raises(InvalidConfigError, match="github"):
        AppConfig.load(_write(tmp_path, text))


def test_parallel_loads_give_equal_configs(config_env: str) -> None:
    runner = ConcurrentRunner(AppConfig.load).run()

    assert runner.errors == []
    assert len(runner.results) == 16
    assert all(result == runner.results[0] for result in runner.results)


def test_every_component_can_be_built_from_config(config_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = AppConfig.load()
    timeouts = config.http_client.model_dump()
    factory = TTLKeyValueStoreFactory(config.ttl_key_value_store.sweep_intervals)
    clients = [
        LeetcodeClient(base_url=config.leetcode.base_url, **timeouts),
        CodeforcesClient(base_url=config.codeforces.base_url, **timeouts),
        GitHubClient(
            base_url=config.github.base_url,
            api_version=config.github.api_version,
            per_page=config.github.per_page,
            **timeouts,
        ),
    ]
    repository = SqliteChatRepository(**config.repository.model_dump())
    try:
        session = repository.create_session()
        assert session.expires_at - session.created_at == config.repository.session_ttl
        assert (tmp_path / config.repository.database_path).is_file()
    finally:
        repository.close()
        factory.close_all()
        for client in clients:
            client.close()


@pytest.mark.parametrize("error_type", [ConfigFileNotFoundError, MissingEnvironmentVariableError, InvalidConfigError])
def test_errors_share_the_config_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, ConfigError)


def test_repository_section_model_is_exported() -> None:
    assert RepositoryConfig.model_config["frozen"] is True



@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("gsk_one", ("gsk_one",)),
        ("gsk_one,gsk_two", ("gsk_one", "gsk_two")),
        (" gsk_one , gsk_two ,, ", ("gsk_one", "gsk_two")),
    ],
)
def test_groq_api_keys_are_split_on_commas(config_env, monkeypatch, value: str, expected: tuple) -> None:
    monkeypatch.setenv("GROQ_API_KEYS", value)
    groq = AppConfig.load().groq
    assert isinstance(groq, GroqConfig)

    assert groq.base_url == "https://api.groq.com"
    assert tuple(key.get_secret_value() for key in groq.api_keys) == expected


def test_groq_api_keys_are_hidden(config_env, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEYS", "gsk_secret_one,gsk_secret_two")
    config = AppConfig.load()

    assert "gsk_secret" not in repr(config)
    assert "gsk_secret" not in str(config.groq.model_dump())


def test_missing_groq_api_keys_raises(config_env, monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEYS")

    with pytest.raises(MissingEnvironmentVariableError, match="GROQ_API_KEYS"):
        AppConfig.load()


@pytest.mark.parametrize("value", ["", " ", ",", " , ,"])
def test_empty_groq_api_keys_raise(config_env, monkeypatch, value: str) -> None:
    monkeypatch.setenv("GROQ_API_KEYS", value)

    with pytest.raises(InvalidConfigError, match="groq.api_keys"):
        AppConfig.load()


def test_invalid_groq_base_url_raises(config_env, tmp_path) -> None:
    with pytest.raises(InvalidConfigError, match=r"groq\.base_url"):
        _load_variant(tmp_path, '"https://api.groq.com"', '"api.groq.com"')


def test_groq_config_built_directly_accepts_a_list_of_keys() -> None:
    groq = GroqConfig(base_url="https://api.groq.com", api_keys=["gsk_a", "gsk_b"])

    assert tuple(key.get_secret_value() for key in groq.api_keys) == ("gsk_a", "gsk_b")


def test_llm_and_orchestrator_defaults(config_env: str) -> None:
    config = AppConfig.load()

    assert isinstance(config.llm, LLMConfig) and isinstance(config.orchestrator, OrchestratorConfig)
    assert [
        (model.model_id, model.weight, model.reasoning_effort, model.supports_strict_json_schema)
        for model in config.llm.models
    ] == [
        ("openai/gpt-oss-20b", 60, "medium", True),
        ("openai/gpt-oss-120b", 40, "medium", True),
    ]
    assert all(not model.model_id.startswith("qwen/") for model in config.llm.models)
    assert config.llm.temperature_range == (0.8, 1.4)
    assert config.llm.top_p_range == (0.9, 1.0)
    assert config.llm.max_completion_tokens == 2048
    assert (config.orchestrator.temperature, config.orchestrator.top_p) == (0.0, 1.0)


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("      weight: 60", "      weight: 0", "llm.models"),
        ("      supports_strict_json_schema: true", "      supports_strict_json_schema: maybe", "llm.models"),
        ('    - model_id: "openai/gpt-oss-120b"', '    - model_id: "openai/gpt-oss-20b"', "llm.models"),
        ("  temperature_range: [0.8, 1.4]", "  temperature_range: [1.4, 0.8]", "llm.temperature_range"),
        ("  temperature_range: [0.8, 1.4]", "  temperature_range: [0.8, 2.4]", "llm.temperature_range"),
        ("  top_p_range: [0.9, 1.0]", "  top_p_range: [0.9, 1.5]", "llm.top_p_range"),
        ("  max_completion_tokens: 2048", "  max_completion_tokens: 0", "llm.max_completion_tokens"),
        ("  temperature: 0.0", "  temperature: 3", "orchestrator.temperature"),
        ("  top_p: 1.0", "  top_p: -1", "orchestrator.top_p"),
    ],
)
def test_invalid_llm_values_raise(config_env, tmp_path, old: str, new: str, field: str) -> None:
    with pytest.raises(InvalidConfigError, match=field.replace(".", r"\.")):
        _load_variant(tmp_path, old, new)


def test_empty_model_list_raises(config_env, tmp_path) -> None:
    start = CONFIG_YAML.index("  models:")
    end = CONFIG_YAML.index("  temperature_range:")
    text = CONFIG_YAML[:start] + "  models: []\n" + CONFIG_YAML[end:]

    with pytest.raises(InvalidConfigError, match=r"llm\.models"):
        AppConfig.load(_write(tmp_path, text))


def test_ai_components_build_from_config(config_env: str) -> None:
    config = AppConfig.load()
    selector = ModelSelector(
        models=[LLMModel(**model.model_dump()) for model in config.llm.models],
        temperature_range=config.llm.temperature_range,
        top_p_range=config.llm.top_p_range,
    )
    with GroqClient(
        base_url=config.groq.base_url,
        api_keys=[key.get_secret_value() for key in config.groq.api_keys],
        **config.http_client.model_dump(),
    ) as groq:
        orchestrator = Orchestrator(
            groq,
            selector,
            owner_name=StaticLoader().get_profile().profile_details.name,
            temperature=config.orchestrator.temperature,
            top_p=config.orchestrator.top_p,
            max_completion_tokens=config.llm.max_completion_tokens,
        )
        worker = Worker(groq, selector, owner_name="Sahib Nanda", max_completion_tokens=config.llm.max_completion_tokens)

    assert "Sahib Nanda" in orchestrator.system_prompt
    assert "Sahib Nanda" in worker.system_prompt
    assert selector.select().model_id in {model.model_id for model in config.llm.models}


def test_data_service_defaults(config_env: str) -> None:
    data = AppConfig.load().data_service

    assert isinstance(data, DataServiceConfig)
    assert data.cache_impl is TTLKeyValueStoreImpl.IN_MEMORY
    assert data.max_workers == 8
    assert [(account.username, account.cache_ttl) for account in data.leetcode_accounts] == [("imsahibnanda", timedelta(hours=1))]
    assert [(account.username, account.cache_ttl) for account in data.codeforces_accounts] == [("shisukenohara", timedelta(minutes=80))]
    assert [(account.username, account.cache_ttl) for account in data.github_accounts] == [
        ("thesahibnanda-max", timedelta(minutes=45)),
        ("thesahibnanda", timedelta(minutes=120)),
    ]
    assert all(isinstance(account, PlatformAccountConfig) for account in data.github_accounts)
    assert data.resume_link.endswith("Sahib_Nanda_Resume.pdf")
    assert len(data.profile_photo_links) == 2
    assert data.leetcode_profile_url_format == "{base_url}/u/{username}/"
    assert data.codeforces_profile_url_format == "{base_url}/profile/{username}"


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("  cache_impl: in_memory", "  cache_impl: redis", "data_service.cache_impl"),
        ("  max_workers: 8", "  max_workers: 0", "data_service.max_workers"),
        ('      cache_ttl: "1h"', '      cache_ttl: "0s"', "data_service.leetcode_accounts"),
        ('    - username: "thesahibnanda"\n', '    - username: "thesahibnanda-max"\n', "data_service.github_accounts"),
        ('    - username: "shisukenohara"\n', '    - username: ""\n', "data_service.codeforces_accounts"),
        ('  resume_link: "https://', '  resume_link: "ftp://', "data_service.resume_link"),
        ('"{base_url}/u/{username}/"', '"{base_url}/u/"', "data_service.leetcode_profile_url_format"),
        ('"{base_url}/profile/{username}"', '"{base_url}/profile/{username}/{extra}"', "data_service.codeforces_profile_url_format"),
    ],
)
def test_invalid_data_service_values_raise(config_env, tmp_path, old: str, new: str, field: str) -> None:
    with pytest.raises(InvalidConfigError, match=field.replace(".", r"\.")):
        _load_variant(tmp_path, old, new)


def test_chat_and_context_defaults(config_env: str) -> None:
    config = AppConfig.load()

    assert isinstance(config.chat, ChatConfig) and isinstance(config.context, ContextConfig)
    assert (config.chat.max_message_chars, config.chat.max_history_messages, config.chat.max_history_chars, config.chat.max_messages_per_chat) == (
        4000,
        20,
        12000,
        200,
    )
    assert set(config.chat.fallback_messages) == {QueryScope.NOT_RELATED_TO_PORTFOLIO, QueryScope.PROMPT_INJECTION, QueryScope.UNSAFE}
    assert all("portfolio" in message for message in config.chat.fallback_messages.values())
    assert (config.context.max_workers, config.context.max_github_repositories, config.context.max_rating_changes) == (5, 5, 5)


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("  max_message_chars: 4000", "  max_message_chars: 0", "chat.max_message_chars"),
        ("  max_messages_per_chat: 200", "  max_messages_per_chat: 1", "chat.max_messages_per_chat"),
        ("  max_rating_changes: 5", "  max_rating_changes: 0", "context.max_rating_changes"),
    ],
)
def test_invalid_chat_and_context_values_raise(config_env, tmp_path, old: str, new: str, field: str) -> None:
    with pytest.raises(InvalidConfigError, match=field.replace(".", r"\.")):
        _load_variant(tmp_path, old, new)


def test_missing_fallback_scope_raises(config_env, tmp_path) -> None:
    text = "\n".join(line for line in CONFIG_YAML.splitlines() if not line.startswith("    UNSAFE:"))

    with pytest.raises(InvalidConfigError, match=r"chat\.fallback_messages"):
        AppConfig.load(_write(tmp_path, text))


def test_blank_fallback_message_raises(config_env, tmp_path) -> None:
    text = "\n".join(
        '    UNSAFE: "   "' if line.startswith("    UNSAFE:") else line for line in CONFIG_YAML.splitlines()
    )

    with pytest.raises(InvalidConfigError, match=r"chat\.fallback_messages"):
        AppConfig.load(_write(tmp_path, text))


def test_in_scope_fallback_is_rejected(config_env, tmp_path) -> None:
    text = CONFIG_YAML.replace("  fallback_messages:\n", '  fallback_messages:\n    IN_SCOPE: "never used"\n', 1)

    with pytest.raises(InvalidConfigError, match=r"chat\.fallback_messages"):
        AppConfig.load(_write(tmp_path, text))


def test_rate_limit_defaults(config_env: str) -> None:
    config = AppConfig.load().rate_limit

    assert isinstance(config, RateLimitConfig)
    assert (config.storage_uri, config.key_prefix) == ("memory://", "rate_limit")
    assert set(config.rules) == {"create_session", "chat_read", "chat_write", "chat_message", "details", "contact"}
    assert all(set(rules) == set(RateLimitScope) for rules in config.rules.values())
    assert all(
        isinstance(rule, RateLimitRuleConfig) and rule.window == timedelta(minutes=1)
        for api, rules in config.rules.items()
        if api != "contact"
        for rule in rules.values()
    )
    assert {scope: rule.limit for scope, rule in config.rules["chat_message"].items()} == {
        RateLimitScope.IP: 5,
        RateLimitScope.SESSION: 5,
        RateLimitScope.GLOBAL: 60,
    }
    assert config.rules["details"][RateLimitScope.IP].limit == 30


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ('storage_uri: "memory://"', 'storage_uri: ""', "rate_limit.storage_uri"),
        ('key_prefix: "rate_limit"', 'key_prefix: ""', "rate_limit.key_prefix"),
        ("ip: {limit: 5, window: \"1m\"}", "ip: {limit: 0, window: \"1m\"}", "rate_limit.rules.chat_message.ip.limit"),
        ("ip: {limit: 5, window: \"1m\"}", "ip: {limit: \"5\", window: \"1m\"}", "rate_limit.rules.chat_message.ip.limit"),
        ("ip: {limit: 5, window: \"1m\"}", "ip: {limit: 5, window: \"1.5s\"}", "rate_limit.rules.chat_message.ip.window"),
        ("ip: {limit: 5, window: \"1m\"}", "ip: {limit: 5, window: \"0s\"}", "rate_limit.rules.chat_message.ip.window"),
        ("ip: {limit: 5, window: \"1m\"}", "user: {limit: 5, window: \"1m\"}", "rate_limit.rules.chat_message"),
        ("    chat_message:\n", "    Chat-Message:\n", "rate_limit.rules"),
    ],
)
def test_invalid_rate_limit_values_raise(config_env, tmp_path, old: str, new: str, field: str) -> None:
    with pytest.raises(InvalidConfigError, match=field.replace(".", r"\.")):
        _load_variant(tmp_path, old, new)


def test_missing_rate_limit_scope_raises(config_env, tmp_path) -> None:
    text = CONFIG_YAML.replace('      global: {limit: 60, window: "1m"}\n', "", 1)

    with pytest.raises(InvalidConfigError, match=r"rate_limit\.rules\.chat_message"):
        AppConfig.load(_write(tmp_path, text))


def test_empty_rate_limit_rules_raise(config_env, tmp_path) -> None:
    text = CONFIG_YAML[: CONFIG_YAML.index("  rules:\n    create_session:")] + "  rules: {}\n"

    with pytest.raises(InvalidConfigError, match=r"rate_limit\.rules"):
        AppConfig.load(_write(tmp_path, text))


def test_rate_limiter_builds_from_config(config_env: str) -> None:
    config = AppConfig.load().rate_limit
    limiter = RateLimiter(
        storage_uri=config.storage_uri,
        key_prefix=config.key_prefix,
        rules={
            api: {scope: RateLimitRule(**rule.model_dump()) for scope, rule in rules.items()}
            for api, rules in config.rules.items()
        },
    )

    for _ in range(5):
        limiter.check("chat_message", client_ip="203.0.113.7", session_id="s1")

    with pytest.raises(RateLimitExceededError) as error:
        limiter.check("chat_message", client_ip="203.0.113.7", session_id="s1")

    assert error.value.scope is RateLimitScope.IP
    assert limiter.apis == frozenset(config.rules)


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("  workers: 1", "  workers: 0", "app.workers"),
        ("  workers: 1", '  workers: "2"', "app.workers"),
        ("  thread_pool_size: 64", "  thread_pool_size: 0", "app.thread_pool_size"),
        ('  timeout: "180s"', '  timeout: "0s"', "app.timeout"),
        ('  keepalive: "5s"', '  keepalive: "soon"', "app.keepalive"),
        ("  max_body_bytes: 262144", "  max_body_bytes: 0", "app.max_body_bytes"),
        ("  trust_forwarded_for: true", '  trust_forwarded_for: "maybe"', "app.trust_forwarded_for"),
        ('  host: "0.0.0.0"', '  host: ""', "app.host"),
        ('    allow_origins: ["*"]', "    allow_origins: []", "app.cors.allow_origins"),
        ('    max_age: "1h"', '    max_age: "1.5s"', "app.cors.max_age"),
    ],
)
def test_invalid_server_values_raise(config_env, tmp_path, old: str, new: str, field: str) -> None:
    with pytest.raises(InvalidConfigError, match=field.replace(".", r"\.")):
        _load_variant(tmp_path, old, new)


def test_mail_defaults(config_env: str) -> None:
    config = AppConfig.load().mail

    assert isinstance(config, MailConfig)
    assert (config.sender_name, config.timeout) == ("Sahib Nanda · Portfolio", timedelta(seconds=15))
    assert config.recipient_mail == FAKE_RECIPIENT_MAIL
    assert all(isinstance(mail_account, SmtpAccountConfig) for mail_account in config.accounts)
    assert [
        (mail_account.host, mail_account.port, mail_account.security, mail_account.username, mail_account.password.get_secret_value())
        for mail_account in config.accounts
    ] == [
        ("smtp.gmail.com", 587, SmtpSecurity.STARTTLS, FAKE_MAIL_USERNAME, FAKE_MAIL_PASSWORD),
        ("smtp.gmail.com", 587, SmtpSecurity.STARTTLS, FAKE_MAIL_USERNAME_2, FAKE_MAIL_PASSWORD_2),
    ]
    assert FAKE_MAIL_PASSWORD not in repr(config)
    assert FAKE_MAIL_PASSWORD_2 not in repr(config)


@pytest.mark.parametrize("variable", ["MAIL_ACCOUNT_1_PASSWORD", "MAIL_ACCOUNT_2_USERNAME", "RECIPIENT_MAIL"])
def test_missing_mail_environment_raises(config_env, monkeypatch, variable: str) -> None:
    monkeypatch.delenv(variable)

    with pytest.raises(MissingEnvironmentVariableError):
        AppConfig.load()


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("      port: 587", "      port: 0", "mail.accounts.0.port"),
        ('  recipient_mail: "${RECIPIENT_MAIL}"', '  recipient_mail: "owner"', "mail.recipient_mail"),
        ("      security: starttls", "      security: plain", "mail.accounts.0.security"),
        ('  sender_name: "Sahib Nanda · Portfolio"', '  sender_name: "  "', "mail.sender_name"),
        ('  timeout: "15s"', '  timeout: "0s"', "mail.timeout"),
        ('      username: "${MAIL_ACCOUNT_1_USERNAME}"', '      username: "not-an-email"', "mail.accounts.0.username"),
    ],
)
def test_invalid_mail_values_raise(config_env, tmp_path, old: str, new: str, field: str) -> None:
    with pytest.raises(InvalidConfigError, match=field.replace(".", r"\.")) as error:
        _load_variant(tmp_path, old, new)

    assert FAKE_MAIL_PASSWORD not in str(error.value)


def test_duplicate_mail_accounts_raise(config_env, tmp_path) -> None:
    start = CONFIG_YAML.index('    - host: "smtp.gmail.com"')
    end = CONFIG_YAML.index('      password: "${MAIL_ACCOUNT_1_PASSWORD}"\n', start) + len('      password: "${MAIL_ACCOUNT_1_PASSWORD}"\n')
    entry = CONFIG_YAML[start:end]
    with pytest.raises(InvalidConfigError, match=r"mail\.accounts"):
        AppConfig.load(_write(tmp_path, CONFIG_YAML[:end] + entry + CONFIG_YAML[end:]))


def test_mailer_builds_from_config(config_env: str) -> None:
    config = AppConfig.load().mail

    mailer = Mailer(
        accounts=[SmtpAccount(**mail_account.model_dump()) for mail_account in config.accounts],
        recipient=config.recipient_mail,
        sender_name=config.sender_name,
        timeout=config.timeout,
    )

    assert (mailer.accounts, mailer.recipient) == ((FAKE_MAIL_USERNAME, FAKE_MAIL_USERNAME_2), FAKE_RECIPIENT_MAIL)


def test_contact_defaults(config_env: str) -> None:
    config = AppConfig.load()

    assert isinstance(config.contact, ContactConfig)
    assert (config.contact.subject_prefix, config.contact.max_subject_chars, config.contact.max_message_chars) == (
        "[Portfolio]",
        150,
        5000,
    )
    assert (config.contact.check_email_deliverability, config.contact.email_dns_timeout) == (True, timedelta(seconds=3))
    contact_limits = {scope: (rule.limit, rule.window) for scope, rule in config.rate_limit.rules["contact"].items()}
    assert contact_limits == {
        RateLimitScope.IP: (3, timedelta(hours=1)),
        RateLimitScope.SESSION: (3, timedelta(hours=1)),
        RateLimitScope.GLOBAL: (50, timedelta(days=1)),
    }


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ('  subject_prefix: "[Portfolio]"', '  subject_prefix: " "', "contact.subject_prefix"),
        ("  max_subject_chars: 150", "  max_subject_chars: 0", "contact.max_subject_chars"),
        ("  max_message_chars: 5000", '  max_message_chars: "5000"', "contact.max_message_chars"),
        ("  check_email_deliverability: true", '  check_email_deliverability: "maybe"', "contact.check_email_deliverability"),
        ('  email_dns_timeout: "3s"', '  email_dns_timeout: "0s"', "contact.email_dns_timeout"),
    ],
)
def test_invalid_contact_values_raise(config_env, tmp_path, old: str, new: str, field: str) -> None:
    with pytest.raises(InvalidConfigError, match=field.replace(".", r"\.")):
        _load_variant(tmp_path, old, new)
