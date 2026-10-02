from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CodeforcesModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
    )


class CodeforcesRatingChange(_CodeforcesModel):
    contest_id: int | None = None
    contest_name: str | None = None
    handle: str | None = None
    rank: int | None = None
    rating_update_time_seconds: int | None = None
    old_rating: int | None = None
    new_rating: int | None = None


class CodeforcesUserRatingResponse(_CodeforcesModel):
    status: str | None = None
    comment: str | None = None
    result: tuple[CodeforcesRatingChange, ...] | None = None
