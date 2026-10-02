class StaticDataError(Exception):
    pass


class StaticFileNotFoundError(StaticDataError):
    pass


class InvalidStaticDataError(StaticDataError):
    pass
