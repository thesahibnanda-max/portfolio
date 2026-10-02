class RepositoryError(Exception):
    pass


class InvalidRepositorySettingError(RepositoryError):
    pass


class InvalidRepositoryArgumentError(RepositoryError):
    pass


class SessionNotFoundError(RepositoryError):
    pass


class ChatNotFoundError(RepositoryError):
    pass


class RepositoryOperationError(RepositoryError):
    pass
