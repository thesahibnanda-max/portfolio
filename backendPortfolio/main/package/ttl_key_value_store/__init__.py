"""
A key-value store whose entries expire at a set time, behind one interface
so the backing storage can be swapped without touching the code that uses it.

Exports:
    TTLKeyValueStore: the interface (an ABC) every implementation follows.
    TTLKeyValueStoreImpl: a StrEnum naming the available implementations.
    TTLKeyValueStoreFactory: builds the implementation chosen by the enum.
    TTLKeyValueStoreError and its subclasses: the errors described under
    Errors.

Interface:
    get(key) returns the value, or None if the key is missing or expired.
    set(key, value, expires_at) stores or overwrites an entry.
    set_if_absent(key, value, expires_at) stores the entry only if the key is
    missing or expired, and returns True if it stored it. The check and the
    write happen as one atomic step, so when many threads race on one key,
    exactly one gets True. This maps to Redis SET key value NX EXAT <epoch>
    and to a DynamoDB conditional put with attribute_not_exists.
    delete(key) removes an entry; a missing key is not an error.
    close() releases resources such as background threads or connections.

    Values are strings. expires_at is an absolute, timezone-aware datetime
    (use UTC); a naive datetime or an empty key raises
    InvalidTTLKeyValueEntryError.

Factory:
    factory = TTLKeyValueStoreFactory(
        {TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=20)},
    )
    store = factory.get_ttl_key_value_store(TTLKeyValueStoreImpl.IN_MEMORY)

    The factory keeps a registry that maps each enum member to its class.
    Its constructor takes a map from each enum member to that
    implementation's sweep interval: how often expired entries are cleaned
    up. It controls memory only; each entry's own expiry comes from
    expires_at.

    The constructor builds every registered implementation once, passing
    each its own interval from the map, and keeps them in a map by enum
    member. It raises MissingSweepIntervalError if any registered
    implementation is missing from the interval map, and
    UnsupportedTTLKeyValueStoreImplError if the map names an implementation
    that is not registered.

    get_ttl_key_value_store(impl) returns the instance for that enum member,
    the same instance on every call, and raises
    UnsupportedTTLKeyValueStoreImplError for an unsupported impl.

    close_all() closes every store the factory created, which stops each
    in-memory sweeper thread. Calling it more than once is safe.

In-memory implementation:
    A private class backed by a dict guarded by a threading.Lock, so it is
    safe to call from many threads at once on the free-threaded Python 3.14t
    build, including FastAPI's thread pool.

    Expired entries are treated as absent on every read, so correctness never
    depends on cleanup. To keep memory bounded, a daemon OS thread wakes
    once per sweep interval and removes expired entries. The interval must
    be a positive timedelta, otherwise InvalidSweepIntervalError. It catches and logs any
    error inside each pass, so it keeps running. close() stops it.

    Limits: the data lives in one process. With several workers or servers,
    each has its own copy, and a restart loses everything.

FastAPI usage:
    Create the factory once at startup and call factory.close_all() after
    the yield in the lifespan, so it runs on shutdown:

        @asynccontextmanager
        async def lifespan(app):
            factory = TTLKeyValueStoreFactory(
                {TTLKeyValueStoreImpl.IN_MEMORY: timedelta(minutes=20)},
            )
            app.state.store = factory.get_ttl_key_value_store(
                TTLKeyValueStoreImpl.IN_MEMORY
            )
            yield
            factory.close_all()

        app = FastAPI(lifespan=lifespan)

    If close_all is never called, the sweeper is a daemon thread, so it does
    not block the process from exiting.

Adding Redis or DynamoDB:
    Add a member to TTLKeyValueStoreImpl, write a class that implements
    TTLKeyValueStore and whose constructor takes the sweep interval as a
    timedelta, register it in TTLKeyValueStoreFactory._IMPLS, and add its
    interval to the map passed to the factory. Redis and DynamoDB expire
    keys themselves, so they can accept the interval and need no sweeper.

Errors (all in exceptions.py, all subclasses of TTLKeyValueStoreError):
    UnsupportedTTLKeyValueStoreImplError: an impl name that is not
    registered, in the interval map or in get_ttl_key_value_store.
    MissingSweepIntervalError: a registered impl has no interval in the map.
    InvalidSweepIntervalError: an interval that is not a positive timedelta.
    InvalidTTLKeyValueEntryError: an empty key or a naive expires_at.
    Catch TTLKeyValueStoreError to handle every store failure at once.
    Errors inside the in-memory sweeper are logged, not raised, so the
    sweeper keeps running.

Dependencies:
    Standard library only, so the GIL stays disabled.
"""

from .exceptions import (
    InvalidSweepIntervalError,
    InvalidTTLKeyValueEntryError,
    MissingSweepIntervalError,
    TTLKeyValueStoreError,
    UnsupportedTTLKeyValueStoreImplError,
)
from .ttl_key_value_store import TTLKeyValueStore, TTLKeyValueStoreImpl
from .ttl_key_value_store_factory import TTLKeyValueStoreFactory

__all__ = [
    "TTLKeyValueStore",
    "TTLKeyValueStoreImpl",
    "TTLKeyValueStoreFactory",
    "TTLKeyValueStoreError",
    "UnsupportedTTLKeyValueStoreImplError",
    "MissingSweepIntervalError",
    "InvalidSweepIntervalError",
    "InvalidTTLKeyValueEntryError",
]
