# vibe_workflow.py

import asyncio
import json
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from burr.core import ApplicationBuilder, State, action, expr, when
from burr.core.action import streaming_action
from burr.integrations.pydantic import PydanticTypingSystem
from pydantic import BaseModel, Field

from logger import logger
from utils import llm
from utils.mcp import StreamableMCPClient, connect_to_mcp

# This will fail if the file doesn't exist, but the design doc assumes it.
# I'll add a placeholder if it causes issues.
from utils.schema import ToolCall

# Global MCP client and tool list
mcp_client: StreamableMCPClient
mcp_tools: list


class VibeStepMetadata(BaseModel):
    name: str = Field(description="The short name of the step.")
    goal: str = Field(description="What this step aims to achieve.")
    hint: str = Field(description="Instructions on how to accomplish this step.")


# 1. State Models from V4 Design
class VibeStep(VibeStepMetadata):
    """Defines a sub-task with its own memory (Sub-Agent)."""

    step_id: int
    chat_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Independent chat/execution history for this sub-task.",
    )
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"


class ApplicationState(BaseModel):
    """The main application state, combining user interaction with the Vibe Workflow."""

    # Global/user-level history
    chat_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="High-level history of interaction with the user.",
    )

    # Vibe Workflow state
    vibe_plan: List[VibeStep] = Field(default_factory=list)
    active_step_id: Optional[int] = None
    current_goal: str = ""

    # Mode and flow control
    user_input: str = ""
    workflow_mode: Literal["chat", "vibe"] = "chat"
    execution_mode: Literal["interactive", "yolo"] = "interactive"
    exit_chat: bool = False

    # Tool execution state
    pending_tool_calls: List[ToolCall] = Field(default_factory=list)
    tool_execution_allowed: bool = False


def get_planner():
    steps = []

    custom_steps = [
        {"name": "计算", "goal": "计算1+1", "hint": "使用计算器计算1+1"},
        {"name": "计算", "goal": "计算1+1", "hint": "使用计算器计算1+1"},
        {"name": "总结", "goal": "总结以上计算结果", "hint": "输出总结的结果"},
    ]

    for idx, step in enumerate(custom_steps):
        steps.append(
            VibeStep(
                step_id=idx, name=step["name"], goal=step["goal"], hint=step["hint"]
            )
        )

    return steps


# 2. Actions
@action.pydantic(reads=["chat_history"], writes=["user_input", "exit_chat"])
def prompt(state: ApplicationState) -> ApplicationState:
    """Get input from the user and handle internal commands."""
    user_input = input("You: ")

    if user_input.lower() in ["exit", "quit"]:
        state.exit_chat = True
        return state

    state.user_input = user_input

    return state


@streaming_action.pydantic(
    reads=["current_goal"],
    writes=["vibe_plan"],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=dict,
)
async def vibe_planner(
    state: ApplicationState,
) -> Tuple[dict, Optional[ApplicationState]]:
    """Creates a vibe plan by breaking down the user's goal into actionable steps."""
    if not state.current_goal:
        yield {"answer": "No goal specified for planning."}, state
        return

    tool_names = [tool["function"]["name"] for tool in mcp_tools] if mcp_tools else []

    planning_prompt = f"""
Break down this goal into 3-5 concrete, actionable steps: "{state.current_goal}"

Available tools: {', '.join(tool_names) if tool_names else 'None'}

Create a step-by-step plan where each step:
1. Is a specific, actionable task that can be completed with a single tool call or set of related tool calls
2. Can be accomplished using the available tools
3. Builds sequentially toward the overall goal
4. Is clear enough for a sub-agent to execute independently
5. Uses specific values, not placeholders (if doing calculations, specify the actual numbers)

IMPORTANT: For multi-step calculations or processes:
- Each step should be self-contained but build on previous results
- Specify exact numbers and operations where possible
- Each step should produce a clear, usable result for the next step

Format your response as a numbered list of steps, like:
1. [Brief description of what to do with specific details]
2. [Brief description of what to do with specific details]
3. [Brief description of what to do with specific details]

Keep steps concise but specific and actionable.
"""

    messages = [{"role": "user", "content": planning_prompt}]

    yield {"answer": f"\n🎯 Planning for goal: {state.current_goal}\n"}, None

    try:
        # Get plan from LLM
        plan_response = await llm.ask(messages, stream=False)

        # Parse the response to extract steps
        steps = []
        lines = plan_response.split("\n")
        step_id = 0

        for line in lines:
            line = line.strip()
            if line and (
                line[0].isdigit() or line.startswith("-") or line.startswith("*")
            ):
                # Remove numbering/bullets and clean up
                step_desc = line
                for prefix in [
                    "1.",
                    "2.",
                    "3.",
                    "4.",
                    "5.",
                    "6.",
                    "7.",
                    "8.",
                    "9.",
                    "-",
                    "*",
                ]:
                    if step_desc.startswith(prefix):
                        step_desc = step_desc[len(prefix) :].strip()
                        break

                if step_desc:
                    step = VibeStep(
                        step_id=step_id, description=step_desc, status="pending"
                    )
                    steps.append(step)
                    step_id += 1

        state.vibe_plan = steps

        # Display the plan
        plan_display = "\n📋 Created plan:\n"
        for i, step in enumerate(steps, 1):
            plan_display += f"  {i}. {step.description}\n"

        yield {"answer": plan_display}, state

    except Exception as e:
        logger.error(f"Error creating vibe plan: {e}")
        yield {"answer": f"Failed to create plan: {e}"}, state


