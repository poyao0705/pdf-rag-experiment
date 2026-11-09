import { afterEach, describe, expect, it, vi } from "vite-plus/test";
import { EventType, type UserMessage } from "@openuidev/react-headless";
import { createChatLLM } from "./chat";

export const line = (delta: object, finish: string | null = null) =>
  JSON.stringify({
    id: "chatcmpl-test",
    object: "chat.completion.chunk",
    created: 0,
    model: "test",
    choices: [{ index: 0, delta, finish_reason: finish }],
  }) + "\n";

const input: UserMessage[] = [{ id: "user", role: "user", content: "hello" }];
afterEach(() => vi.unstubAllGlobals());

describe("OpenUI chat transport", () => {
  it("sends formatter history and abort signal and renders before EOF", async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c;
      },
    });
    const fetch = vi.fn().mockResolvedValue(new Response(body));
    vi.stubGlobal("fetch", fetch);
    const llm = createChatLLM();
    const signal = new AbortController().signal;
    const response = await llm.send({ threadId: "thread", messages: input, signal });
    expect(fetch.mock.calls[0]?.[0]).toBe("/api/chat");
    const options = fetch.mock.calls[0]?.[1];
    expect(options.signal).toBe(signal);
    expect(JSON.parse(options.body).messages).toEqual([{ role: "user", content: "hello" }]);
    const events = llm.streamProtocol.parse(response)[Symbol.asyncIterator]();
    controller.enqueue(
      new TextEncoder().encode(line({ role: "assistant" }) + line({ content: "incremental" })),
    );
    expect((await events.next()).value?.type).toBe(EventType.TEXT_MESSAGE_START);
    expect((await events.next()).value).toMatchObject({
      type: EventType.TEXT_MESSAGE_CONTENT,
      delta: "incremental",
    });
    controller.enqueue(new TextEncoder().encode(line({}, "stop")));
    controller.close();
    expect((await events.next()).value?.type).toBe(EventType.TEXT_MESSAGE_END);
    expect((await events.next()).done).toBe(true);
  });

  it("handles split UTF-8/JSON and a final record without newline", async () => {
    const bytes = new TextEncoder().encode(
      line({ role: "assistant" }) + line({ content: "你好 🌍" }) + line({}, "stop").trimEnd(),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          new ReadableStream({
            start(c) {
              for (const byte of bytes) c.enqueue(new Uint8Array([byte]));
              c.close();
            },
          }),
        ),
      ),
    );
    const llm = createChatLLM();
    const response = await llm.send({
      threadId: "t",
      messages: input,
      signal: new AbortController().signal,
    });
    const events = [];
    for await (const event of llm.streamProtocol.parse(response)) events.push(event);
    expect(events).toContainEqual(expect.objectContaining({ delta: "你好 🌍" }));
    expect(events.at(-1)?.type).toBe(EventType.TEXT_MESSAGE_END);
  });

  it("surfaces safe FastAPI HTTP error details", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(Response.json({ detail: "Model request timed out" }, { status: 504 })),
    );
    await expect(
      createChatLLM().send({
        threadId: "t",
        messages: input,
        signal: new AbortController().signal,
      }),
    ).rejects.toThrow("Model request timed out");
  });

  it("surfaces midstream error records and preserves earlier content", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            line({ content: "partial" }) +
              JSON.stringify({ error: { message: "Safe stream failure", type: "stream_error" } }) +
              "\n",
          ),
        ),
    );
    const llm = createChatLLM();
    const response = await llm.send({
      threadId: "t",
      messages: input,
      signal: new AbortController().signal,
    });
    const events = llm.streamProtocol.parse(response)[Symbol.asyncIterator]();
    expect((await events.next()).value?.type).toBe(EventType.TEXT_MESSAGE_START);
    expect((await events.next()).value).toMatchObject({ delta: "partial" });
    await expect(events.next()).rejects.toThrow("Safe stream failure");
  });

  it("does not treat abrupt EOF as successful completion", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(line({ content: "partial" }))));
    const llm = createChatLLM();
    const response = await llm.send({
      threadId: "t",
      messages: input,
      signal: new AbortController().signal,
    });
    await expect(async () => {
      for await (const _event of llm.streamProtocol.parse(response)) {
        /* consume */
      }
    }).rejects.toThrow("before completion");
  });
});
