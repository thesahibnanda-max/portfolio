import { EventSourceParserStream } from "eventsource-parser/stream";
import type { z } from "zod";
import type { ApiClient } from "./client";
import { ApiError, InvalidResponseError } from "./errors";
import {
  type ChatReply,
  chatReplySchema,
  envelopeSchema,
  errorResponseSchema,
  streamStepSchema,
  streamTokenSchema,
} from "./schemas";

export type ChatStreamEvent =
  | { readonly type: "token"; readonly text: string }
  | { readonly type: "done"; readonly reply: ChatReply }
  | { readonly type: "error"; readonly error: ApiError };

export type AgentStreamEvent = ChatStreamEvent | { readonly type: "step"; readonly label: string };

const doneSchema = envelopeSchema(chatReplySchema);

export async function* streamChatMessage(
  client: ApiClient,
  sessionId: string,
  chatId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent, void, undefined> {
  for await (const event of streamEvents(
    client,
    `/chats/${encodeURIComponent(chatId)}/messages/stream`,
    sessionId,
    message,
    signal,
  )) {
    if (event.type !== "step") {
      yield event;
    }
  }
}

export function streamAgentMessage(
  client: ApiClient,
  sessionId: string,
  chatId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<AgentStreamEvent, void, undefined> {
  return streamEvents(client, `/chats/${encodeURIComponent(chatId)}/agent/stream`, sessionId, message, signal);
}

async function* streamEvents(
  client: ApiClient,
  path: string,
  sessionId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<AgentStreamEvent, void, undefined> {
  const response = await client.send(path, {
    method: "POST",
    body: { message },
    sessionId,
    signal,
  });
  if (response.body === null) {
    throw new InvalidResponseError("The chat stream has no body");
  }

  const events = response.body.pipeThrough(new TextDecoderStream()).pipeThrough(new EventSourceParserStream());
  let finished = false;
  for await (const event of events) {
    const parsed = toChatStreamEvent(event.event, event.data);
    if (parsed === null) {
      continue;
    }
    yield parsed;
    if (parsed.type !== "token" && parsed.type !== "step") {
      finished = true;
      break;
    }
  }

  if (!finished && signal?.aborted !== true) {
    throw new InvalidResponseError("The chat stream ended before the answer was complete");
  }
}

export function toChatStreamEvent(name: string | undefined, data: string): AgentStreamEvent | null {
  const payload = parseJson(data);
  switch (name) {
    case "step":
      return { type: "step", label: validate(streamStepSchema, payload, name).label };
    case "token":
      return { type: "token", text: validate(streamTokenSchema, payload, name).text };
    case "done":
      return { type: "done", reply: validate(doneSchema, payload, name).data };
    case "error":
      return { type: "error", error: new ApiError(validate(errorResponseSchema, payload, name), null) };
    default:
      return null;
  }
}

function parseJson(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch (error) {
    throw new InvalidResponseError("A chat stream event is not JSON", { cause: error });
  }
}

function validate<T extends z.ZodType>(schema: T, payload: unknown, name: string): z.infer<T> {
  const result = schema.safeParse(payload);
  if (!result.success) {
    throw new InvalidResponseError(`Invalid "${name}" chat stream event`, { cause: result.error });
  }
  return result.data;
}
