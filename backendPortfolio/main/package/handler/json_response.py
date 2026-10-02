from pydantic import BaseModel
from starlette.responses import Response


class PydanticJSONResponse(Response):
    media_type = "application/json"

    def render(self, content: BaseModel) -> bytes:
        return content.__pydantic_serializer__.to_json(content)
