import {
  processStreamedMessage,
  type ChatLLM,
  type ChatStorage,
  type Message,
  type Thread,
} from "@openuidev/react-headless";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const isThread = (value: unknown): value is Thread =>
  isRecord(value) &&
  typeof value.id === "string" &&
  typeof value.title === "string" &&
  (typeof value.createdAt === "string" || typeof value.createdAt === "number");

const isMessage = (value: unknown): value is Message =>
  isRecord(value) &&
  typeof value.id === "string" &&
  (value.role === "user" || value.role === "assistant") &&
  (typeof value.content === "string" ||
    (Array.isArray(value.content) &&
      value.content.every(
        (part) => isRecord(part) && part.type === "text" && typeof part.text === "string",
      )));

export function localStorageChat(
  llm: ChatLLM,
  key: string,
): { llm: ChatLLM; storage: ChatStorage } {
  const threadsKey = key + ":threads";
  const messagesKey = (id: string) => key + ":messages:" + id;
  const memory = new Map<string, unknown>();
  const deleted = new Set<string>();
  const versions = new Map<string, number>();

  const read = <T>(itemKey: string, fallback: T, valid: (value: unknown) => boolean): T => {
    if (memory.has(itemKey)) return memory.get(itemKey) as T;
    let value: unknown;
    try {
      value = JSON.parse(localStorage.getItem(itemKey) ?? "null");
    } catch {
      /* Private browsing, corrupt data, and quota failures must not break chat. */
    }
    const result = valid(value) ? (value as T) : fallback;
    memory.set(itemKey, result);
    return result;
  };
  const write = (itemKey: string, value: unknown) => {
    memory.set(itemKey, value);
    try {
      localStorage.setItem(itemKey, JSON.stringify(value));
    } catch {
      /* In-memory fallback. */
    }
  };
  const threads = () =>
    read<Thread[]>(threadsKey, [], (value) => Array.isArray(value) && value.every(isThread));

  const send: ChatLLM["send"] = async (params) => {
    const { threadId } = params;
    const version = (versions.get(threadId) ?? 0) + 1;
    versions.set(threadId, version);
    const reply = new Map<string, Message>();
    const persist = () => {
      if (!deleted.has(threadId) && versions.get(threadId) === version)
        write(messagesKey(threadId), [...params.messages, ...reply.values()]);
    };
    persist();
    const response = await llm.send(params);
    if (!response.ok || !response.body) return response;
    const [forChat, forStorage] = response.body.tee();
    const keep = (message: Message) => {
      reply.set(message.id, message);
      persist();
    };
    void processStreamedMessage({
      response: new Response(forStorage, response),
      createMessage: keep,
      updateMessage: keep,
      adapter: {
        async *parse(storageResponse) {
          try {
            yield* llm.streamProtocol.parse(storageResponse);
          } catch {
            /* Flush received partial text; the UI's independent branch surfaces errors. */
          }
        },
      },
    })
      .catch(() => {})
      .finally(persist);
    return new Response(forChat, response);
  };

  return {
    llm: { ...llm, send },
    storage: {
      thread: {
        async listThreads() {
          return { threads: threads() };
        },
        async createThread(firstMessage) {
          const title = typeof firstMessage.content === "string" ? firstMessage.content.trim() : "";
          const thread: Thread = {
            id: crypto.randomUUID(),
            title: title.slice(0, 60) || "New chat",
            createdAt: Date.now(),
          };
          write(threadsKey, [thread, ...threads()]);
          return thread;
        },
        async getMessages(id) {
          if (deleted.has(id)) return [];
          return read<Message[]>(
            messagesKey(id),
            [],
            (value) => Array.isArray(value) && value.every(isMessage),
          );
        },
        async updateThread(thread) {
          write(
            threadsKey,
            threads().map((item) => (item.id === thread.id ? thread : item)),
          );
          return thread;
        },
        async deleteThread(id) {
          deleted.add(id);
          write(
            threadsKey,
            threads().filter((thread) => thread.id !== id),
          );
          memory.delete(messagesKey(id));
          try {
            localStorage.removeItem(messagesKey(id));
          } catch {
            /* In-memory deletion still applies. */
          }
        },
      },
    },
  };
}