@streaming_action.pydantic(
    reads=[],
    writes=["exit_chat"],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=dict,
)
async def exit_chat(state: ApplicationState) -> Tuple[dict, Optional[ApplicationState]]:
    """Exit the chat."""
    print(f"Exiting. Final state can be logged here if needed.")
    state.exit_chat = True
    yield {"answer": "Goodbye!"}, state


@streaming_action.pydantic(
    reads=["vibe_plan", "current_goal", "active_step_id"],
    writes=["active_step_id", "pending_tool_calls", "vibe_plan", "current_goal"],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=dict,
)
async def vibe_step_executor(
    state: ApplicationState,
) -> Tuple[dict, Optional[ApplicationState]]:
    """Finds and executes the next pending step in the Vibe Plan."""
    # 1. Find the next pending step
    next_step = None
    for i, step in enumerate(state.vibe_plan):
        if step.status == "pending":
            state.active_step_id = i
            step.status = "in_progress"
            next_step = step
            break

    # 2. If no pending steps, the plan is complete
    if next_step is None:
        logger.info("Vibe plan complete.")
        state.current_goal = ""  # Clear goal
        state.vibe_plan = []  # Clear plan
        completion_message = "All steps completed!"
        yield {"answer": completion_message}, state
        return

    # 3. Execute the step
    step_message = (
        f"\n> Executing Step {next_step.step_id + 1}: {next_step.description}"
    )
    print(step_message)
    yield {"answer": step_message}, None

    # 4. Build context from previous completed steps
    previous_results = ""
    for i, completed_step in enumerate(state.vibe_plan):
        if completed_step.status == "completed" and i < next_step.step_id:
            if completed_step.chat_history:
                # Extract tool results from chat history
                for msg in completed_step.chat_history:
                    if msg.get("role") == "tool" and msg.get("content"):
                        tool_name = msg.get("name", "unknown")
                        content = msg.get("content", "")
                        previous_results += (
                            f"Step {i + 1} - {tool_name} result: {content}\n"
                        )

    tool_names = [tool["function"]["name"] for tool in mcp_tools]
    context_info = (
        f"\nContext from previous steps:\n{previous_results}"
        if previous_results
        else ""
    )

    system_message = {
        "role": "system",
        "content": f"You are a sub-agent focused on a single task: '{next_step.description}'. "
        f"You have access to these tools: {', '.join(tool_names)}. "
        f"{context_info}"
        f"Your goal is to use these tools to achieve your task. "
        f"Use the actual results from previous steps, not placeholder values. "
        f"You must respond with one or more tool calls. Do not respond with conversational text.",
    }
    next_step.chat_history.append(system_message)

    # 5. Call LLM to get tool calls for the step
    llm_response_stream = await llm.ask(
        next_step.chat_history, stream=True, tools=mcp_tools
    )

    # 6. Process stream and extract tool calls
    tool_calls: List[ToolCall] = []
    async for chunk in llm_response_stream:
        if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
            tool_calls.extend(chunk.get("tool_calls", []))

    if tool_calls:
        logger.info(f"Tool calls generated for step {next_step.step_id}: {tool_calls}")
        state.pending_tool_calls = tool_calls
    else:
        # If no tool calls, something went wrong or the step is trivial
        logger.warning(f"No tool calls generated for step {next_step.step_id}")
        next_step.status = "failed"

    yield {}, state


@action.pydantic(
    reads=["pending_tool_calls", "active_step_id", "vibe_plan"],
    writes=["tool_execution_allowed", "vibe_plan"],
)
def human_confirm(state: ApplicationState) -> ApplicationState:
    """Asks the user for confirmation to execute tool calls."""
    print("\nProposed tool calls:")
    for tool_call in state.pending_tool_calls:
        print(f"- {tool_call.function.name}({tool_call.function.arguments})")

    user_input = input("Allow tool execution? (y/n): ").strip().lower()
    state.tool_execution_allowed = user_input in ["y", "yes"]
    if not state.tool_execution_allowed:
        # If user denies, we mark the step as failed
        active_step = state.vibe_plan[state.active_step_id]
        active_step.status = "failed"
    return state


