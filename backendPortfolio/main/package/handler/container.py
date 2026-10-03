from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

import dns.resolver
import httpx

from main.config import AppConfig
from main.package.ai.agent import Agent
from main.package.ai.common import LLMModel, ModelSelector
from main.package.ai.orchestrator import Orchestrator
from main.package.ai.worker import Worker
from main.package.clients.codeforces import CodeforcesClient
from main.package.clients.github import GitHubClient
from main.package.clients.groq import GroqClient
from main.package.clients.leetcode import LeetcodeClient
from main.package.mail import Mailer, SmtpAccount, SmtpConnector
from main.package.ratelimiter import RateLimiter, RateLimitRule
from main.package.repository import ChatRepository, SqliteChatRepository
from main.package.service.agent import AgentService, AnswerCache, ScopeGate, TokenBudget
from main.package.service.chat import ChatService, HistoryWindow, MessageValidator
from main.package.service.contact import ContactService, EmailNormalizer
from main.package.service.context import (
    CodeforcesContextProvider,
    ContextAggregator,
    GitHubContextProvider,
    LeetcodeContextProvider,
    PersonalityContextProvider,
    ProfileContextProvider,
)
from main.package.service.data import DataService, PlatformAccount
from main.package.static import StaticLoader
from main.package.ttl_key_value_store import TTLKeyValueStore, TTLKeyValueStoreFactory


@dataclass(frozen=True)
class UpstreamTransports:
    leetcode: httpx.BaseTransport | None = None
    codeforces: httpx.BaseTransport | None = None
    github: httpx.BaseTransport | None = None
    groq: httpx.BaseTransport | None = None
    smtp: SmtpConnector | None = None
    dns_resolver: dns.resolver.Resolver | None = None


