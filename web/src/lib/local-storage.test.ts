import { afterEach, beforeEach, expect, it, vi } from "vite-plus/test";
import { processStreamedMessage, type UserMessage } from "@openuidev/react-headless";
import { createChatLLM } from "./chat";
import { localStorageChat } from "./local-storage";

const user: UserMessage = { id: "u", role: "user", content: "First question" };
const line = (delta: object, finish: string | null = null) =>
  JSON.stringify({ choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n";
beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function setup() {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          line({ role: "assistant" }) + line({ content: "saved reply" }) + line({}, "stop"),
        ),
      ),
  );
  return localStorageChat(createChatLLM(), "test-chat");
}

it("creates lists renames deletes and reopens isolated threads", async () => {
  const { storage } = setup();
  const first = await storage.thread.createThread(user);
  const second = await storage.thread.createThread({ ...user, id: "u2", content: "Second" });
  await storage.thread.updateThread({ ...first, title: "Renamed" });
  expect((await storage.thread.listThreads()).threads.map((t) => t.title)).toEqual([
    "Second",
    "Renamed",
  ]);
  expect(await storage.thread.getMessages(second.id)).toEqual([]);
  const reopened = localStorageChat(createChatLLM(), "test-chat");
  expect((await reopened.storage.thread.listThreads()).threads).toHaveLength(2);
  await storage.thread.deleteThread(first.id);
  expect((await storage.thread.listThreads()).threads).toHaveLength(1);
});

it("persists the streamed assistant and restores complete history", async () => {
  const { llm, storage } = setup();
  const thread = await storage.thread.createThread(user);
  const response = await llm.send({
    threadId: thread.id,
    messages: [user],
    signal: new AbortController().signal,
  });
  await processStreamedMessage({
    response,
    adapter: llm.streamProtocol,
    createMessage() {},
    updateMessage() {},
  });
  await vi.waitFor(async () =>
    expect((await storage.thread.getMessages(thread.id)).at(-1)).toMatchObject({
      role: "assistant",
      content: "saved reply",
    }),
  );
  const reopened = localStorageChat(createChatLLM(), "test-chat");
  expect(await reopened.storage.thread.getMessages(thread.id)).toHaveLength(2);
});

it.each(["{bad", "{}", '[{"id":7}]'])("tolerates corrupt stored thread data %s", async (raw) => {
  localStorage.setItem("test-chat:threads", raw);
  expect((await setup().storage.thread.listThreads()).threads).toEqual([]);
});

it("falls back to memory when localStorage access is denied", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("denied");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  const { llm, storage } = setup();
  const thread = await storage.thread.createThread(user);
  expect((await storage.thread.listThreads()).threads).toHaveLength(1);
  const response = await llm.send({
    threadId: thread.id,
    messages: [user],
    signal: new AbortController().signal,
  });
  expect(response.ok).toBe(true);
  await processStreamedMessage({
    response,
    adapter: llm.streamProtocol,
    createMessage() {},
    updateMessage() {},
  });
});

it("does not resurrect deleted messages when an active stream finishes", async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            controller = c;
          },
        }),
      ),
    ),
  );
  const { llm, storage } = localStorageChat(createChatLLM(), "test-chat");
  const thread = await storage.thread.createThread(user);
  const response = await llm.send({
    threadId: thread.id,
    messages: [user],
    signal: new AbortController().signal,
  });
  const consumed = processStreamedMessage({
    response,
    adapter: llm.streamProtocol,
    createMessage() {},
    updateMessage() {},
  });
  await storage.thread.deleteThread(thread.id);
  controller.enqueue(new TextEncoder().encode(line({ content: "late" }) + line({}, "stop")));
  controller.close();
  await consumed;
  await vi.waitFor(async () => expect(await storage.thread.getMessages(thread.id)).toEqual([]));
  expect(localStorage.getItem("test-chat:messages:" + thread.id)).toBeNull();
});
