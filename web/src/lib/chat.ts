import {
  fetchLLM,
  openAIMessageFormat,
  openAIReadableStreamAdapter,
  type ChatLLM,
  type StreamProtocolAdapter,
} from "@openuidev/react-headless";

/** Validate only framing/errors; leave all normal chat events to OpenUI's adapter. */
async function* checkedRecords(response: Response): AsyncGenerator<Uint8Array> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No chat response body");
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";
  let completed = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = done ? "" : (lines.pop() ?? "");
      for (const line of lines) {
        if (!line.trim()) continue;
        let record;
        try {
          record = JSON.parse(line);
        } catch {
          throw new Error("Invalid chat response");
        }
        if (record?.error) {
          throw new Error(
            typeof record.error.message === "string" ? record.error.message : "Chat stream failed",
          );
        }
        if (record?.choices?.[0]?.finish_reason === "stop") completed = true;
        yield encoder.encode(line + "\n");
      }
      if (done) break;
    }
    if (!completed) throw new Error("Chat response ended before completion");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function checkedAdapter(): StreamProtocolAdapter {
  const adapter = openAIReadableStreamAdapter();
  return {
    async *parse(response) {
      const records = checkedRecords(response);
      const body = new ReadableStream<Uint8Array>(
        {
          async pull(controller) {
            try {
              const next = await records.next();
              if (next.done) controller.close();
              else controller.enqueue(next.value);
            } catch (error) {
              controller.error(error);
            }
          },
          async cancel() {
            await records.return(undefined);
          },
        },
        { highWaterMark: 0 },
      );
      try {
        yield* adapter.parse(new Response(body, response));
      } finally {
        await records.return(undefined);
      }
    },
  };
}

export function createChatLLM(): ChatLLM {
  const llm = fetchLLM({
    url: "/api/chat",
    messageFormat: openAIMessageFormat,
    streamAdapter: checkedAdapter(),
  });
  return {
    ...llm,
    async send(params) {
      const response = await llm.send(params);
      if (!response.ok) {
        const body = await response
          .clone()
          .json()
          .catch(() => null);
        if (typeof body?.detail === "string") throw new Error(body.detail);
      }
      return response;
    },
  };
}
