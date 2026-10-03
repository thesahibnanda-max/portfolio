class AgentServiceError(Exception):
    pass


class InvalidAgentServiceSettingError(AgentServiceError):
    pass


class AgentBudgetExhaustedError(AgentServiceError):
    pass
