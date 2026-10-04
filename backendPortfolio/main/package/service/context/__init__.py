"""
Builds the portfolio context text the Worker AI answers from: one block per
knowledge domain the orchestrator asked for.

Exports:
    ContextProvider: the strategy interface, one implementation per
    ContextType.
    ProfileContextProvider, PersonalityContextProvider, GitHubContextProvider,
    LeetcodeContextProvider, CodeforcesContextProvider: the providers.
    ContextAggregator: picks and runs the providers a decision needs.
    ContextError and InvalidContextSettingError: the errors.

Providers:
    Each provider has a context_type and render(), which loads its data and
    renders its own Jinja template from templates/ (embedded in this package,
    the only place the context wording lives):
        PROFILE (profile.md): the profile JSON from StaticLoader (name, email,
        spoken languages, skills by category, achievements, experience,
        education, projects with links) plus the primary LeetCode account's
        country, LinkedIn, Twitter and websites, plus every platform's
        usernames from DataService.
        SITE (site.md): the portfolio site and the /cli terminal, rendered
        once from the CLI manifest: every skill (slash command) with usage
        and aliases, grouped by plugin with counts, the plugins, the /config
        settings, the modes and keyboard shortcuts. It tells the model that
        "skills" in a question about the terminal means its commands.
        PERSONALITY (personality.md): the personality JSON plus the LeetCode
        "about me" text. Private details (gender, height and physical
        appearance) are deliberately left out, so the AI cannot reveal them;
        only the nationality and favourite colours are kept.
        GITHUB (github.md): per account, repo, follower and following counts,
        bio, and the top max_repositories repositories by stars.
        LEETCODE (leetcode.md): per account, rank, problems solved by
        difficulty, contest rating, streak, badges and languages used.
        CODEFORCES (codeforces.md): per account, current and max rating,
        rated contest count and the last max_rating_changes contests.
    Blank values are left out instead of printed as empty. Data comes from
    main.package.service.data.DataService (cached) and
    main.package.static.StaticLoader (loaded once).
    Adding a knowledge domain means a new ContextType member, a new provider
    and a new template; nothing else changes.

ContextAggregator(*, providers, max_workers)
    providers: exactly one ContextProvider for every ContextType except NONE;
    a missing or duplicate one raises InvalidContextSettingError at startup.
    max_workers: positive int, the size of its own thread pool.
    aggregate(contexts) -> str: renders the requested providers in parallel
    and joins their blocks with a blank line, always in ContextType order
    (PROFILE, GITHUB, LEETCODE, CODEFORCES, PERSONALITY) whatever order they
    were asked in. Duplicates count once. NONE, or no contexts, gives "".
    Anything other than ContextType members raises InvalidContextSettingError.
    Data errors (main.package.service.data.DataServiceError) pass through.
    close() shuts the pool down; it is also a context manager.

Thread safety:
    Templates are compiled once and rendering keeps no shared state, so one
    aggregator and its providers can serve every thread on the free-threaded
    Python 3.14t build.
"""

from .context_aggregator import ContextAggregator
from .context_provider import ContextProvider
from .exceptions import ContextError, InvalidContextSettingError
from .providers import (
    CodeforcesContextProvider,
    GitHubContextProvider,
    LeetcodeContextProvider,
    PersonalityContextProvider,
    ProfileContextProvider,
    SiteContextProvider,
)

__all__ = [
    "ContextProvider",
    "ProfileContextProvider",
    "PersonalityContextProvider",
    "GitHubContextProvider",
    "LeetcodeContextProvider",
    "CodeforcesContextProvider",
    "SiteContextProvider",
    "ContextAggregator",
    "ContextError",
    "InvalidContextSettingError",
]
