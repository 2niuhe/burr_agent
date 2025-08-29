import asyncio
import json
from typing import Tuple, List

from burr.core import ApplicationBuilder, State, action, when
from burr.core.action import streaming_action

from logger import logger
from utils import llm
from utils.llm import ToolCall
from utils.mcp import StreamableMCPClient, connect_to_mcp

# Global MCP client and tool list
mcp_client: StreamableMCPClient
mcp_tools: list


@action(reads=[], writes=["user_input"])
def prompt(state: State) -> tuple[dict, State]:
    """Get input from the user."""
    user_input = input("You: ")

    if user_input.lower() in ["exit", "quit"]:
        return {"exit_chat": True}, state.update(exit_chat=True)
    
    return {"user_input": user_input}, state.update(user_input=user_input)


@action(reads=['tool_execution_needed', 'pending_tool_calls'], writes=['tool_execution_allowed'])
def human_confirm(state: State) -> tuple[dict, State]:
    """Ask the user if they want to execute the tool calls."""

    user_input = input("Allow tool execution? (y/n): ").strip().lower()
    if user_input in ['y', 'yes']:
        return {"tool_execution_allowed": True}, state.update(tool_execution_allowed=True)
    else:
        return {"tool_execution_allowed": False}, state.update(tool_execution_allowed=False)


@streaming_action(reads=["user_input", "chat_history"], writes=["chat_history", "pending_tool_calls", "tool_execution_needed"])
async def response(state: State) -> Tuple[dict, State]:
    """Async streaming call to LLM, handle tool calls, update conversation history."""
    # Add the user's latest message to the history
    new_user_message = {"role": "user", "content": state["user_input"]}
    state_with_user_message = state.append(chat_history=new_user_message).update(
        pending_tool_calls=[],
        tool_execution_needed=False
    )

    # Use global MCP tool list
    global mcp_tools
    tools = mcp_tools

    # Add debug information
    logger.debug(f"MCP tools available: {tools}")

    # Add system message explaining tool usage
    tool_names = [tool["function"]["name"] for tool in tools]
    system_message = {
        "role": "system",
        "content": f"You can use the following tools: {', '.join(tool_names)}. Please use these tools to help the user when needed.",
    }
    state_with_user_message = state_with_user_message.append(
        chat_history=system_message
    )

    # Single LLM call with streaming
    llm_response_stream = await llm.ask(
        state_with_user_message["chat_history"], stream=True, tools=tools
    )
    
    # Collect all chunks and detect tool calls
    llm_response_chunks = []
    tool_calls_detected = False
    tool_calls: List[ToolCall] = []
    
    print("AI: ", end="", flush=True)
    async for chunk in llm_response_stream:
        if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
            tool_calls_detected = True
            tool_calls.extend(chunk.get("tool_calls", []))
        elif isinstance(chunk, str):
            llm_response_chunks.append(chunk)
            print(chunk, end="", flush=True)
            # Stream content chunks to user
            yield {"answer": chunk}, None
    
    state_with_user_message = state_with_user_message.append(
        chat_history={"role": "assistant", "content": "".join(llm_response_chunks)}
    )
    
    # Handle tool calls if detected
    if tool_calls_detected and tool_calls:
        logger.info(f"Tool calls detected: {tool_calls}")
        print(f"\nPending Tool Calls:\n {[tool_call.function.to_dict() for tool_call in tool_calls]}")
        yield {}, state_with_user_message.update(
            pending_tool_calls=tool_calls,
            tool_execution_needed=True
        )
    else:
        yield {}, state_with_user_message
    

@streaming_action(
    reads=['chat_history', 'tool_execution_allowed', 'pending_tool_calls'],
    writes=['chat_history', 'tool_execution_allowed', 'pending_tool_calls'])