@dataclass(frozen=True)
class ServiceContainer:
    repository: ChatRepository
    data_service: DataService
    static_loader: StaticLoader
    chat_service: ChatService
    agent_service: AgentService
    contact_service: ContactService
    rate_limiter: RateLimiter
    closers: tuple[Callable[[], None], ...] = ()

    def close(self) -> None:
        for close in reversed(self.closers):
            close()

    @classmethod
    def from_config(cls, config: AppConfig, transports: UpstreamTransports = UpstreamTransports()) -> Self:
        closers: list[Callable[[], None]] = []
        try:
            return cls._build(config, transports, closers)
        except BaseException:
            for close in reversed(closers):
                close()
            raise

    @classmethod
    def _build(cls, config: AppConfig, transports: UpstreamTransports, closers: list[Callable[[], None]]) -> Self:
        timeouts = config.http_client.model_dump()

        factory = TTLKeyValueStoreFactory(config.ttl_key_value_store.sweep_intervals)
        closers.append(factory.close_all)
        leetcode = LeetcodeClient(base_url=config.leetcode.base_url, transport=transports.leetcode, **timeouts)
        closers.append(leetcode.close)
        codeforces = CodeforcesClient(base_url=config.codeforces.base_url, transport=transports.codeforces, **timeouts)
        closers.append(codeforces.close)
        github = GitHubClient(
            base_url=config.github.base_url,
            api_version=config.github.api_version,
            per_page=config.github.per_page,
            transport=transports.github,
            **timeouts,
        )
        closers.append(github.close)
        groq = GroqClient(
            base_url=config.groq.base_url,
            api_keys=[key.get_secret_value() for key in config.groq.api_keys],
            transport=transports.groq,
            **timeouts,
        )
        closers.append(groq.close)

        data_service = cls._data_service(config, factory, leetcode, codeforces, github)
        closers.append(data_service.close)
        static_loader = StaticLoader()
        aggregator = cls._aggregator(config, static_loader, data_service)
        closers.append(aggregator.close)
        repository = SqliteChatRepository(**config.repository.model_dump())
        closers.append(repository.close)

        return cls(
            repository=repository,
            data_service=data_service,
            static_loader=static_loader,
            chat_service=cls._chat_service(config, repository, aggregator, groq, static_loader),
            agent_service=cls._agent_service(
                config,
                repository,
                aggregator,
                groq,
                static_loader,
                factory.get_ttl_key_value_store(config.data_service.cache_impl),
            ),
            contact_service=cls._contact_service(config, transports),
            rate_limiter=cls._rate_limiter(config),
            closers=tuple(closers),
        )

    @staticmethod
    def _data_service(
        config: AppConfig,
        factory: TTLKeyValueStoreFactory,
        leetcode: LeetcodeClient,
        codeforces: CodeforcesClient,
        github: GitHubClient,
    ) -> DataService:
        settings = config.data_service
        return DataService(
            leetcode_client=leetcode,
            codeforces_client=codeforces,
            github_client=github,
            ttl_key_value_store_factory=factory,
            cache_impl=settings.cache_impl,
            leetcode_accounts=[PlatformAccount(**account.model_dump()) for account in settings.leetcode_accounts],
            codeforces_accounts=[PlatformAccount(**account.model_dump()) for account in settings.codeforces_accounts],
            github_accounts=[PlatformAccount(**account.model_dump()) for account in settings.github_accounts],
            profile_photo_links=settings.profile_photo_links,
            leetcode_profile_url_format=settings.leetcode_profile_url_format,
            codeforces_profile_url_format=settings.codeforces_profile_url_format,
            max_workers=settings.max_workers,
        )

    @staticmethod
    def _aggregator(config: AppConfig, static_loader: StaticLoader, data_service: DataService) -> ContextAggregator:
        return ContextAggregator(
            providers=[
                ProfileContextProvider(static_loader, data_service),
                PersonalityContextProvider(static_loader, data_service),
                GitHubContextProvider(data_service, max_repositories=config.context.max_github_repositories),
                LeetcodeContextProvider(data_service),
                CodeforcesContextProvider(data_service, max_rating_changes=config.context.max_rating_changes),
            ],
            max_workers=config.context.max_workers,
        )

    @staticmethod
    def _chat_service(
        config: AppConfig,
        repository: ChatRepository,
        aggregator: ContextAggregator,
        groq: GroqClient,
        static_loader: StaticLoader,
    ) -> ChatService:
        selector = ModelSelector(
            models=[LLMModel(**model.model_dump()) for model in config.llm.models],
            temperature_range=config.llm.temperature_range,
            top_p_range=config.llm.top_p_range,
        )
        owner_name = static_loader.get_profile().profile_details.name
        return ChatService(
            repository=repository,
            orchestrator=Orchestrator(
                groq,
                selector,
                owner_name=owner_name,
                temperature=config.orchestrator.temperature,
                top_p=config.orchestrator.top_p,
                max_completion_tokens=config.llm.max_completion_tokens,
            ),
            worker=Worker(groq, selector, owner_name=owner_name, max_completion_tokens=config.llm.max_completion_tokens),
            context_aggregator=aggregator,
            message_validator=MessageValidator(max_message_chars=config.chat.max_message_chars),
            history_window=HistoryWindow(
                max_messages=config.chat.max_history_messages,
                max_chars=config.chat.max_history_chars,
            ),
            fallback_messages=config.chat.fallback_messages,
            max_messages_per_chat=config.chat.max_messages_per_chat,
        )

    @staticmethod
    def _agent_service(
        config: AppConfig,
        repository: ChatRepository,
        aggregator: ContextAggregator,
        groq: GroqClient,
        static_loader: StaticLoader,
        store: TTLKeyValueStore,
    ) -> AgentService:
        settings = config.agent
        selector = ModelSelector(
            models=[LLMModel(**settings.model.model_dump())],
            temperature_range=(settings.temperature, settings.temperature),
            top_p_range=(settings.top_p, settings.top_p),
        )
        return AgentService(
            repository=repository,
            agent=Agent(
                groq,
                selector,
                owner_name=static_loader.get_profile().profile_details.name,
                markers=settings.markers,
                max_completion_tokens=settings.max_completion_tokens,
            ),
            scope_gate=ScopeGate(
                injection_patterns=settings.injection_patterns,
                context_keywords=settings.context_keywords,
                default_contexts=settings.default_contexts,
            ),
            context_aggregator=aggregator,
            message_validator=MessageValidator(max_message_chars=settings.max_question_chars),
            history_window=HistoryWindow(max_messages=settings.max_history_messages, max_chars=settings.max_history_chars),
            answer_cache=AnswerCache(store=store, ttl=settings.cache_ttl),
            token_budget=TokenBudget(daily_tokens=settings.daily_token_budget),
            fallback_messages=config.chat.fallback_messages,
            max_messages_per_chat=settings.max_messages_per_chat,
        )

    @staticmethod
    def _contact_service(config: AppConfig, transports: UpstreamTransports) -> ContactService:
        mail = config.mail
        contact = config.contact
        mailer = Mailer(
            accounts=[SmtpAccount(**account.model_dump()) for account in mail.accounts],
            recipient=mail.recipient_mail,
            sender_name=mail.sender_name,
            timeout=mail.timeout,
            connector=transports.smtp,
        )
        email_normalizer = EmailNormalizer(
            check_deliverability=contact.check_email_deliverability,
            dns_timeout=contact.email_dns_timeout,
            resolver=transports.dns_resolver,
        )
        return ContactService(
            mailer=mailer,
            email_normalizer=email_normalizer,
            subject_prefix=contact.subject_prefix,
            max_subject_chars=contact.max_subject_chars,
            max_message_chars=contact.max_message_chars,
        )

    @staticmethod
    def _rate_limiter(config: AppConfig) -> RateLimiter:
        settings = config.rate_limit
        return RateLimiter(
            storage_uri=settings.storage_uri,
            key_prefix=settings.key_prefix,
            rules={
                api: {scope: RateLimitRule(**rule.model_dump()) for scope, rule in rules.items()}
                for api, rules in settings.rules.items()
            },
        )
