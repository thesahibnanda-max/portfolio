import copy
import hashlib
import json
import tomllib
from functools import partial, partialmethod
from pathlib import Path
from types import MappingProxyType

import pytest
from pydantic import ValidationError

import main.package.static
import main.package.static.static as static_module
from main.package.static import (
    InvalidStaticDataError,
    Personality,
    Profile,
    ProfileImage,
    StaticDataError,
    StaticFileNotFoundError,
    StaticLoader,
)
from tests.support import ConcurrentRunner

STATIC_DIR = Path(main.package.static.__file__).parent
PROFILE_PATH = STATIC_DIR / "profile.json"
PERSONALITY_PATH = STATIC_DIR / "personality.json"
IMAGE_PATH = STATIC_DIR / "pfp.jpg"
PYPROJECT_PATH = STATIC_DIR.parents[2] / "pyproject.toml"
PROFILE_JSON = json.loads(PROFILE_PATH.read_text())
PERSONALITY_JSON = json.loads(PERSONALITY_PATH.read_text())
DELETE = object()


class ReadCounter:
    def __init__(self, original) -> None:
        self._original = original
        self.paths: list[Path] = []

    def read(self, path: Path) -> bytes:
        self.paths.append(path)
        return self._original(path)


def _mutated(document: dict, keys: tuple, value: object) -> dict:
    result = copy.deepcopy(document)
    target = result
    for key in keys[:-1]:
        target = target[key]
    if value is DELETE:
        del target[keys[-1]]
    else:
        target[keys[-1]] = value
    return result


def _write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content)
    return path


def _point_at(
    monkeypatch: pytest.MonkeyPatch,
    *,
    profile: Path = PROFILE_PATH,
    personality: Path = PERSONALITY_PATH,
    image: Path = IMAGE_PATH,
) -> None:
    monkeypatch.setattr(static_module, "_PROFILE_PATH", profile)
    monkeypatch.setattr(static_module, "_PERSONALITY_PATH", personality)
    monkeypatch.setattr(static_module, "_PROFILE_IMAGE_PATH", image)


def _read_many(loader: StaticLoader, count: int) -> tuple[int, int]:
    profiles = {id(loader.get_profile()) for _ in range(count)}
    personalities = {id(loader.get_personality()) for _ in range(count)}
    return len(profiles), len(personalities)


@pytest.fixture
def loader() -> StaticLoader:
    return StaticLoader()


def test_loads_profile_from_real_file(loader: StaticLoader) -> None:
    profile = loader.get_profile()

    assert isinstance(profile, Profile)
    assert profile.profile_details.name == PROFILE_JSON["profileDetails"]["name"]
    assert len(profile.projects) == len(PROFILE_JSON["projects"])
    assert all(project.link.startswith("http") for project in profile.projects)
    assert profile.experience[0].start_date == PROFILE_JSON["experience"][0]["startDate"]
    assert profile.experience[0].employment_type == PROFILE_JSON["experience"][0]["employmentType"]
    assert profile.education[0].field == PROFILE_JSON["education"][0]["field"]
    assert profile.skills_by_category["Backend"] == tuple(PROFILE_JSON["skillsByCategory"]["Backend"])
    assert isinstance(profile.projects, tuple)
    assert isinstance(profile.projects[0].technologies, tuple)


def test_loads_personality_from_real_file(loader: StaticLoader) -> None:
    personality = loader.get_personality()
    personal = personality.personal_profile

    assert isinstance(personality, Personality)
    assert personal.basic_info.height.centimeters == 183
    assert personal.physical_appearance.accessories.wears_glasses is True
    assert personal.physical_appearance.face.facial_hair == "Clean-shaven"
    assert personal.interests.sports.football.favorite_team == "FC Barcelona"
    assert personal.favorites.sports_icons.cricket == "Virat Kohli"
    assert personal.lifestyle.continuous_learning is True
    assert personal.languages[0].name == "English"
    assert isinstance(personal.personality.core_traits, tuple)


def test_models_dump_back_to_the_source_json(loader: StaticLoader) -> None:
    assert json.loads(loader.get_profile().model_dump_json(by_alias=True)) == PROFILE_JSON
    assert json.loads(loader.get_personality().model_dump_json(by_alias=True)) == PERSONALITY_JSON
    assert isinstance(loader.get_profile().model_dump()["skills_by_category"], dict)