@streaming_action.pydantic(
    reads=[
        "chat_history",
        "tool_execution_allowed",
        "pending_tool_calls",
        "active_step_id",
        "vibe_plan",
    ],
    writes=[
        "chat_history",
        "tool_execution_allowed",
        "pending_tool_calls",
        "vibe_plan",
    ],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=dict,
)
async def execute_tools(
    state: ApplicationState,
) -> Tuple[dict, Optional[ApplicationState]]:
    """Executes the pending tool calls and records the results in the active step's history."""
    if not state.tool_execution_allowed or not state.pending_tool_calls:
        state.tool_execution_allowed = False
        yield {}, state
        return

    active_step = state.vibe_plan[state.active_step_id]

    # Add tool call message to the step's history
    tool_call_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call.to_dict() for tool_call in state.pending_tool_calls],
    }
    active_step.chat_history.append(tool_call_message)

    for tool_call in state.pending_tool_calls:
        try:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments or "{}")

            logger.info(f"Calling tool: {function_name} with args: {function_args}")
            tool_result = await mcp_client.call_tool(function_name, function_args)

            result_message = f"Tool {function_name} Result: {tool_result}"
            print(result_message)
            yield {"answer": result_message}, None

            # Add tool result to the step's history
            active_step.chat_history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": tool_result,
                }
            )
        except Exception as e:
            logger.error(f"Tool Call Failed: {e}")
            error_content = f"Error executing tool {tool_call.function.name}: {e}"
            active_step.chat_history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": error_content,
                }
            )

    # Mark the step as completed
    active_step.status = "completed"

    # Clear pending calls
    state.pending_tool_calls = []
    state.tool_execution_allowed = False
    yield {}, state


# 3. Application Builder
def application():
    """Builds the Burr application with states, actions, and transitions."""
    return (
        ApplicationBuilder()
        .with_typing(PydanticTypingSystem(ApplicationState))
        .with_state(ApplicationState())
        .with_actions(
            prompt=prompt,
            router=router,
            exit_chat=exit_chat,
            vibe_planner=vibe_planner,
            vibe_step_executor=vibe_step_executor,
            human_confirm=human_confirm,
            execute_tools=execute_tools,
        )
        .with_transitions(
            # Entry and exit
            ("prompt", "vibe_planner", when(exit_chat=False, workflow_mode="vibe")),
            ("prompt", "exit_chat", when(exit_chat=True)),
            # Routing to Vibe or Chat
            ("vibe_planner", "vibe_step_executor"),
            (
                "vibe_step_executor",
                "prompt",
                expr("len(pending_tool_calls) == 0"),
            ),  # Plan is complete or failed
            # Vibe Workflow Core Loop
            (
                "vibe_step_executor",
                "human_confirm",
                ~when(pending_tool_calls=[]) & when(execution_mode="interactive"),
            ),
            (
                "vibe_step_executor",
                "execute_tools",
                ~when(pending_tool_calls=[]) & when(execution_mode="yolo"),
            ),
            ("vibe_step_executor", "prompt", when(pending_tool_calls=[])),
            ("human_confirm", "execute_tools", when(tool_execution_allowed=True)),
            ("human_confirm", "prompt", when(tool_execution_allowed=False)),
            ("execute_tools", "vibe_step_executor"),
        )
        .with_entrypoint("prompt")
        .with_tracker("local", project="burr_vibe_agent")
        .build()
    )


# 4. Main Execution Loop
async def main():
    """Initializes MCP and runs the chat application."""
    global mcp_client, mcp_tools
    try:
        mcp_client = await connect_to_mcp()
        mcp_tools = mcp_client.get_tools_for_llm()
    except Exception as e:
        logger.error(f"Failed to connect to MCP: {e}")
        print("Could not connect to MCP. Tool execution will not be available.")
        mcp_client = None
        mcp_tools = []

    app = application()

    logger.info("Welcome to the Vibe Workflow Agent!")
    logger.info("Enter a goal to start, or 'exit' to quit.")
    logger.info("Use '/mode yolo' or '/mode interactive' to switch execution modes.")

    try:
        while True:
            # Run application (async streaming)
            action, result_container = await app.astream_result(
                halt_after=["prompt", "human_confirm", "exit_chat"]
            )

            if action.name == "exit_chat":
                # Consume the exit_chat streaming results
                async for item in result_container:
                    pass
                break

            # Consume the results from the streaming action
            async for item in result_container:
                pass
            # The actions themselves print to the console, so we just consume here.

    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        if mcp_client:
            await mcp_client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