async def execute_tools(state: State) -> Tuple[dict, State]:
    """Execute tool calls and update conversation history."""

    global mcp_client

    pending_tools_calls: List[ToolCall] = state.get('pending_tool_calls', [])
    tool_execution_allowed: bool = state.get('tool_execution_allowed', False)


    if not pending_tools_calls or not tool_execution_allowed:
        # nothing to do
        yield {}, state.update(tool_execution_allowed=False)

    # Add tool call message to history
    tool_call_message = {
        "role": "assistant",
        "content": "",    
        "tool_calls": [tool_call.to_dict() for tool_call in pending_tools_calls]
    }
    state_with_tool_calls = state.append(
        chat_history=tool_call_message
    )


    for tool_call in pending_tools_calls:
        try:
            # Extract function name and arguments from ChoiceDeltaToolCall object
            function_name = tool_call.function.name
            function_args = tool_call.function.arguments
            
            # Parse arguments if it's a string
            if isinstance(function_args, str):
                try:
                    function_args = json.loads(function_args)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse tool arguments: {function_args}")
                    function_args = {}

            logger.info(f"Calling tool: {function_name} with args: {function_args}")
            tool_result = await mcp_client.call_tool(function_name, function_args)

            print(f"Tool Call Result: {tool_result}")

            # Add tool call result to message history
            tool_result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": tool_result,
            }

            # Update state to include tool result
            state_with_tool_calls = state_with_tool_calls.append(
                chat_history=tool_result_message
            )
        except Exception as e:
            logger.exception(f"Tool Call Failed: {e}")

    # Get final reply using the same streaming approach
    final_content_stream = await llm.ask(
        state_with_tool_calls["chat_history"], stream=True
    )

    print("AI: ", end="", flush=True)

    # Stream final reply to user
    buffer = ""
    async for content in final_content_stream:
        buffer += content
        print(content, end="", flush=True)
        yield {"answer": content}, None

    # Add final reply to history and finish
    final_assistant_message = {"role": "assistant", "content": buffer}
    final_state = state_with_tool_calls.append(
        chat_history=final_assistant_message).update(
            pending_tool_calls=[],
            tool_execution_allowed=False
        )
    yield {"answer": buffer}, final_state


@action(reads=['chat_history'], writes=['exit_chat'])
def exit_chat(state: State) -> Tuple[dict, State]:
    """Exit the chat."""
    print(f"Chat History: {state['chat_history']}")
    return {"exit_chat": True}, state.update(exit_chat=True)


def application():
    """Build Burr application."""
    return (
        ApplicationBuilder()
        .with_state(
            chat_history=[],
            user_input="",
            pending_tool_calls=[],
            tool_execution_allowed=False,
            exit_chat=False
        )
        .with_actions(
            prompt=prompt,
            response=response,
            human_confirm=human_confirm,
            execute_tools=execute_tools,
            exit_chat=exit_chat
        )
        .with_transitions(
            ("prompt", "response", when(exit_chat=False)),
            ("prompt", "exit_chat", when(exit_chat=True)),
            ("response", "human_confirm", when(tool_execution_needed=True)),
            ("response", "prompt", when(tool_execution_needed=False)),
            ("human_confirm", "execute_tools", when(tool_execution_allowed=True)),
            ("human_confirm", "prompt", when(tool_execution_allowed=False)),
            ("execute_tools", "prompt")
        )
        .with_entrypoint("prompt")
        .with_tracker("local", project="burr_agent")
        .build()
    )


async def chat():
    """Run chat application."""
    # Initialize MCP client
    global mcp_client, mcp_tools
    mcp_client = await connect_to_mcp()
    mcp_tools = mcp_client.get_tools_for_llm()

    app = application()

    logger.info("Welcome to the Burr-driven streaming chatbot!")
    logger.info("Enter 'exit' or 'quit' to end the conversation.")

    try:
        while True:
            # Run application (async streaming)
            action, result_container = await app.astream_result(
                halt_after=["response", "execute_tools", "exit_chat"]
            )

            if action.name == "exit_chat":
                print("Goodbye!")
                break

            async for item in result_container:
                pass
            print()  # New line
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        # Clean up MCP client
        await mcp_client.cleanup()


if __name__ == "__main__":
    asyncio.run(chat())
