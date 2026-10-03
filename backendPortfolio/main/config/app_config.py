import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Self
from urllib.parse import urlsplit

import pytimeparse2
import yaml
from envyaml import EnvYAML
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
)

from main.config.exceptions import (
    ConfigFileNotFoundError,
    InvalidConfigError,
    MissingEnvironmentVariableError,
)
from main.package.ai.common.dto import ContextType
from main.package.ai.orchestrator.dto import QueryScope
from main.package.mail.dto import SmtpSecurity
from main.package.ratelimiter.dto import RateLimitScope
from main.package.ttl_key_value_store.ttl_key_value_store import TTLKeyValueStoreImpl

_DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")


def _parse_duration(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("Duration must be a string like '15m' or a number of seconds")

    if isinstance(value, int | float):
        return timedelta(seconds=value)

    if isinstance(value, str):
        duration = pytimeparse2.parse(value, as_timedelta=True)
        if duration is None:
            raise ValueError(f"Invalid duration {value!r}, use a form like '90s', '15m', '12h' or '1h30m'")
        return duration

    return value


def _require_positive_duration(value: timedelta) -> timedelta:
    if value <= timedelta(0):
        raise ValueError("Duration must be positive")

    return value




def _require_http_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.query or parts.fragment:
        raise ValueError("URL must be http or https with a host and no query or fragment")

    return value


def _split_comma_separated(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    return tuple(part.strip() for part in value.split(",") if part.strip())


def _require_ordered_range(value: tuple[float, float]) -> tuple[float, float]:
    if value[0] > value[1]:
        raise ValueError("Range minimum must not be greater than its maximum")

    return value


def _require_unique_model_ids(models: tuple["LLMModelConfig", ...]) -> tuple["LLMModelConfig", ...]:
    model_ids = [model.model_id for model in models]
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("Model ids must be unique")

    return models


def _require_unique_usernames(accounts: tuple["PlatformAccountConfig", ...]) -> tuple["PlatformAccountConfig", ...]:
    usernames = [account.username for account in accounts]
    if len(set(usernames)) != len(usernames):
        raise ValueError("Usernames must be unique")

    return accounts


def _require_unique_mail_usernames(accounts: tuple["SmtpAccountConfig", ...]) -> tuple["SmtpAccountConfig", ...]:
    usernames = [account.username for account in accounts]
    if len(set(usernames)) != len(usernames):
        raise ValueError("Mail account usernames must be unique")

    return accounts


def _require_email_like(value: str) -> str:
    local, _, domain = value.rpartition("@")
    if not local or "." not in domain or any(character.isspace() for character in value):
        raise ValueError("Must be an email address like name@example.com")

    return value


def _require_profile_url_format(value: str) -> str:
    if "{base_url}" not in value or "{username}" not in value:
        raise ValueError("Profile URL format must contain {base_url} and {username}")

    try:
        value.format(base_url="https://example.com", username="user")
    except (KeyError, IndexError, ValueError) as error:
        raise ValueError("Profile URL format may only use {base_url} and {username}") from error

    return value


def _require_fallback_scopes(messages: dict[QueryScope, str]) -> dict[QueryScope, str]:
    expected = set(QueryScope) - {QueryScope.IN_SCOPE}
    if set(messages) != expected:
        raise ValueError(f"Fallback messages must cover exactly {sorted(expected)}")

    return messages


def _require_agent_markers(markers: dict[QueryScope, str]) -> dict[QueryScope, str]:
    if QueryScope.IN_SCOPE in markers:
        raise ValueError("IN_SCOPE has no marker")

    values = list(markers.values())
    if any(value != value.strip() for value in values):
        raise ValueError("Markers must not have surrounding whitespace")

    if len(set(values)) != len(values) or any(a != b and b.startswith(a) for a in values for b in values):
        raise ValueError("Markers must be unique and none may be a prefix of another")

    return markers


def _require_regex(value: str) -> str:
    try:
        re.compile(value)
    except re.error as error:
        raise ValueError(f"Invalid regular expression: {error}") from error

    return value


def _require_real_contexts(contexts: tuple[ContextType, ...]) -> tuple[ContextType, ...]:
    if ContextType.NONE in contexts:
        raise ValueError("NONE is not a context section")

    return contexts


def _require_real_context_keys(keywords: dict[ContextType, Any]) -> dict[ContextType, Any]:
    _require_real_contexts(tuple(keywords))
    return keywords


def _require_whole_seconds(value: timedelta) -> timedelta:
    if value % timedelta(seconds=1):
        raise ValueError("Duration must be a whole number of seconds")

    return value


def _require_every_rate_limit_scope(rules: dict[RateLimitScope, Any]) -> dict[RateLimitScope, Any]:
    if set(rules) != set(RateLimitScope):
        raise ValueError(f"Rules must cover exactly {sorted(RateLimitScope)}")

    return rules


def _require_non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text must not be blank")

    return value.strip()


def _format_validation_error(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
        for detail in error.errors(include_input=False, include_url=False)
    )


Duration = Annotated[
    timedelta,
    BeforeValidator(_parse_duration),
    AfterValidator(_require_positive_duration),
]
NonEmptyStr = Annotated[str, Field(min_length=1)]
HttpUrlStr = Annotated[str, AfterValidator(_require_http_url)]


class _FrozenConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CorsConfig(_FrozenConfig):
    allow_origins: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    max_age: Annotated[Duration, AfterValidator(_require_whole_seconds)]


class ServerConfig(_FrozenConfig):
    host: NonEmptyStr
    port: Annotated[int, Field(ge=1, le=65535)]
    workers: Annotated[int, Field(strict=True, ge=1)]
    thread_pool_size: Annotated[int, Field(strict=True, ge=1)]
    timeout: Duration
    graceful_timeout: Duration
    keepalive: Duration
    max_body_bytes: Annotated[int, Field(strict=True, ge=1)]
    trust_forwarded_for: bool
    cors: CorsConfig


class TTLKeyValueStoreConfig(_FrozenConfig):
    sweep_intervals: dict[TTLKeyValueStoreImpl, Duration]


class HttpClientConfig(_FrozenConfig):
    connect_timeout: Duration
    read_timeout: Duration
    write_timeout: Duration
    pool_timeout: Duration


class LeetcodeConfig(_FrozenConfig):
    base_url: HttpUrlStr


class CodeforcesConfig(_FrozenConfig):
    base_url: HttpUrlStr


class GitHubConfig(_FrozenConfig):
    base_url: HttpUrlStr
    api_version: NonEmptyStr
    per_page: Annotated[int, Field(ge=1, le=100)]


class GroqConfig(_FrozenConfig):
    base_url: HttpUrlStr
    api_keys: Annotated[
        tuple[Annotated[SecretStr, Field(min_length=1)], ...],
        BeforeValidator(_split_comma_separated),
        Field(min_length=1),
    ]


class LLMModelConfig(_FrozenConfig):
    model_id: NonEmptyStr
    weight: Annotated[int, Field(ge=1)]
    reasoning_effort: NonEmptyStr | None = None
    supports_strict_json_schema: bool = False


class LLMConfig(_FrozenConfig):
    models: Annotated[
        tuple[LLMModelConfig, ...],
        Field(min_length=1),
        AfterValidator(_require_unique_model_ids),
    ]
    temperature_range: Annotated[
        tuple[Annotated[float, Field(ge=0, le=2)], Annotated[float, Field(ge=0, le=2)]],
        AfterValidator(_require_ordered_range),
    ]
    top_p_range: Annotated[
        tuple[Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)]],
        AfterValidator(_require_ordered_range),
    ]
    max_completion_tokens: Annotated[int, Field(ge=1)]


