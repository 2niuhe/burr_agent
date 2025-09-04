from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from utils.schema import ToolCall


class VibeStepMetadata(BaseModel):
    name: str = Field(description="The short name of the step.")
    goal: str = Field(description="What this step aims to achieve.")
    hint: str = Field(description="Instructions on how to accomplish this step.")

# 1. State Models from V4 Design
class VibeStep(VibeStepMetadata):
    """Defines a sub-task with its own memory (Sub-Agent)."""
    step_id: int
    chat_history: List[Dict[str, Any]] = Field(default_factory=list, description="Independent chat/execution history for this sub-task.")
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"


class ApplicationState(BaseModel):
    """The main application state, combining user interaction with the Vibe Workflow."""
    # Global/user-level history
    chat_history: List[Dict[str, Any]] = Field(default_factory=list, description="High-level history of interaction with the user.")
    
    # Vibe Workflow state
    vibe_plan: List[VibeStep] = Field(default_factory=list)
    active_step_id: Optional[int] = None
    current_goal: str = ""
    
    # Mode and flow control
    user_input: str = ""
    workflow_mode: Literal["chat", "vibe"] = "chat"
    execution_mode: Literal["interactive", "yolo"] = "interactive"
    exit_chat: bool = Field(default=False, description="Whether to exit the chat.")
    
    # Tool execution state
    pending_tool_calls: List[ToolCall] = Field(default_factory=list)
    tool_execution_allowed: bool = False
    _version: str = "0.0.1"