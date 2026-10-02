class ConfigError(Exception):
    pass


class ConfigFileNotFoundError(ConfigError):
    pass


class MissingEnvironmentVariableError(ConfigError):
    pass


class InvalidConfigError(ConfigError):
    pass
