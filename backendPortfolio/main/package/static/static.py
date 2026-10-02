from pathlib import Path

from pydantic import BaseModel, ValidationError

from main.package.static.dto import Personality, Profile
from main.package.static.exceptions import InvalidStaticDataError, StaticFileNotFoundError

_PROFILE_PATH = Path(__file__).with_name("profile.json")
_PERSONALITY_PATH = Path(__file__).with_name("personality.json")


class StaticLoader:
    def __init__(self) -> None:
        self._profile = self._load(_PROFILE_PATH, Profile)
        self._personality = self._load(_PERSONALITY_PATH, Personality)

    def get_profile(self) -> Profile:
        return self._profile

    def get_personality(self) -> Personality:
        return self._personality

    @staticmethod
    def _load[T: BaseModel](path: Path, model: type[T]) -> T:
        try:
            content = path.read_bytes()
        except FileNotFoundError as error:
            raise StaticFileNotFoundError(f"Static file not found: {path}") from error

        try:
            return model.model_validate_json(content)
        except ValidationError as error:
            raise InvalidStaticDataError(f"Static file {path} is not a valid {model.__name__}: {error}") from error
