import hashlib
from pathlib import Path

from pydantic import BaseModel, ValidationError

from main.package.static.dto import CliManifest, Personality, Profile, StaticAsset
from main.package.static.exceptions import InvalidStaticDataError, StaticFileNotFoundError

_PROFILE_PATH = Path(__file__).with_name("profile.json")
_PERSONALITY_PATH = Path(__file__).with_name("personality.json")
_PROFILE_IMAGE_PATH = Path(__file__).with_name("pfp.jpg")
_RESUME_PATH = Path(__file__).with_name("resume.pdf")
_CLI_PATH = Path(__file__).with_name("cli.json")
_FORTUNES_PATH = Path(__file__).with_name("fortunes.md")
_FORTUNE_PREFIX = "- "
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_JPEG_MEDIA_TYPE = "image/jpeg"
_PDF_SIGNATURE = b"%PDF-"
_PDF_MEDIA_TYPE = "application/pdf"
_ETAG_LENGTH = 16


class StaticLoader:
    def __init__(self) -> None:
        self._profile = self._load(_PROFILE_PATH, Profile)
        self._personality = self._load(_PERSONALITY_PATH, Personality)
        self._profile_image = self._load_asset(_PROFILE_IMAGE_PATH, _JPEG_SIGNATURE, _JPEG_MEDIA_TYPE)
        self._resume = self._load_asset(_RESUME_PATH, _PDF_SIGNATURE, _PDF_MEDIA_TYPE)
        self._cli_manifest = self._load(_CLI_PATH, CliManifest)
        self._fortunes = self._load_fortunes(_FORTUNES_PATH)

    def get_profile(self) -> Profile:
        return self._profile

    def get_personality(self) -> Personality:
        return self._personality

    def get_profile_image(self) -> StaticAsset:
        return self._profile_image

    def get_resume(self) -> StaticAsset:
        return self._resume

    def get_cli_manifest(self) -> CliManifest:
        return self._cli_manifest

    def get_fortunes(self) -> tuple[str, ...]:
        return self._fortunes

    @staticmethod
    def _load_fortunes(path: Path) -> tuple[str, ...]:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise StaticFileNotFoundError(f"Static file not found: {path}") from error

        fortunes = tuple(
            line.strip().removeprefix(_FORTUNE_PREFIX).strip()
            for line in text.splitlines()
            if line.strip().startswith(_FORTUNE_PREFIX) and line.strip().removeprefix(_FORTUNE_PREFIX).strip()
        )
        if not fortunes:
            raise InvalidStaticDataError(f"Static file {path} has no '- ' fortune lines")

        return fortunes

    @staticmethod
    def _load_asset(path: Path, signature: bytes, media_type: str) -> StaticAsset:
        try:
            content = path.read_bytes()
        except FileNotFoundError as error:
            raise StaticFileNotFoundError(f"Static file not found: {path}") from error

        if not content.startswith(signature):
            raise InvalidStaticDataError(f"Static file {path} is not a valid {media_type} file")

        return StaticAsset(
            content=content,
            media_type=media_type,
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
