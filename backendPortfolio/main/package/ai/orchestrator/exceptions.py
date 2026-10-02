class OrchestratorError(Exception):
    pass


class InvalidOrchestratorSettingError(OrchestratorError):
    pass


class InvalidOrchestratorInputError(OrchestratorError):
    pass


class OrchestratorResponseError(OrchestratorError):
    pass