def test_getters_return_the_same_instance_every_time(loader: StaticLoader) -> None:
    assert loader.get_profile() is loader.get_profile()
    assert loader.get_personality() is loader.get_personality()


def test_files_are_read_once_at_construction_and_never_again(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = ReadCounter(Path.read_bytes)
    monkeypatch.setattr(Path, "read_bytes", partialmethod(counter.read))

    static_loader = StaticLoader()
    assert counter.paths == [PROFILE_PATH, PERSONALITY_PATH, IMAGE_PATH]

    for _ in range(1000):
        static_loader.get_profile()
        static_loader.get_personality()
        static_loader.get_profile_image()

    assert counter.paths == [PROFILE_PATH, PERSONALITY_PATH, IMAGE_PATH]


def test_editing_files_after_construction_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path = _write(tmp_path, "profile.json", PROFILE_PATH.read_text())
    personality_path = _write(tmp_path, "personality.json", PERSONALITY_PATH.read_text())
    _point_at(monkeypatch, profile=profile_path, personality=personality_path)
    static_loader = StaticLoader()

    profile_path.write_text("not json any more")
    personality_path.unlink()

    assert static_loader.get_profile().profile_details.name == PROFILE_JSON["profileDetails"]["name"]
    assert static_loader.get_personality().personal_profile.basic_info.height.feet == 6


def test_reads_the_files_next_to_the_module() -> None:
    assert static_module._PROFILE_PATH == PROFILE_PATH
    assert static_module._PERSONALITY_PATH == PERSONALITY_PATH
    assert static_module._PROFILE_IMAGE_PATH == IMAGE_PATH


def test_works_from_any_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert StaticLoader().get_profile().profile_details.email == PROFILE_JSON["profileDetails"]["email"]


def test_takes_no_arguments() -> None:
    with pytest.raises(TypeError):
        StaticLoader(PROFILE_PATH)


def test_parallel_reads_return_the_same_instances(loader: StaticLoader) -> None:
    runner = ConcurrentRunner(partial(_read_many, loader, 100)).run()

    assert runner.errors == []
    assert runner.results == [(1, 1)] * 16


def test_models_are_frozen(loader: StaticLoader) -> None:
    with pytest.raises(ValidationError):
        loader.get_profile().profile_details.name = "Someone Else"

    with pytest.raises(ValidationError):
        loader.get_personality().personal_profile.lifestyle.fitness_focused = False


def test_skills_by_category_is_read_only(loader: StaticLoader) -> None:
    skills = loader.get_profile().skills_by_category

    assert isinstance(skills, MappingProxyType)
    with pytest.raises(TypeError):
        skills["Backend"] = ("COBOL",)


def test_missing_file_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, profile=tmp_path / "missing.json")

    with pytest.raises(StaticFileNotFoundError, match="missing.json") as error:
        StaticLoader()

    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_missing_personality_file_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, personality=tmp_path / "gone.json")

    with pytest.raises(StaticFileNotFoundError, match="gone.json"):
        StaticLoader()


@pytest.mark.parametrize("content", ["not json", "", "[1, 2]", '{"profileDetails": '])
def test_invalid_profile_json_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    _point_at(monkeypatch, profile=_write(tmp_path, "profile.json", content))

    with pytest.raises(InvalidStaticDataError, match="profile.json") as error:
        StaticLoader()

    assert isinstance(error.value.__cause__, ValidationError)