class OrchestratorConfig(_FrozenConfig):
    temperature: Annotated[float, Field(ge=0, le=2)]
    top_p: Annotated[float, Field(ge=0, le=1)]


class RepositoryConfig(_FrozenConfig):
    database_path: NonEmptyStr
    session_ttl: Duration
    sweep_interval: Duration
    busy_timeout: Duration


class PlatformAccountConfig(_FrozenConfig):
    username: NonEmptyStr
    cache_ttl: Duration


PlatformAccounts = Annotated[
    tuple[PlatformAccountConfig, ...],
    Field(min_length=1),
    AfterValidator(_require_unique_usernames),
]
ProfileUrlFormat = Annotated[str, AfterValidator(_require_profile_url_format)]


class DataServiceConfig(_FrozenConfig):
    cache_impl: TTLKeyValueStoreImpl
    max_workers: Annotated[int, Field(ge=1)]
    leetcode_accounts: PlatformAccounts
    codeforces_accounts: PlatformAccounts
    github_accounts: PlatformAccounts
    profile_photo_links: tuple[HttpUrlStr, ...]
    leetcode_profile_url_format: ProfileUrlFormat
    codeforces_profile_url_format: ProfileUrlFormat


class ChatConfig(_FrozenConfig):
    max_message_chars: Annotated[int, Field(ge=1)]
    max_history_messages: Annotated[int, Field(ge=1)]
    max_history_chars: Annotated[int, Field(ge=1)]
    max_messages_per_chat: Annotated[int, Field(ge=2)]
    fallback_messages: Annotated[
        dict[QueryScope, Annotated[str, AfterValidator(_require_non_blank)]],
        AfterValidator(_require_fallback_scopes),
    ]


