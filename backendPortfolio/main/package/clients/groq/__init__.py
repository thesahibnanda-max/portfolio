"""
Client for Groq's OpenAI-compatible chat completions API, with a plain call
and a streaming call.

Exports:
    GroqClient: the client.
    GroqChatCompletionStream: the object returned by stream_chat_completion.
    GroqChatCompletionRequest and its parts (GroqMessage, GroqTool,
    GroqToolFunction, and the response formats GroqJsonObjectResponseFormat,
    GroqJsonSchemaResponseFormat with GroqJsonSchema, and the
    GroqResponseFormat alias): the request DTOs.
    GroqChatCompletion and its parts (GroqChoice, GroqResponseMessage,
    GroqDelta, GroqUsage, GroqXGroq, GroqToolCall, GroqFunctionCall): the
    response DTOs, also used for each streamed chunk.
    GroqTextDelta, GroqStreamEnd and the GroqStreamEvent alias: stream events.
    GroqClientError and its subclasses: the errors described under Errors.

Construction:
    GroqClient(
        *,
        base_url,
        api_keys,
        connect_timeout,
        read_timeout,
        write_timeout,
        pool_timeout,
        transport=None,
    )
    base_url: http or https URL with a host and no query or fragment, for
    example "https://api.groq.com". A trailing slash is removed.
    api_keys: non-empty sequence of non-blank API keys. Each request uses one
    picked at random, spreading load across keys like the Java client. Keys
    are kept in a tuple and never appear in a repr or error message.
    connect_timeout, read_timeout, write_timeout, pool_timeout: positive
    timedeltas. read_timeout is the longest gap allowed between two received
    bytes, not a limit on the whole answer, so it stops a stalled stream
    without cutting off a long one.
    transport: optional httpx transport, only for tests.
    Every setting is keyword-only and validated; a bad one raises
    InvalidGroqClientSettingError. The client owns one httpx.Client, so call
    close() when done, or use it as a context manager.

create_chat_completion(request) -> GroqChatCompletion
    POST <base_url>/openai/v1/chat/completions with "stream": false and
    returns the whole completion; the answer is
    completion.choices[0].message.content.

stream_chat_completion(request) -> GroqChatCompletionStream
    Builds the same request with "stream": true and returns a stream object.
    Nothing is sent until the stream is entered:

        with client.stream_chat_completion(request) as stream:
            for event in stream:
                match event:
                    case GroqTextDelta(text=text):
                        send_to_user(text)
                    case GroqStreamEnd(text=full, finish_reason=reason, usage=usage):
                        save(full, reason, usage)

    The "stream" field is set by the method called, never by the request, so
    the body always matches the method.

Stream contract:
    Entering sends the request and checks the HTTP status. A 4xx or 5xx,
    including 429, raises there, before any event, so a caller can still
    answer its own client with a proper error status.
    Iterating pulls Server-Sent Events, parsed by httpx-sse, one at a time
    from the socket: nothing is buffered, and a slow reader slows the upstream
    read. It yields a GroqTextDelta for every non-empty content piece, in
    order. Whitespace-only pieces are kept, so "is 1832" never becomes
    "is1832". Chunks with only a role, empty content or no choices yield
    nothing.
    After the [DONE] marker it yields exactly one GroqStreamEnd with the full
    text, the finish_reason and the usage (from x_groq.usage, or usage), and
    then stops. stream.text, stream.finish_reason, stream.usage,
    stream.completed and stream.cancelled stay readable afterwards.
    A stream that ends without [DONE] raises GroqStreamIncompleteError with
    the partial_text, so a cut-off answer is never taken as complete.
    Leaving the with block always closes the connection, also when the caller
    stops early with break, raises, or its own client disconnects.
    cancel() may be called from any other thread, for example for "stop
    generating" or shutdown. It marks the stream cancelled and shuts down the
    underlying socket, which wakes a reader blocked waiting for data at once;
    the reading thread then raises GroqStreamCancelledError with the
    partial_text and closes the connection itself when it leaves its with
    block. Closing the response from another thread would not wake a blocked
    read, which is why the socket is shut down instead. cancel() after the
    stream finished does nothing.
    A stream is read by one thread and read once: iterating outside its with
    block, entering it twice or iterating again after the end raises
    GroqStreamStateError. Nothing is retried automatically, because repeating
    a request that already streamed text would duplicate output.

Intended use with a frontend (built later):
    A worker thread owns the stream and appends numbered events to a bounded
    per-chat-turn buffer; the HTTP endpoint only reads that buffer as
    Server-Sent Events. GroqTextDelta maps to "event: token", GroqStreamEnd to
    "event: done" (after which the worker saves the answer), and any
    GroqClientError to "event: error". The browser reconnects with
    Last-Event-ID and the endpoint replays from the buffer, so a disconnect
    loses no tokens and never leaves a half-saved answer. "Stop generating"
    calls cancel(). Responses use Content-Type text/event-stream,
    Cache-Control no-cache, X-Accel-Buffering no, and a ": ping" comment every
    15 seconds.

Request DTO (GroqChatCompletionRequest, extra fields rejected):
    messages: at least one GroqMessage (role "system", "user", "assistant" or
    "tool"; content; tool_call_id; tool_calls).
    model: non-empty model id, for example "llama-3.3-70b-versatile".
    temperature (0 to 2), max_completion_tokens (at least 1), top_p (0 to 1),
    stop (up to 4 strings), reasoning_effort and tools (GroqTool with a
    GroqToolFunction) are optional; fields left as None are not sent.
    Invalid values raise pydantic's ValidationError when the request is built.

JSON enforcement (request.response_format):
    GroqJsonSchemaResponseFormat(json_schema=GroqJsonSchema(name=..., schema=..., strict=True))
        Strict JSON Schema mode. Groq constrains decoding so the reply always
        matches the schema. Supported on openai/gpt-oss-20b,
        openai/gpt-oss-120b and qwen/qwen3.8-27b (per Groq's docs). In strict
        mode every property must be listed in "required" and every object
        must set "additionalProperties": false; express optional fields as a
        union with null. name must match ^[a-zA-Z0-9_-]{1,64}$. The schema is
        sent under the key "schema".
        With strict=False it is best effort on the same models (plus
        openai/gpt-oss-safeguard-20b): a reply that does not match makes
        Groq answer HTTP 400 with error code json_validate_failed, raised as
        GroqJsonValidationError.
    GroqJsonObjectResponseFormat()
        JSON object mode, on every model, including llama-3.3-70b-versatile.
        The reply is always valid JSON but its shape is not enforced, so
        validate it (for example with main.package.json_extract). The prompt
        must ask for JSON.
    Groq does not support structured outputs together with streaming or with
    tools: a request with both response_format and tools fails validation
    when it is built, and stream_chat_completion raises
    InvalidGroqRequestError for a request with response_format, before
    anything is sent.

Response DTOs:
    Frozen pydantic models matching Groq's snake_case JSON; unknown fields are
    ignored, every field is optional, and lists are tuples.

Errors (all in exceptions.py, all subclasses of GroqClientError):
    InvalidGroqClientSettingError: a constructor setting is invalid.
    InvalidGroqRequestError: the request is not a GroqChatCompletionRequest,
    or a request with response_format was passed to stream_chat_completion.
    GroqRequestError: the request or stream failed on the network
    (connection error, timeout, dropped stream, or a response that is not an
    event stream); the httpx error is chained as __cause__.
    GroqHTTPStatusError: a non-2xx response, with status_code and body (first
    500 characters).
    GroqRateLimitError: a GroqHTTPStatusError for HTTP 429.
    GroqJsonValidationError: a GroqHTTPStatusError for HTTP 400 with error
    code json_validate_failed (a best-effort json_schema reply that did not
    match). The code is read from the full body, not the shortened one.
    GroqResponseError: the body or a chunk is not valid JSON, does not match
    the DTO shape, or the stream sent an error event.
    GroqStreamIncompleteError: a GroqResponseError for a stream that ended
    without [DONE]; has partial_text.
    GroqStreamCancelledError: the stream was cancelled; has partial_text.
    GroqStreamStateError: the stream was used outside its contract.
    Catch GroqClientError to handle every failure at once.

Thread safety:
    One GroqClient can be shared across threads on the free-threaded Python
    3.14t build: it holds only immutable settings, a tuple of keys and an
    httpx.Client, whose connection pool is thread-safe. Each stream belongs
    to the thread reading it; only cancel() is meant for other threads.

Dependencies:
    httpx, httpx-sse and pydantic. httpx and httpx-sse are pure Python and
    pydantic-core ships a cp314t wheel, so the GIL stays disabled.
"""

