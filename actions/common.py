from typing import Dict, List, Optional, Tuple

from burr.core import action
from burr.core.action import streaming_action

from logger import logger
from utils.common import get_tool_call_markdown, run_concurrrently
from utils.llm import ask
from utils.mcp import StreamableMCPClient, connect_to_mcp
from schema import (
    ActionStreamMessage,
    BasicState,
    HumanConfirmResult,
    Message,
    Role,
    ToolCall,
)


@action.pydantic(reads=["chat_history"], writes=["chat_history", "exit_chat"])
def get_user_input(
    state: BasicState, user_input: str, system_prompt: str = ""
) -> BasicState:
    """Get input from the user."""
    logger.info(f"User input: {user_input}")
    if system_prompt:
        system_message = Message.system_message(content=system_prompt)
        logger.info(f"System prompt: {system_prompt}")
        state.chat_history.append(system_message)

    if user_input.lower() in ["exit", "quit"]:
        state.exit_chat = True
        return state

    state.chat_history.append(Message.user_message(content=user_input))
    return state


@streaming_action.pydantic(
    reads=["chat_history"],
    writes=["exit_chat"],
    state_input_type=BasicState,
    state_output_type=BasicState,
    stream_type=ActionStreamMessage,
)
async def exit_chat(
    state: BasicState,
) -> Tuple[ActionStreamMessage, Optional[BasicState]]:
    """Exit the chat."""
    logger.info(f"Chat History: {state.chat_history}")
    yield ActionStreamMessage(content="Goodbye!", role=Role.ASSISTANT), state


@streaming_action.pydantic(
    reads=["pending_tool_calls"],
    writes=["tool_execution_allowed", "chat_history"],
    state_input_type=BasicState,
    state_output_type=BasicState,
    stream_type=HumanConfirmResult,
)
async def human_confirm(
    state: BasicState, user_input: str = "No"
) -> Tuple[ActionStreamMessage, Optional[BasicState]]:
    """Ask the user if they want to execute the tool calls."""

    allowed = user_input in ["y", "yes"]
    if not allowed:
        tool_names = [tool.function.name for tool in state.pending_tool_calls]
        # clear pending tool calls
        state.pending_tool_calls = []
        state.chat_history.append(
            Message.assistant_message(
                content=f"Tool Calls Denied by user. Tool names: {tool_names}"
            )
        )
    state.tool_execution_allowed = allowed
    result = HumanConfirmResult(allowed=allowed, content="")
    if not allowed:
        result.content = f"Tool Calls Denied by user. Tool names: {tool_names}"

    yield result, state


@streaming_action.pydantic(
    reads=["chat_history", "pending_tool_calls"],
    writes=["chat_history", "pending_tool_calls", "tool_execution_allowed"],
    state_input_type=BasicState,
    state_output_type=BasicState,
    stream_type=ActionStreamMessage,
)
async def execute_tools(
    state: BasicState, mcp_client: StreamableMCPClient = None
) -> Tuple[ActionStreamMessage, Optional[BasicState]]:
    """Execute tool calls and update conversation history."""

    if not mcp_client:
        mcp_client = await connect_to_mcp()

    pending_tools_calls: List[ToolCall] = state.pending_tool_calls

    # Add tool call message to history
    tool_call_message = Message.from_tool_calls(tool_calls=pending_tools_calls)
    state.chat_history.append(tool_call_message)

    tasks = {}

    tool_call_id_to_name = {
        tool_call.id: tool_call.function.name for tool_call in pending_tools_calls
    }

    for tool_call in pending_tools_calls:
        tasks[tool_call.id] = mcp_client.call_tool(
            tool_call.function.name, tool_call.function.arguments
        )

    results: Dict[str, str] = await run_concurrrently(tasks)

    for tool_call_id, tool_result in results.items():
        try:
            tool_name = tool_call_id_to_name[tool_call_id]
            logger.info(f"Tool Call Result: {tool_result} for {tool_name}")

            tool_result_message = Message.tool_message(
                tool_call_id=tool_call_id,
                name=tool_name,
                content=tool_result,
            )

            state.chat_history.append(tool_result_message)

            yield (
                ActionStreamMessage(content=tool_result + "\n\n", role=Role.TOOL),
                None,
            )
        except Exception as e:
            logger.exception(f"Tool Call Failed: {e}")

    final_content_stream = await ask(state.chat_history, stream=True)

    # Stream final reply to user
    buffer = ""
    async for content in final_content_stream:
        buffer += content
        yield ActionStreamMessage(content=content, role=Role.ASSISTANT), None

    # Add final reply to history and finish
    final_assistant_message = Message.assistant_message(content=buffer)
    state.chat_history.append(final_assistant_message)
    state.pending_tool_calls = []
    state.tool_execution_allowed = False
    yield ActionStreamMessage(content="", role=Role.ASSISTANT), state


@streaming_action.pydantic(
    reads=["chat_history"],
    writes=["chat_history", "pending_tool_calls"],
    state_input_type=BasicState,
    state_output_type=BasicState,
    stream_type=ActionStreamMessage,
)
async def ask_llm(
    state: BasicState, system_prompt: str = "", mcp_tools: List[dict] = []
) -> Tuple[ActionStreamMessage, Optional[BasicState]]:
    """Async streaming call to LLM, handle tool calls, update conversation history."""
    # Add debug information
    logger.debug(f"MCP tools available: {mcp_tools}")
    logger.debug(f"System prompt: {system_prompt}")

    if system_prompt:
        system_message = Message.system_message(content=system_prompt)
        state.chat_history.append(system_message)

    # Add system message explaining tool usage
    tool_names = [tool["function"]["name"] for tool in mcp_tools] if mcp_tools else []

    # Single LLM call with streaming
    llm_response_stream = await ask(state.chat_history, stream=True, tools=mcp_tools)

    # Collect all chunks and detect tool calls
    llm_response_chunks = []
    tool_calls_detected = False
    tool_calls: List[ToolCall] = []

    async for chunk in llm_response_stream:
        if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
            tool_calls_detected = True
            tool_calls.extend(chunk.get("tool_calls", []))
        elif isinstance(chunk, str):
            llm_response_chunks.append(chunk)
            yield ActionStreamMessage(content=chunk, role=Role.ASSISTANT), None

    state.chat_history.append(
        Message.assistant_message(content="".join(llm_response_chunks))
    )

    # Handle tool calls if detected
    if tool_calls_detected and tool_calls:
        state.pending_tool_calls = tool_calls
        logger.info(f"Tool calls detected: {tool_calls}")
        tool_calls_json = get_tool_call_markdown(tool_calls)
        yield (
            ActionStreamMessage(
                content=f"\n\nPending Tool Calls:\n\n{tool_calls_json}\n",
                tool_calls=tool_calls,
                role=Role.ASSISTANT,
            ),
            None,
        )
        yield ActionStreamMessage(content="", role=Role.ASSISTANT), state
    else:
        yield ActionStreamMessage(content="", role=Role.ASSISTANT), state
