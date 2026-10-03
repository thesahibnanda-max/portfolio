import hashlib
from pathlib import Path

from pydantic import BaseModel, ValidationError

from main.package.static.dto import Personality, Profile, ProfileImage
from main.package.static.exceptions import InvalidStaticDataError, StaticFileNotFoundError

_PROFILE_PATH = Path(__file__).with_name("profile.json")
_PERSONALITY_PATH = Path(__file__).with_name("personality.json")
_PROFILE_IMAGE_PATH = Path(__file__).with_name("pfp.jpg")
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_JPEG_MEDIA_TYPE = "image/jpeg"
_ETAG_LENGTH = 16


class StaticLoader:
    def __init__(self) -> None:
        self._profile = self._load(_PROFILE_PATH, Profile)
        self._personality = self._load(_PERSONALITY_PATH, Personality)
        self._profile_image = self._load_jpeg(_PROFILE_IMAGE_PATH)

    def get_profile(self) -> Profile:
        return self._profile

    def get_personality(self) -> Personality:
        return self._personality

    def get_profile_image(self) -> ProfileImage:
        return self._profile_image

    @staticmethod
    def _load_jpeg(path: Path) -> ProfileImage:
        try:
            content = path.read_bytes()
        except FileNotFoundError as error:
            raise StaticFileNotFoundError(f"Static file not found: {path}") from error

        if not content.startswith(_JPEG_SIGNATURE):
            raise InvalidStaticDataError(f"Static file {path} is not a JPEG image")

        return ProfileImage(
            content=content,
            media_type=_JPEG_MEDIA_TYPE,
            etag=hashlib.sha256(content).hexdigest()[:_ETAG_LENGTH],
        )

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