class AgentConfig(_FrozenConfig):
    model: LLMModelConfig
    temperature: Annotated[float, Field(ge=0, le=2)]
    top_p: Annotated[float, Field(ge=0, le=1)]
    max_completion_tokens: Annotated[int, Field(strict=True, ge=1)]
    max_question_chars: Annotated[int, Field(strict=True, ge=1)]
    max_history_messages: Annotated[int, Field(strict=True, ge=1)]
    max_history_chars: Annotated[int, Field(strict=True, ge=1)]
    max_messages_per_chat: Annotated[int, Field(strict=True, ge=2)]
    cache_ttl: Duration
    daily_token_budget: Annotated[int, Field(strict=True, ge=1)]
    markers: Annotated[dict[QueryScope, NonEmptyStr], Field(min_length=1), AfterValidator(_require_agent_markers)]
    injection_patterns: tuple[Annotated[str, Field(min_length=1), AfterValidator(_require_regex)], ...]
    default_contexts: Annotated[tuple[ContextType, ...], Field(min_length=1), AfterValidator(_require_real_contexts)]
    context_keywords: Annotated[
        dict[ContextType, Annotated[tuple[Annotated[str, AfterValidator(_require_non_blank)], ...], Field(min_length=1)]],
        AfterValidator(_require_real_context_keys),
    ]


class ContextConfig(_FrozenConfig):
    max_workers: Annotated[int, Field(ge=1)]
    max_github_repositories: Annotated[int, Field(ge=1)]
    max_rating_changes: Annotated[int, Field(ge=1)]


class RateLimitRuleConfig(_FrozenConfig):
    limit: Annotated[int, Field(strict=True, ge=1)]
    window: Annotated[Duration, AfterValidator(_require_whole_seconds)]


class RateLimitConfig(_FrozenConfig):
    storage_uri: NonEmptyStr
    key_prefix: NonEmptyStr
    rules: Annotated[
        dict[
            Annotated[str, Field(pattern=r"^[a-z0-9_]+$")],
            Annotated[dict[RateLimitScope, RateLimitRuleConfig], AfterValidator(_require_every_rate_limit_scope)],
        ],
        Field(min_length=1),
    ]


class SmtpAccountConfig(_FrozenConfig):
    host: NonEmptyStr
    port: Annotated[int, Field(strict=True, ge=1, le=65535)]
    security: SmtpSecurity
    username: Annotated[str, AfterValidator(_require_email_like)]
    password: Annotated[SecretStr, Field(min_length=1)]


class MailConfig(_FrozenConfig):
    recipient_mail: Annotated[str, AfterValidator(_require_email_like)]
    sender_name: Annotated[str, AfterValidator(_require_non_blank)]
    timeout: Duration
    accounts: Annotated[
        tuple[SmtpAccountConfig, ...],
        Field(min_length=1),
        AfterValidator(_require_unique_mail_usernames),
    ]


class ContactConfig(_FrozenConfig):
    subject_prefix: Annotated[str, AfterValidator(_require_non_blank)]
    max_subject_chars: Annotated[int, Field(strict=True, ge=1)]
    max_message_chars: Annotated[int, Field(strict=True, ge=1)]
    check_email_deliverability: Annotated[bool, Field(strict=True)]
    email_dns_timeout: Duration


class AppConfig(_FrozenConfig):
    app: ServerConfig
    ttl_key_value_store: TTLKeyValueStoreConfig
    http_client: HttpClientConfig
    leetcode: LeetcodeConfig
    codeforces: CodeforcesConfig
    github: GitHubConfig
    groq: GroqConfig
    llm: LLMConfig
    orchestrator: OrchestratorConfig
    repository: RepositoryConfig
    data_service: DataServiceConfig
    chat: ChatConfig
    agent: AgentConfig
    context: ContextConfig
    rate_limit: RateLimitConfig
    mail: MailConfig
    contact: ContactConfig

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> Self:
        config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH

        try:
            raw_config = EnvYAML(str(config_path), env_file=os.devnull, flatten=False).export()
        except FileNotFoundError as error:
            raise ConfigFileNotFoundError(f"Config file not found: {config_path}") from error
        except yaml.YAMLError as error:
            raise InvalidConfigError(f"Config file is not valid YAML: {config_path}") from error
        except ValueError as error:
            raise MissingEnvironmentVariableError(str(error)) from error

        sections = {name: raw_config[name] for name in cls.model_fields if name in raw_config}

        try:
            return cls.model_validate(sections)
        except ValidationError as error:
            raise InvalidConfigError(
                f"Invalid config in {config_path}: {_format_validation_error(error)}"
            ) from error
