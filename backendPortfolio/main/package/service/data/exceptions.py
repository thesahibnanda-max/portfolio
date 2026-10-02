class DataServiceError(Exception):
    pass


class InvalidDataServiceSettingError(DataServiceError):
    pass


class DataSourceUnavailableError(DataServiceError):
    def __init__(self, message: str, *, platform: str, account: str) -> None:
        super().__init__(message)
        self.platform = platform
        self.account = account


class DataSourceResponseError(DataServiceError):
    def __init__(self, message: str, *, platform: str, account: str) -> None:
        super().__init__(message)
        self.platform = platform
        self.account = account
