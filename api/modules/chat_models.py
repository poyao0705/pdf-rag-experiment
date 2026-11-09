from typing import Literal, Self

from agents import TResponseInputItem
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TextPart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text"]
    text: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[TextPart] = Field(min_length=1)

    @property
    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return "\n".join(part.text for part in self.content)

    @model_validator(mode="after")
    def validate_text(self) -> Self:
        if self.role == "user" and not self.text.strip():
            raise ValueError("User messages must contain non-blank text")
        return self


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_last_message(self) -> Self:
        if self.messages[-1].role != "user":
            raise ValueError("Conversation must end with a user message")
        return self

    def to_agent_input(self) -> list[TResponseInputItem]:
        return [
            {"role": message.role, "content": message.text} for message in self.messages
        ]
