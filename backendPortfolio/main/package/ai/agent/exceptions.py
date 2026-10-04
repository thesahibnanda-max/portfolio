class AgentError(Exception):
    pass


class InvalidAgentSettingError(AgentError):
    pass


class InvalidAgentInputError(AgentError):
    pass


class AgentStreamStateError(AgentError):
    pass


class AgentResponseError(AgentError):
    pass
