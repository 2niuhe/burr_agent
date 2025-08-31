import json
from typing import List, Optional, Tuple

from burr.core import action
from burr.core.action import streaming_action
from pydantic import BaseModel

from logger import logger
from utils import llm
from utils.llm import ToolCall

from .state import ApplicationState, VibeStep
from .tools_manager import ToolsManager


def _parse_internal_commands(user_input: str, state: ApplicationState) -> ApplicationState:
    text = user_input.strip()
    if not text.startswith("/"):
        return state

    parts = text.split()
    cmd = parts[0].lower()

    if cmd == "/mode" and len(parts) >= 2:
        mode = parts[1].lower()
        if mode in ("interactive", "yolo"):
            state.execution_mode = mode  # type: ignore
    elif cmd == "/workflow" and len(parts) >= 2:
        wf = parts[1].lower()
        if wf in ("chat", "vibe", "ops"):
            state.workflow_mode = wf  # type: ignore
    elif cmd == "/goal" and len(parts) >= 2:
        state.current_goal = " ".join(parts[1:])

    return state


@action.pydantic(reads=[], writes=["user_input", "exit_chat"])
def prompt(state: ApplicationState) -> ApplicationState:
    user_input = input("You: ")
    if user_input.lower() in ["exit", "quit"]:
        state.exit_chat = True
        return state
    state.user_input = user_input
    return state


@action.pydantic(reads=["user_input", "workflow_mode", "current_goal"], writes=["route_target", "chat_history"])
def router(state: ApplicationState) -> ApplicationState:
    # Commands first
    original = state.user_input
    state = _parse_internal_commands(original, state)

    if original.startswith("/"):
        # Acknowledge command
        state.chat_history.append({
            "role": "assistant",
            "content": f"Ok. mode={state.execution_mode}, workflow={state.workflow_mode}, goal='{state.current_goal}'"
        })
        state.route_target = "chat_response"
        return state

    if state.workflow_mode == "vibe":
        if not state.current_goal:
            state.current_goal = original
        state.route_target = "vibe_planner"
        return state

    # default chat path
    state.route_target = "chat_response"
    return state


@streaming_action.pydantic(
    reads=["user_input", "chat_history"],
    writes=["chat_history", "pending_tool_calls", "tool_execution_needed"],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=dict,
)
async def chat_response(state: ApplicationState) -> Tuple[dict, Optional[ApplicationState]]:
    # user message
    state.chat_history.append({"role": "user", "content": state.user_input})

    # tools are available for chat as well
    await ToolsManager.ensure_initialized()
    tools = ToolsManager.get_tools_for_llm()

    llm_stream = await llm.ask(state.chat_history, stream=True, tools=tools)

    print("AI: ", end="", flush=True)
    buffer: List[str] = []
    tool_calls_detected = False
    detected_tool_calls: List[ToolCall] = []
    async for chunk in llm_stream:
        if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
            tool_calls_detected = True
            detected_tool_calls.extend(chunk.get("tool_calls", []))
        elif isinstance(chunk, str):
            buffer.append(chunk)
            print(chunk, end="", flush=True)
            yield {"answer": chunk}, None
    final = "".join(buffer)
    state.chat_history.append({"role": "assistant", "content": final})

    if tool_calls_detected and detected_tool_calls:
        state.pending_tool_calls = detected_tool_calls
        state.tool_execution_needed = True
        yield {}, state
    else:
        state.tool_execution_needed = False
        yield {}, state


@action.pydantic(reads=["current_goal", "vibe_plan"], writes=["vibe_plan", "active_step_id"])
def vibe_planner(state: ApplicationState) -> ApplicationState:
    goal = (state.current_goal or "").strip()
    # Heuristic planning without async calls: split by punctuation/phrases
    delimiters = [";", "\n", "->", " then ", " and then ", " next ", " afterwards "]
    parts: List[str] = [goal]
    for d in delimiters:
        tmp: List[str] = []
        for p in parts:
            tmp.extend([s.strip() for s in p.split(d) if s.strip()])
        parts = tmp
        if len(parts) >= 2:
            break

    if not parts:
        parts = [goal] if goal else ["Clarify the goal with the user"]

    # Cap 4 steps and normalize
    steps: List[VibeStep] = []
    for idx, desc in enumerate(parts[:4], start=1):
        steps.append(VibeStep(step_id=idx, description=desc))

    if not steps:
        steps = [VibeStep(step_id=1, description="Investigate the problem")]

    state.vibe_plan = steps
    state.active_step_id = steps[0].step_id
    return state


def _get_active_step(state: ApplicationState) -> Optional[VibeStep]:
    for step in state.vibe_plan:
        if step.step_id == state.active_step_id:
            return step
    return None


