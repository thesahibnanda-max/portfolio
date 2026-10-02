class TTLKeyValueStoreError(Exception):
    pass


class UnsupportedTTLKeyValueStoreImplError(TTLKeyValueStoreError):
    pass


class MissingSweepIntervalError(TTLKeyValueStoreError):
    pass


class InvalidSweepIntervalError(TTLKeyValueStoreError):
    pass


class InvalidTTLKeyValueEntryError(TTLKeyValueStoreError):
    pass
