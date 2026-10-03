from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel

YearMonth = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
YearMonthOrPresent = Annotated[str, Field(pattern=r"^(\d{4}-(0[1-9]|1[0-2])|Present)$")]


def _freeze_mapping(value: Mapping[str, tuple[str, ...]]) -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType(dict(value))


def _thaw_mapping(value: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    return dict(value)


class _StaticModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
    )


class ProfileDetails(_StaticModel):
    name: str
    email: str


class Project(_StaticModel):
    name: str
    year: int
    link: str
    description: tuple[str, ...]
    technologies: tuple[str, ...]


class Experience(_StaticModel):
    company: str
    location: str
    employment_type: str
    title: str
    start_date: YearMonth
    end_date: YearMonthOrPresent
    description: tuple[str, ...]
    technologies: tuple[str, ...]


class Education(_StaticModel):
    institution: str
    degree: str
    field: str
    start_date: YearMonth
    end_date: YearMonthOrPresent
    grade: str


class Profile(_StaticModel):
    profile_details: ProfileDetails
    projects: tuple[Project, ...]
    languages: tuple[str, ...]
    achievements: tuple[str, ...]
    experience: tuple[Experience, ...]
    education: tuple[Education, ...]
    skills_by_category: Annotated[
        Mapping[str, tuple[str, ...]],
        AfterValidator(_freeze_mapping),
        PlainSerializer(_thaw_mapping, return_type=dict[str, tuple[str, ...]]),
    ]


class Height(_StaticModel):
    feet: int
    centimeters: int


class BasicInfo(_StaticModel):
    nationality: str
    gender: str
    height: Height


class Hair(_StaticModel):
    color: str
    texture: str
    style: str


class Eyes(_StaticModel):
    color: str


class Face(_StaticModel):
    shape: str
    eyebrows: str
    facial_hair: str


class Accessories(_StaticModel):
    wears_glasses: bool


class Fashion(_StaticModel):
    style: str
    favorite_colors: tuple[str, ...]


class PhysicalAppearance(_StaticModel):
    body_type: str
    physique: str
    fitness_level: str
    strongest_muscle_group: str
    fitness_goals: tuple[str, ...]
    hair: Hair
    eyes: Eyes
    skin_tone: str
    face: Face
    accessories: Accessories
    fashion: Fashion


class WorkPreferences(_StaticModel):
    preferred_domains: tuple[str, ...]
    engineering_values: tuple[str, ...]


class PersonalityTraits(_StaticModel):
    core_traits: tuple[str, ...]
    professional_traits: tuple[str, ...]
    work_preferences: WorkPreferences
    personal_values: tuple[str, ...]


class SportFavorite(_StaticModel):
    favorite_team: str
    favorite_player: str


class Sports(_StaticModel):
    football: SportFavorite
    cricket: SportFavorite


class Interests(_StaticModel):
    sports: Sports
    fitness: tuple[str, ...]
    technology: tuple[str, ...]


class TitledFavorite(_StaticModel):
    title: str
    genre: str


class Artist(_StaticModel):
    name: str
    type: str


class SportsIcons(_StaticModel):
    football: str
    cricket: str


class Favorites(_StaticModel):
    movies: tuple[TitledFavorite, ...]
    games: tuple[TitledFavorite, ...]
    artists: tuple[Artist, ...]
    sports_icons: SportsIcons


class Lifestyle(_StaticModel):
    fitness_focused: bool
    sports_enthusiast: bool
    technology_enthusiast: bool
    continuous_learning: bool


class SpokenLanguage(_StaticModel):
    name: str
    proficiency: str


class PersonalProfile(_StaticModel):
    basic_info: BasicInfo
    physical_appearance: PhysicalAppearance
    personality: PersonalityTraits
    interests: Interests
    favorites: Favorites
    lifestyle: Lifestyle
    languages: tuple[SpokenLanguage, ...]


class Personality(_StaticModel):
    personal_profile: PersonalProfile


class ProfileImage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content: Annotated[bytes, Field(min_length=1, repr=False)]
    media_type: Annotated[str, Field(pattern=r"^image/[a-z0-9.+-]+$")]
    etag: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