@pytest.mark.parametrize(
    ("keys", "value", "field"),
    [
        (("profileDetails", "email"), DELETE, "email"),
        (("projects", 0, "link"), DELETE, "link"),
        (("projects", 0, "year"), "soon", "year"),
        (("projects", 0, "stars"), 5, "stars"),
        (("unknownSection",), [], "unknownSection"),
        (("experience", 0, "startDate"), "2026-13", "startDate"),
        (("experience", 0, "startDate"), "Sept 2026", "startDate"),
        (("experience", 0, "startDate"), "Present", "startDate"),
        (("experience", 0, "endDate"), "soon", "endDate"),
        (("education", 0, "endDate"), "2025-5", "endDate"),
        (("skillsByCategory", "Backend"), "Flask", "Backend"),
        (("languages",), "Python", "languages"),
    ],
)
def test_profile_that_breaks_the_schema_raises(tmp_path, monkeypatch, keys: tuple, value: object, field: str) -> None:
    _point_at(monkeypatch, profile=_write(tmp_path, "profile.json", json.dumps(_mutated(PROFILE_JSON, keys, value))))

    with pytest.raises(InvalidStaticDataError, match=field) as error:
        StaticLoader()

    assert "Profile" in str(error.value)


@pytest.mark.parametrize(
    ("keys", "value", "field"),
    [
        (("personalProfile", "basicInfo"), DELETE, "basicInfo"),
        (("personalProfile", "lifestyle", "fitnessFocused"), "sometimes", "fitnessFocused"),
        (("personalProfile", "basicInfo", "height", "centimeters"), "tall", "centimeters"),
        (("personalProfile", "favorites", "movies", 0, "rating"), 5, "rating"),
    ],
)
def test_personality_that_breaks_the_schema_raises(tmp_path, monkeypatch, keys: tuple, value: object, field: str) -> None:
    _point_at(monkeypatch, personality=_write(tmp_path, "personality.json", json.dumps(_mutated(PERSONALITY_JSON, keys, value))))

    with pytest.raises(InvalidStaticDataError, match=field) as error:
        StaticLoader()

    assert "Personality" in str(error.value)


def test_end_date_accepts_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _mutated(PROFILE_JSON, ("education", 0, "endDate"), "Present")
    _point_at(monkeypatch, profile=_write(tmp_path, "profile.json", json.dumps(profile)))

    assert StaticLoader().get_profile().education[0].end_date == "Present"


@pytest.mark.parametrize("error_type", [StaticFileNotFoundError, InvalidStaticDataError])
def test_errors_share_the_static_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, StaticDataError)


def test_loads_the_profile_photo_with_a_content_hash_etag(loader: StaticLoader) -> None:
    image = loader.get_profile_image()
    content = IMAGE_PATH.read_bytes()

    assert isinstance(image, ProfileImage)
    assert image.content == content
    assert image.media_type == "image/jpeg"
    assert image.etag == hashlib.sha256(content).hexdigest()[:16]
    assert loader.get_profile_image() is image


def test_profile_photo_bytes_stay_out_of_repr(loader: StaticLoader) -> None:
    text = repr(loader.get_profile_image())

    assert "content" not in text
    assert loader.get_profile_image().etag in text


def test_profile_is_plain_json_data(loader: StaticLoader) -> None:
    assert "profile_image" not in Profile.model_fields
    assert set(loader.get_profile().model_dump(by_alias=True)) == set(PROFILE_JSON)


def test_missing_profile_photo_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, image=tmp_path / "no-photo.jpg")

    with pytest.raises(StaticFileNotFoundError, match="no-photo.jpg") as error:
        StaticLoader()

    assert isinstance(error.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize("content", [b"", b"\x89PNG\r\n\x1a\n", b"not an image", b"\xff\xd8"])
def test_non_jpeg_profile_photo_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: bytes) -> None:
    path = tmp_path / "pfp.jpg"
    path.write_bytes(content)
    _point_at(monkeypatch, image=path)

    with pytest.raises(InvalidStaticDataError, match="not a JPEG"):
        StaticLoader()


def test_profile_image_rejects_bad_fields() -> None:
    with pytest.raises(ValidationError):
        ProfileImage(content=b"", media_type="image/jpeg", etag="0" * 16)
    with pytest.raises(ValidationError):
        ProfileImage(content=b"\xff\xd8\xff", media_type="text/html", etag="0" * 16)
    with pytest.raises(ValidationError):
        ProfileImage(content=b"\xff\xd8\xff", media_type="image/jpeg", etag="not-hex")


def test_package_data_ships_the_photo() -> None:
    package_data = tomllib.loads(PYPROJECT_PATH.read_text())["tool"]["setuptools"]["package-data"]

    assert "*.jpg" in package_data["main.package.static"]