from .dto import (
    GroqChatCompletion,
    GroqChatCompletionRequest,
    GroqChoice,
    GroqDelta,
    GroqFunctionCall,
    GroqJsonObjectResponseFormat,
    GroqJsonSchema,
    GroqJsonSchemaResponseFormat,
    GroqMessage,
    GroqResponseFormat,
    GroqResponseMessage,
    GroqStreamEnd,
    GroqStreamEvent,
    GroqTextDelta,
    GroqTool,
    GroqToolCall,
    GroqToolFunction,
    GroqUsage,
    GroqXGroq,
)
from .exceptions import (
    GroqClientError,
    GroqHTTPStatusError,
    GroqJsonValidationError,
    GroqRateLimitError,
    GroqRequestError,
    GroqResponseError,
    GroqStreamCancelledError,
    GroqStreamIncompleteError,
    GroqStreamStateError,
    InvalidGroqClientSettingError,
    InvalidGroqRequestError,
)
from .groq_client import GroqClient
from .groq_stream import GroqChatCompletionStream

__all__ = [
    "GroqClient",
    "GroqChatCompletionStream",
    "GroqChatCompletionRequest",
    "GroqMessage",
    "GroqTool",
    "GroqToolFunction",
    "GroqResponseFormat",
    "GroqJsonObjectResponseFormat",
    "GroqJsonSchemaResponseFormat",
    "GroqJsonSchema",
    "GroqChatCompletion",
    "GroqChoice",
    "GroqResponseMessage",
    "GroqDelta",
    "GroqUsage",
    "GroqXGroq",
    "GroqToolCall",
    "GroqFunctionCall",
    "GroqTextDelta",
    "GroqStreamEnd",
    "GroqStreamEvent",
    "GroqClientError",
    "InvalidGroqClientSettingError",
    "InvalidGroqRequestError",
    "GroqRequestError",
    "GroqHTTPStatusError",
    "GroqRateLimitError",
    "GroqJsonValidationError",
    "GroqResponseError",
    "GroqStreamIncompleteError",
    "GroqStreamCancelledError",
    "GroqStreamStateError",
]
