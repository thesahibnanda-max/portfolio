class JsonExtractorError(Exception):
    pass


class EmptyJsonInputError(JsonExtractorError):
    pass


class JsonExtractionError(JsonExtractorError):
    pass
