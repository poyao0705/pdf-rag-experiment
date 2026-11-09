import { render, screen } from "@testing-library/react";
import { AgentInterface } from "@openuidev/react-ui";
import { expect, it, vi } from "vite-plus/test";
import { openuiLibrary } from "./library";
import App from "./App";

vi.mock("@openuidev/react-ui", () => ({
  AgentInterface: vi.fn(() => <div data-testid="agent-interface" />),
}));

it("wires the real OpenUI library, transport and storage into the full-screen interface", () => {
  render(<App />);
  const props = vi.mocked(AgentInterface).mock.calls[0]?.[0];
  expect(props?.componentLibrary).toBe(openuiLibrary);
  expect(typeof props?.llm?.send).toBe("function");
  expect(typeof props?.storage?.thread.getMessages).toBe("function");
  expect(screen.getByTestId("agent-interface").parentElement?.className).toBe(
    "h-screen w-screen overflow-hidden",
  );
});
