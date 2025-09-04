from typing import List, Literal, Optional, Dict, Any

from pydantic import BaseModel, Field

from utils.llm import ToolCall


class VibeStep(BaseModel):
    """A sub-task with its own isolated execution history."""

    step_id: int
    description: str

    # Per-step, isolated chat/execution history
    chat_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Fields used to summarize/report the step
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None
    analysis: Optional[str] = None
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"


class ApplicationState(BaseModel):
    # Global/user-level history (what the user sees)
    chat_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Active subtask tracking
    active_step_id: Optional[int] = None

    # Workflow and control
    user_input: str = ""
    workflow_mode: Literal["chat", "vibe", "ops"] = "chat"
    execution_mode: Literal["interactive", "yolo"] = "interactive"
    current_goal: str = ""
    exit_chat: bool = False

    # Tool call gating and queue
    pending_tool_calls: List[ToolCall] = Field(default_factory=list)
    tool_execution_allowed: bool = False
    tool_execution_needed: bool = False

    # Vibe plan
    vibe_plan: List[VibeStep] = Field(default_factory=list)

    # Router hint for paths
    route_target: Optional[Literal[
        "chat_response",
        "vibe_planner",
        "vibe_step_executor",
    ]] = None


