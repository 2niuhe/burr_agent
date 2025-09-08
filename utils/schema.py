from enum import Enum
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class Function(BaseModel):
    name: str = None
    arguments: Optional[str] = None

    def to_dict(self):
        return {"name": self.name, "arguments": self.arguments or "{}"}


class ToolCall(BaseModel):
    id: str
    type: str = "function"
    function: Function

    def to_dict(self):
        return {"id": self.id, "type": self.type, "function": self.function.to_dict()}


class Role(str, Enum):
    """Message role options"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


ROLE_VALUES = tuple(role.value for role in Role)
ROLE_TYPE = Literal[ROLE_VALUES]  # type: ignore


class ToolChoice(str, Enum):
    """Tool choice options"""

    NONE = "none"
    AUTO = "auto"
    REQUIRED = "required"


TOOL_CHOICE_VALUES = tuple(choice.value for choice in ToolChoice)
TOOL_CHOICE_TYPE = Literal[TOOL_CHOICE_VALUES]  # type: ignore


class ActionStreamMessage(BaseModel):
    content: str
    tool_calls: List[ToolCall] = Field(
        default_factory=list, description="The tool calls."
    )
    role: ROLE_TYPE = Field(default=Role.ASSISTANT)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class Message(BaseModel):
    """Represents a chat message in the conversation"""

    role: ROLE_TYPE = Field(...)  # type: ignore
    content: Optional[str] = Field(default=None)
    tool_calls: Optional[List[ToolCall]] = Field(default=None)
    name: Optional[str] = Field(default=None)
    tool_call_id: Optional[str] = Field(default=None)

    def __add__(self, other) -> List["Message"]:
        """支持 Message + list 或 Message + Message 的操作"""
        if isinstance(other, list):
            return [self] + other
        elif isinstance(other, Message):
            return [self, other]
        else:
            raise TypeError(
                f"unsupported operand type(s) for +: '{type(self).__name__}' and '{type(other).__name__}'"
            )

    def __radd__(self, other) -> List["Message"]:
        """支持 list + Message 的操作"""
        if isinstance(other, list):
            return other + [self]
        else:
            raise TypeError(
                f"unsupported operand type(s) for +: '{type(other).__name__}' and '{type(self).__name__}'"
            )

    def to_dict(self) -> dict:
        """Convert message to dictionary format"""
        message = {"role": self.role}
        if self.content is not None:
            message["content"] = self.content
        if self.tool_calls is not None:
            message["tool_calls"] = [
                tool_call.to_dict() for tool_call in self.tool_calls
            ]
        if self.name is not None:
            message["name"] = self.name
        if self.tool_call_id is not None:
            message["tool_call_id"] = self.tool_call_id
        return message

    @classmethod
    def user_message(cls, content: str) -> "Message":
        """Create a user message"""
        return cls(role=Role.USER, content=content)

    @classmethod
    def system_message(cls, content: str) -> "Message":
        """Create a system message"""
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def assistant_message(cls, content: Optional[str] = None) -> "Message":
        """Create an assistant message"""
        return cls(role=Role.ASSISTANT, content=content)

    @classmethod
    def tool_message(cls, content: str, name, tool_call_id: str) -> "Message":
        """Create a tool message"""
        return cls(
            role=Role.TOOL,
            content=content,
            name=name,
            tool_call_id=tool_call_id,
        )

    @classmethod
    def from_tool_calls(
        cls,
        tool_calls: List[ToolCall],
        content: Union[str, List[str]] = "",
        **kwargs,
    ):
        """Create ToolCallsMessage from raw tool calls.

        Args:
            tool_calls: Raw tool calls from LLM
            content: Optional message content
        """
        formatted_calls = [
            {"id": call.id, "function": call.function.to_dict(), "type": "function"}
            for call in tool_calls
        ]
        return cls(
            role=Role.ASSISTANT,
            content=content,
            tool_calls=formatted_calls,
            **kwargs,
        )


class Memory(BaseModel):
    messages: List[Message] = Field(default_factory=list)
    max_messages: int = Field(default=100)

    def append(self, message: Message) -> None:
        """Add a message to memory"""
        self.messages.append(message)
        # Optional: Implement message limit
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]

    def extend(self, messages: List[Message]) -> None:
        """Add multiple messages to memory"""
        self.messages.extend(messages)
        # Optional: Implement message limit
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]

    def clear(self) -> None:
        """Clear all messages"""
        self.messages.clear()

    def get_recent_messages(self, n: int) -> List[Message]:
        """Get n most recent messages"""
        return self.messages[-n:]

    def to_dict_list(self) -> List[dict]:
        """Convert messages to list of dicts"""
        return [msg.to_dict() for msg in self.messages]


class VibeStepMetadata(BaseModel):
    name: str = Field(description="The short name of the step.")
    goal: str = Field(description="What this step aims to achieve.")
    hint: str = Field(description="Instructions on how to accomplish this step.")


# 1. State Models from V4 Design
class VibeStep(VibeStepMetadata):
    """Defines a sub-task with its own memory (Sub-Agent)."""

    step_id: int
    chat_history: Memory = Field(
        default_factory=Memory,
        description="Independent chat/execution history for this sub-task.",
    )
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"


class BasicState(BaseModel):
    """State for the interactive mode."""

    chat_history: Memory = Field(
        default_factory=Memory, description="The chat history."
    )

    # for human confirm
    pending_tool_calls: List[ToolCall] = Field(
        default_factory=list, description="The pending tool calls."
    )
    tool_execution_allowed: bool = Field(
        default=False, description="Whether to allow tool execution."
    )

    # tool_call mode
    yolo_mode: bool = Field(default=False, description="Whether to use yolo mode.")
    
    exit_chat: bool = Field(default=False, description="Whether to exit the chat.")
    _version: str = "0.0.1"

    # Opetional Vibe Workflow state
    vibe_plan: List[VibeStep] = Field(default_factory=list)
    active_step_id: Optional[int] = None
    current_goal: str = ""


class HumanConfirmResult(BaseModel):
    allowed: bool
    content: str = ""
