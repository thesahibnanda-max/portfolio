from dataclasses import dataclass
from pathlib import Path

from jinja2 import Template

from main.package.ai.common import ContextType, build_prompt_environment
from main.package.service.context.context_provider import ContextProvider
from main.package.service.context.exceptions import InvalidContextSettingError
from main.package.service.data import (
    CodeforcesDetails,
    CodeforcesRatingTransition,
    DataService,
    GitHubDetails,
    GitHubRepositorySummary,
)
from main.package.static import StaticLoader

_ENVIRONMENT = build_prompt_environment(Path(__file__).with_name("templates"))


@dataclass(frozen=True)
class _GitHubAccountView:
    details: GitHubDetails
    top_repositories: tuple[GitHubRepositorySummary, ...]


@dataclass(frozen=True)
class _CodeforcesAccountView:
    details: CodeforcesDetails
    recent_changes: tuple[CodeforcesRatingTransition, ...]


def _require_instance(name: str, value: object, expected: type) -> None:
    if not isinstance(value, expected):
        raise InvalidContextSettingError(f"{name} must be a {expected.__name__}")


def _require_positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidContextSettingError(f"{name} must be a positive int")

    return value


def _stars(repository: GitHubRepositorySummary) -> int:
    return repository.stars or 0


def _template(name: str) -> Template:
    return _ENVIRONMENT.get_template(name)


class ProfileContextProvider(ContextProvider):
    def __init__(self, static_loader: StaticLoader, data_service: DataService) -> None:
        _require_instance("static_loader", static_loader, StaticLoader)
        _require_instance("data_service", data_service, DataService)
        self._static_loader = static_loader
        self._data_service = data_service
        self._template = _template("profile.md")

    @property
    def context_type(self) -> ContextType:
        return ContextType.PROFILE

    def render(self) -> str:
        return self._template.render(
            profile=self._static_loader.get_profile(),
            leetcode=self._data_service.get_leetcode_details()[0],
            github_usernames=[account.username for account in self._data_service.github_accounts],
            leetcode_usernames=[account.username for account in self._data_service.leetcode_accounts],
            codeforces_usernames=[account.username for account in self._data_service.codeforces_accounts],
        )


class PersonalityContextProvider(ContextProvider):
    def __init__(self, static_loader: StaticLoader, data_service: DataService) -> None:
        _require_instance("static_loader", static_loader, StaticLoader)
        _require_instance("data_service", data_service, DataService)
        self._static_loader = static_loader
        self._data_service = data_service
        self._template = _template("personality.md")

    @property
    def context_type(self) -> ContextType:
        return ContextType.PERSONALITY

    def render(self) -> str:
        return self._template.render(
            personality=self._static_loader.get_personality(),
            about_me=self._data_service.get_leetcode_details()[0].about_me,
        )


class GitHubContextProvider(ContextProvider):
    def __init__(self, data_service: DataService, *, max_repositories: int) -> None:
        _require_instance("data_service", data_service, DataService)
        self._data_service = data_service
        self._max_repositories = _require_positive_int("max_repositories", max_repositories)
        self._template = _template("github.md")

    @property
    def context_type(self) -> ContextType:
        return ContextType.GITHUB

    def render(self) -> str:
        accounts = [
            _GitHubAccountView(
                details=details,
                top_repositories=tuple(sorted(details.repositories, key=_stars, reverse=True)[:self._max_repositories]),
            )
            for details in self._data_service.get_github_details()
        ]
        return self._template.render(accounts=accounts)


class LeetcodeContextProvider(ContextProvider):
    def __init__(self, data_service: DataService) -> None:
        _require_instance("data_service", data_service, DataService)
        self._data_service = data_service
        self._template = _template("leetcode.md")

    @property
    def context_type(self) -> ContextType:
        return ContextType.LEETCODE

    def render(self) -> str:
        return self._template.render(accounts=self._data_service.get_leetcode_details())


class CodeforcesContextProvider(ContextProvider):
    def __init__(self, data_service: DataService, *, max_rating_changes: int) -> None:
        _require_instance("data_service", data_service, DataService)
        self._data_service = data_service
        self._max_rating_changes = _require_positive_int("max_rating_changes", max_rating_changes)
        self._template = _template("codeforces.md")

    @property
    def context_type(self) -> ContextType:
        return ContextType.CODEFORCES

    def render(self) -> str:
        accounts = [
            _CodeforcesAccountView(details=details, recent_changes=details.rating_history[-self._max_rating_changes:])
            for details in self._data_service.get_codeforces_details()
        ]
        return self._template.render(accounts=accounts)


def _format_alias(alias: str) -> str:
    return f"/{alias}"


class SiteContextProvider(ContextProvider):
    def __init__(self, static_loader: StaticLoader) -> None:
        _require_instance("static_loader", static_loader, StaticLoader)
        manifest = static_loader.get_cli_manifest()
        enabled = {plugin.name for plugin in manifest.plugins if plugin.enabled_by_default}
        environment = build_prompt_environment(Path(__file__).with_name("templates"))
        environment.filters["format_alias"] = _format_alias
        self._text = environment.get_template("site.md").render(
            owner_name=static_loader.get_profile().profile_details.name,
            plugins=manifest.plugins,
            skills=manifest.skills,
            settings=manifest.settings,
            counts={plugin.name: sum(skill.plugin == plugin.name for skill in manifest.skills) for plugin in manifest.plugins},
            default_count=sum(skill.plugin in enabled for skill in manifest.skills),
        )

    @property
    def context_type(self) -> ContextType:
        return ContextType.SITE

    def render(self) -> str:
        return self._text
