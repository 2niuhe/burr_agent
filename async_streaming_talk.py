import asyncio
import json
from typing import Tuple

from burr.core import ApplicationBuilder, State, action
from burr.core.action import streaming_action

# Import global logger
from logger import logger
from utils import llm
from utils.mcp import StreamableMCPClient, connect_to_mcp

# Global MCP client and tool list
mcp_client: StreamableMCPClient
mcp_tools: list


@action(reads=[], writes=["user_input"])
def prompt(state: State, user_input: str) -> tuple[dict, State]:
    """Get input from the user."""
    return {"user_input": user_input}, state.update(user_input=user_input)


@streaming_action(reads=["user_input", "chat_history"], writes=["chat_history"])
async def response(state: State) -> Tuple[dict, State]:
    """Async streaming call to LLM, handle tool calls, update conversation history."""
    # Add the user's latest message to the history
    new_user_message = {"role": "user", "content": state["user_input"]}
    state_with_user_message = state.append(chat_history=new_user_message)

    # Use global MCP tool list
    global mcp_tools
    tools = mcp_tools

    # Add debug information
    logger.info(f"MCP tools available: {tools}")

    # Add system message explaining tool usage
    tool_names = [tool["function"]["name"] for tool in tools]
    system_message = {
        "role": "system",
        "content": f"You can use the following tools: {', '.join(tool_names)}. Please use these tools to help the user when needed.",
    }
    state_with_user_message = state_with_user_message.append(
        chat_history=system_message
    )

    # First use ask_tool to check if tool calls are needed
    llm_response = await llm.ask_tool(
        state_with_user_message["chat_history"], tools=tools
    )

    # Handle tool calls
    if llm_response.tool_calls:
        logger.info(f"Tool calls detected: {llm_response.tool_calls}")

        # Add tool call message to history
        tool_call_message = {"role": "assistant", "tool_calls": llm_response.tool_calls}
        state_with_tool_calls = state_with_user_message.append(
            chat_history=tool_call_message
        )

        # Execute tool calls with MCP asynchronously
        for tool_call in llm_response.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            logger.info(f"Calling tool: {function_name} with args: {function_args}")
            tool_result = await mcp_client.call_tool(function_name, function_args)
            logger.info(f"Tool result: {tool_result}")

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

        # Get final reply using ask function (non-streaming for tool-based responses)
        final_content = await llm.ask(
            state_with_tool_calls["chat_history"], stream=False
        )

        # Stream output final reply (as chunks) to caller
        for char in final_content:
            yield {"answer": char}, None

        # Add final reply to history and finish
        final_assistant_message = {"role": "assistant", "content": final_content}
        final_state = state_with_tool_calls.append(chat_history=final_assistant_message)
        yield {"answer": final_content}, final_state
    else:
        # Normal streaming response handling using ask function
        buffer = ""
        # Get the async generator from ask function
        stream_generator = await llm.ask(
            state_with_user_message["chat_history"], stream=True
        )

        # Iterate over the async generator
        async for content in stream_generator:
            buffer += content
            yield {"answer": content}, None

        # Add complete model response to history and finish
        new_assistant_message = {"role": "assistant", "content": buffer}
        final_state = state_with_user_message.append(chat_history=new_assistant_message)
        yield {"answer": buffer}, final_state


def application():
    """Build Burr application."""
    return (
        ApplicationBuilder()
        .with_state(chat_history=[], user_input="")
        .with_actions(
            prompt=prompt,
            response=response,
        )
        .with_transitions(
            ("prompt", "response"),
            ("response", "prompt"),
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
            user_message = input("You: ")
            if user_message.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break

            # Run application (async streaming)
            action, result_container = await app.astream_result(
                halt_after=["response"], inputs={"user_input": user_message}
            )

            print("AI: ", end="", flush=True)
            async for item in result_container:
                content = item.get("answer", "")
                print(content, end="", flush=True)
            print()  # New line
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        # Clean up MCP client
        await mcp_client.cleanup()


if __name__ == "__main__":
    asyncio.run(chat())
