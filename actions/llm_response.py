from typing import List, Optional, Tuple
from burr.core import streaming_action
from state import ApplicationState
from logger import logger
from utils.schema import ToolCall, ActionStreamMessage
from utils.llm import ask
from utils.mcp import mcp_tools


@streaming_action.pydantic(
    reads=["chat_history"],
    writes=["pending_tool_calls", "vibe_plan", "chat_history"],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=ActionStreamMessage,
)
async def llm_response(state: ApplicationState) -> Tuple[ActionStreamMessage, Optional[ApplicationState]]:
    """Call LLM to get tool calls for the step"""



    yield {}, state