import { AgentInterface } from "@openuidev/react-ui";
import { openuiLibrary } from "./library";
import { createChatLLM } from "./lib/chat";
import { localStorageChat } from "./lib/local-storage";

const { llm, storage } = localStorageChat(createChatLLM(), "pdf-rag-openui");

export default function App() {
  return (
    <div className="h-screen w-screen overflow-hidden">
      <AgentInterface
        llm={llm}
        storage={storage}
        componentLibrary={openuiLibrary}
        agentName="OpenUI Chat"
      />
    </div>
  );
}
