class WorkerError(Exception):
    pass


class InvalidWorkerSettingError(WorkerError):
    pass


class InvalidWorkerInputError(WorkerError):
    pass


class WorkerResponseError(WorkerError):
    pass
