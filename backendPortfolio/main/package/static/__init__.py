"""
The site owner's profile, personality, profile photo and résumé, plus the
Portfolio Agent CLI manifest and fortunes, read from files in this package
once and then served from memory.

Exports:
    StaticLoader: loads the files once and returns them on every call.
    CliManifest (with CliPlugin, CliSkill, CliSetting): what the /cli
    terminal can do.
    StaticAsset: a binary file served as-is (content, media_type, etag); used
    for the profile photo and the résumé.
    Profile, Personality and the nested DTOs they are built from.
    StaticDataError and its subclasses: the errors described under Errors.

Load once:
    StaticLoader() takes no arguments and does not depend on
    main.config.AppConfig. It reads profile.json and personality.json from
    this package's own folder (with pfp.jpg and resume.pdf), so it works
    from any working directory.
    The constructor reads, parses and validates every file immediately and
    keeps the results. get_profile(), get_personality(), get_profile_image()
    and get_resume() then return those same objects on every call: no
    file access, no parsing, no lock.
    Loading in the constructor means the data is ready as soon as the loader
    exists, a missing or broken file fails at startup instead of on the
    first request, and there is no first-caller race to guard against
    under free threading. Create one StaticLoader at startup and share it.
    Editing a file afterwards has no effect until a new StaticLoader is
    created, for example after a restart.

Files and DTOs:
    Frozen pydantic models. JSON keys are camelCase and are read into
    snake_case attributes; lists become tuples. Because this is our own
    data, unknown keys are rejected (extra="forbid") and every field is
    required, so a typo in a file fails loudly at startup. Dumping a model
    with model_dump_json(by_alias=True) gives back the original JSON.

    profile.json -> Profile
        profile_details: ProfileDetails (name, email)
        projects: tuple of Project (name, year, link, description,
        technologies)
        languages, achievements: tuples of str
        experience: tuple of Experience (company, location, employment_type,
        title, start_date, end_date, description, technologies)
        education: tuple of Education (institution, degree, field,
        start_date, end_date, grade)
        skills_by_category: read-only mapping from a category name such as
        "Distributed Systems" to a tuple of skills. It is a
        types.MappingProxyType, so it cannot be changed, and it is dumped as
        a plain dict.
        start_date must be "YYYY-MM"; end_date must be "YYYY-MM" or
        "Present".

    personality.json -> Personality
        personal_profile: PersonalProfile with
            basic_info: BasicInfo (nationality, gender, height: Height with
            feet and centimeters)
            physical_appearance: PhysicalAppearance (body_type, physique,
            fitness_level, strongest_muscle_group, fitness_goals, hair: Hair,
            eyes: Eyes, skin_tone, face: Face, accessories: Accessories with
            wears_glasses, fashion: Fashion)
            personality: PersonalityTraits (core_traits,
            professional_traits, work_preferences: WorkPreferences,
            personal_values)
            interests: Interests (sports: Sports with football and cricket
            as SportFavorite, fitness, technology)
            favorites: Favorites (movies and games as TitledFavorite,
            artists as Artist, sports_icons: SportsIcons)
            lifestyle: Lifestyle (four bools)
            languages: tuple of SpokenLanguage (name, proficiency)

    pfp.jpg -> StaticAsset
        content: the JPEG bytes (hidden from repr). media_type: "image/jpeg".
        etag: the first 16 hex characters of the content's SHA-256, which
        changes whenever the photo does, so it can version URLs and answer
        If-None-Match. The file must start with the JPEG signature
        (FF D8 FF); anything else raises InvalidStaticDataError. The photo
        is kept out of Profile so the profile stays plain JSON data; the API
        serves it from its own endpoint.

    cli.json -> CliManifest, from get_cli_manifest()
        The single source of truth for the terminal, shared by the /cli UI
        (through GET /details/cli) and both AIs (through the SITE context).
        plugins: name, summary, enabled_by_default, removable.
        skills: name, aliases, usage, summary, group (Explore, AI,
        Session), plugin, arg_source (where autocomplete finds arguments).
        settings: key, label, summary, options (at least 2), default.
        Plugin names, setting keys, and skill names together with aliases
        are each unique; every skill's plugin exists; a plugin that cannot
        be removed is enabled by default; every default is one of its
        options. Anything else fails at startup.

    fortunes.md -> tuple of str, from get_fortunes()
        Every line starting with "- " is one fortune for /fortune; a file
        without any raises InvalidStaticDataError.

    resume.pdf -> StaticAsset
        The same shape as the photo with media_type "application/pdf". The
        file must start with the PDF signature (%PDF-). Replacing the file
        changes the etag, so the versioned résumé URL changes with it.

Errors (all in exceptions.py, all subclasses of StaticDataError):
    StaticFileNotFoundError: a file does not exist; FileNotFoundError is
    chained as __cause__.
    InvalidStaticDataError: a file is not valid JSON or does not match its
    DTO (missing or unknown field, wrong type, bad date), pfp.jpg is not a
    JPEG or resume.pdf is not a PDF. The message names
    the file and every failing field; pydantic's ValidationError is chained
    as __cause__.
    Catch StaticDataError to handle every failure at once.

Thread safety:
    After construction the loader holds only frozen models, tuples and a
    read-only mapping, so one instance can be read from any number of
    threads at once on the free-threaded Python 3.14t build.

Example:
    loader = StaticLoader()
    loader.get_profile().profile_details.name
    loader.get_profile() is loader.get_profile()
"""

from .dto import (
    Accessories,
    CliManifest,
    CliPlugin,
    CliSetting,
    CliSkill,
    Artist,
    BasicInfo,
    Education,
    Experience,
    Eyes,
    Face,
    Fashion,
    Favorites,
    Hair,
    Height,
    Interests,
    Lifestyle,
    PersonalityTraits,
    Personality,
    PersonalProfile,
    PhysicalAppearance,
    Profile,
    ProfileDetails,
    Project,
    SpokenLanguage,
    SportFavorite,
    Sports,
    SportsIcons,
    StaticAsset,
    TitledFavorite,
    WorkPreferences,
)
from .exceptions import (
    InvalidStaticDataError,
    StaticDataError,
    StaticFileNotFoundError,
)
from .static import StaticLoader

__all__ = [
    "StaticLoader",
    "StaticAsset",
    "CliManifest",
    "CliPlugin",
    "CliSkill",
    "CliSetting",
    "Profile",
    "ProfileDetails",
    "Project",
    "Experience",
    "Education",
    "Personality",
    "PersonalProfile",
    "BasicInfo",
    "Height",
    "PhysicalAppearance",
    "Hair",
    "Eyes",
    "Face",
    "Accessories",
    "Fashion",
    "PersonalityTraits",
    "WorkPreferences",
    "Interests",
    "Sports",
    "SportFavorite",
    "Favorites",
    "TitledFavorite",
    "Artist",
    "SportsIcons",
    "Lifestyle",
    "SpokenLanguage",
    "StaticDataError",
    "StaticFileNotFoundError",
    "InvalidStaticDataError",
]
