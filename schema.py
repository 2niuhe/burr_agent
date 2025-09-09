from enum import Enum
from typing import Any, List, Literal, Optional, Union
from collections import OrderedDict

from logger import logger

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
    async def tool_message(cls, content: str, name, tool_call_id: str) -> "Message":
        """Create a tool message"""
        from config import CONFIG
        original_content_length = len(content)
        if original_content_length > CONFIG.toolresult_compress_threshold:
            logger.warning(f"Tool result is too large: {original_content_length}, compressing...")
            from utils.prompts import COMPRESS_TOOL_RESULT_PROMPT
            from utils.llm import ask
            from utils.common import run_concurrrently

            def split_chunks(text, chunk_size, overlap):
                chunks = []
                start = 0
                content_length = len(text)
                while start < content_length:
                    end = min(start + chunk_size, content_length)
                    chunk = text[start:end]
                    chunks.append(chunk)
                    if end == content_length:
                        break
                    next_start = end - overlap if (end - overlap) > start else end
                    start = next_start
                return chunks

            chunk_size = 4 * CONFIG.toolresult_compress_threshold
            overlap = max(100, chunk_size // 100)
            chunks = split_chunks(content, chunk_size, overlap)
            chunk_idxs = list(range(len(chunks)))
            tasks = {idx: ask([Message.system_message(content=COMPRESS_TOOL_RESULT_PROMPT), Message.user_message(content=chunk)], stream=False) for idx, chunk in enumerate(chunks)}
            results = await run_concurrrently(tasks)
            compressed_chunks = [results[idx] for idx in chunk_idxs]
            content = "\n".join(compressed_chunks)
            logger.warning(f"Tool result compressed: {len(content)}, compress rate: {original_content_length / len(content)}")
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

    @property
    def total_tokens(self) -> int:
        """Count the number of tokens in the memory"""
        return sum([len(message.content) for message in self.messages if message.content])


    async def compress_message(self) -> None:
        """Compress a message"""
        from config import CONFIG
        if self.total_tokens > CONFIG.memory_compress_threshold:
            logger.info(f"Memory is too large, compressing...")
            from utils.prompts import COMPRESS_MEMORY_PROMPT
            from utils.llm import ask
            system_messages = [Message.system_message(content=COMPRESS_MEMORY_PROMPT)]
            user_messages = self.get_messages_except_system()
            content = await ask(user_messages, system_msgs=system_messages, stream=False)
            self.messages.clear(except_roles=[Role.SYSTEM])
            self.messages.append(Message.user_message(content=content))


    def append(self, message: Message, compress: bool = False) -> None:
        """Add a message to memory"""

        if (self.messages and 
            self.messages[-1].role == message.role):
            
            content = ""
            if self.messages[-1].content:
                content += self.messages[-1].content
            if message.content:
                content += '\n' + message.content

            self.messages[-1].content = content
            
            tool_calls = []
            if self.messages[-1].tool_calls:
                tool_calls.extend(self.messages[-1].tool_calls)
            if message.tool_calls:
                tool_calls.extend(message.tool_calls)

            self.messages[-1].tool_calls = tool_calls
        else:
            self.messages.append(message)


    def extend(self, messages: List[Message]) -> None:
        """Add multiple messages to memory"""
        for message in messages:
            self.append(message)


    def clear(self, except_roles: List[ROLE_TYPE] = []) -> None:
        """Clear all messages"""
        if except_roles:
            self.messages = [message for message in self.messages if message.role in except_roles]
        else:
            self.messages.clear()
        
    def get_messages_except_system(self) -> List[Message]:
        """Get messages except system messages"""
        return [message for message in self.messages if message.role != Role.SYSTEM]

    def get_recent_messages(self, n: int) -> List[Message]:
        """Get n most recent messages"""
        return self.messages[-n:]

    def to_dict_list(self) -> List[dict]:
        """Convert messages to list of dicts"""
        return [msg.to_dict() for msg in self.messages]


class VibeStepMetadata(BaseModel):
    name: str = Field(description="The short name of the step.")
    goal: str = Field(description="What this step aims to achieve.")
    hint: str = Field(description="Instructions on how to accomplish this step.", default="")
    
    def to_ordered_dict(self) -> OrderedDict:
        """Convert to OrderedDict maintaining field order: name, goal, hint"""
        ordered_dict = OrderedDict()
        ordered_dict["name"] = self.name
        ordered_dict["goal"] = self.goal
        ordered_dict["hint"] = self.hint
        return ordered_dict


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
