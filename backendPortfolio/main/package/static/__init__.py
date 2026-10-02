"""
The site owner's profile and personality, read from JSON files once and then
served from memory.

Exports:
    StaticLoader: loads both files once and returns them on every call.
    Profile, Personality and the nested DTOs they are built from.
    StaticDataError and its subclasses: the errors described under Errors.

Load once:
    StaticLoader() takes no arguments and does not depend on
    main.config.AppConfig. It reads profile.json and personality.json from
    this package's own folder, so it works from any working directory.
    The constructor reads, parses and validates both files immediately and
    keeps the results. get_profile() and get_personality() then return those
    same objects on every call: no file access, no parsing, no lock.
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

Errors (all in exceptions.py, all subclasses of StaticDataError):
    StaticFileNotFoundError: a file does not exist; FileNotFoundError is
    chained as __cause__.
    InvalidStaticDataError: a file is not valid JSON or does not match its
    DTO (missing or unknown field, wrong type, bad date). The message names
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