@streaming_action.pydantic(
    reads=["vibe_plan", "active_step_id", "execution_mode"],
    writes=["vibe_plan", "pending_tool_calls", "tool_execution_needed"],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=dict,
)
async def vibe_step_executor(state: ApplicationState) -> Tuple[dict, Optional[ApplicationState]]:
    step = _get_active_step(state)
    if step is None:
        yield {}, state
        return
    step.status = "in_progress"

    # Prepare per-step system message and tools
    await ToolsManager.ensure_initialized()
    tools = ToolsManager.get_tools_for_llm()
    system_message = {
        "role": "system",
        "content": f"Sub-task: {step.description}. Use tools when helpful.",
    }

    # Build step-local history (kept inside step)
    step.chat_history.append(system_message)

    llm_stream = await llm.ask(step.chat_history, stream=True, tools=tools)

    print("AI: ", end="", flush=True)
    buffer: List[str] = []
    detected_tool_calls: List[ToolCall] = []
    tool_calls_detected = False
    async for chunk in llm_stream:
        if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
            tool_calls_detected = True
            detected_tool_calls.extend(chunk.get("tool_calls", []))
        elif isinstance(chunk, str):
            buffer.append(chunk)
            print(chunk, end="", flush=True)
            yield {"answer": chunk}, None

    if buffer:
        step.chat_history.append({"role": "assistant", "content": "".join(buffer)})

    if tool_calls_detected and detected_tool_calls:
        state.pending_tool_calls = detected_tool_calls
        state.tool_execution_needed = True
        yield {}, state
    else:
        state.tool_execution_needed = False
        yield {}, state


@action.pydantic(reads=["tool_execution_needed", "execution_mode"], writes=["tool_execution_allowed"])
def human_confirm(state: ApplicationState) -> ApplicationState:
    if not state.tool_execution_needed:
        state.tool_execution_allowed = False
        return state

    if state.execution_mode == "yolo":
        state.tool_execution_allowed = True
        return state

    user_input = input("Allow tool execution? (y/n): ").strip().lower()
    state.tool_execution_allowed = user_input in ["y", "yes"]
    return state


@streaming_action.pydantic(
    reads=["pending_tool_calls", "vibe_plan", "active_step_id", "chat_history"],
    writes=["vibe_plan", "pending_tool_calls", "chat_history"],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=dict,
)
async def execute_tools(state: ApplicationState) -> Tuple[dict, Optional[ApplicationState]]:
    pending: List[ToolCall] = state.pending_tool_calls
    if not pending:
        yield {}, state
        return

    step = _get_active_step(state)

    client = ToolsManager.get_client()
    if client is None:
        logger.warning("No MCP client available; skipping tool execution")
        state.pending_tool_calls = []
        yield {}, state
        return

    # Add assistant tool_call message into appropriate history
    if step is not None:
        step.chat_history.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [tc.to_dict() for tc in pending],
        })
    else:
        state.chat_history.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [tc.to_dict() for tc in pending],
        })

    # Execute tools in sequence
    for tc in pending:
        function_name = tc.function.name
        function_args = tc.function.arguments
        try:
            args_obj = json.loads(function_args) if isinstance(function_args, str) else (function_args or {})
        except Exception:
            args_obj = {}
        result = await client.call_tool(function_name, args_obj)
        msg = {
            "role": "tool",
            "tool_call_id": tc.id,
            "name": function_name,
            "content": result,
        }
        if step is not None:
            step.chat_history.append(msg)
        else:
            state.chat_history.append(msg)

    state.pending_tool_calls = []

    # Ask for finalization on the step history
    history_for_final = step.chat_history if step is not None else state.chat_history
    final_stream = await llm.ask(history_for_final, stream=True)
    print("AI: ", end="", flush=True)
    buffer: List[str] = []
    async for content in final_stream:
        buffer.append(content)
        print(content, end="", flush=True)
        yield {"answer": content}, None
    if step is not None:
        step.chat_history.append({"role": "assistant", "content": "".join(buffer)})
    else:
        state.chat_history.append({"role": "assistant", "content": "".join(buffer)})
    yield {}, state


@action.pydantic(reads=["vibe_plan", "active_step_id"], writes=["vibe_plan"])
def vibe_result_analyzer(state: ApplicationState) -> ApplicationState:
    step = _get_active_step(state)
    if step is None:
        return state
    # Heuristic: if last assistant message exists after tool run, consider complete
    if step.chat_history and step.chat_history[-1].get("role") == "assistant":
        step.status = "completed"
    else:
        step.status = "failed"
    return state


@action.pydantic(reads=["vibe_plan", "active_step_id", "chat_history"], writes=["chat_history", "active_step_id"])
def step_summarizer(state: ApplicationState) -> ApplicationState:
    step = _get_active_step(state)
    if step is None:
        return state

    # Heuristic summary without async calls
    last_assistant = next((m for m in reversed(step.chat_history) if m.get("role") == "assistant" and m.get("content")), None)
    last_tool = next((m for m in reversed(step.chat_history) if m.get("role") == "tool" and m.get("content")), None)
    summary_bits: List[str] = []
    if last_assistant and last_assistant.get("content"):
        summary_bits.append(str(last_assistant["content"])[:160])
    if last_tool and last_tool.get("content"):
        summary_bits.append(f"Tool: {str(last_tool['content'])[:120]}")
    if not summary_bits:
        summary_bits = ["No significant output captured."]
    summary_text = " | ".join(summary_bits)

    state.chat_history.append({
        "role": "assistant",
        "content": f"{('✅' if step.status=='completed' else '❌')} Step {step.step_id} {step.status}: {summary_text}",
    })

    # Advance to next step or clear active
    next_step_id: Optional[int] = None
    found = False
    for s in state.vibe_plan:
        if found and s.status == "pending":
            next_step_id = s.step_id
            break
        if s.step_id == step.step_id:
            found = True
    state.active_step_id = next_step_id
    return state


@action.pydantic(reads=["chat_history"], writes=[])
def exit_chat(state: ApplicationState) -> ApplicationState:
    # Placeholder exit action to allow the app loop to halt and exit cleanly
    print("Goodbye!")
    return state

