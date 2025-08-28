import asyncio
import json
import os
from typing import Any, Dict, List

from burr.core import ApplicationBuilder, State, action

# Import global logger
from logger import logger
from utils import llm
from utils.mcp import StreamableMCPClient, call_mcp_tool


@action(reads=[], writes=["user_input"])
def prompt(state: State, user_input: str) -> tuple[dict, State]:
    """Get input from the user."""
    return {"user_input": user_input}, state.update(user_input=user_input)


@action(reads=["user_input", "chat_history"], writes=["chat_history"])
async def response(state: State) -> tuple[dict, State]:
    """Call LLM and get response, then update conversation history."""
    # Add the user's latest message to the history
    # Use state.append method to append new message to chat history list
    new_user_message = {"role": "user", "content": state["user_input"]}
    state_with_user_message = state.append(chat_history=new_user_message)

    # Get MCP tool list (assuming MCP server is always available)
    tools = None
    mcp_client = StreamableMCPClient()
    try:
        connected = await mcp_client.connect(os.getenv("MCP_SERVER_URL"))
        if connected:
            tools = mcp_client.get_tools_for_llm()
    except Exception as e:
        logger.error(f"Error getting MCP tool list: {e}")
    finally:
        await mcp_client.cleanup()

    # Call LLM to get response using the new ask function
    # Support tool calls
    llm_response = await llm.ask(
        state_with_user_message["chat_history"], stream=False, tools=tools
    )

    # Handle tool calls
    if llm_response.tool_calls:
        # Handle tool calls and get results
        new_messages, updated_chat_history = await handle_tool_calls(
            state_with_user_message["chat_history"], llm_response
        )

        # Get final reply using the new ask function
        answer = await llm.ask(updated_chat_history, stream=False)
    else:
        answer = llm_response.content or "Sorry, I didn't understand your question."

    # Also add the model's response to the history
    new_assistant_message = {"role": "assistant", "content": answer}
    # Use state.append method to append AI's reply to chat history list
    final_state = state_with_user_message.append(chat_history=new_assistant_message)

    # Return result and updated state
    result = {"answer": answer}
    return result, final_state


async def handle_tool_calls(
    messages: list, response
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Handle tool calls and generate response messages.

    :param messages: Conversation history list
    :param response: LLM's response containing tool calls
    :return: (New message list, Updated complete message history)
    """
    new_messages = []
    updated_messages = messages.copy()

    if response.tool_calls:
        # Add tool calls to message history
        tool_call_message = {"role": "assistant", "tool_calls": response.tool_calls}
        new_messages.append(tool_call_message)
        updated_messages.append(tool_call_message)

        # Execute tool calls
        for tool_call in response.tool_calls:
            function_name = tool_call.function.name
            try:
                # Parse tool arguments
                function_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                error_message = f"Error parsing tool arguments: {e}"
                logger.error(error_message)
                tool_result = error_message
            else:
                # Call tool - Use function directly from utils/mcp.py
                tool_result = await call_mcp_tool(function_name, function_args)

            # Add tool call result to message history
            tool_result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": tool_result,
            }
            new_messages.append(tool_result_message)
            updated_messages.append(tool_result_message)

    return new_messages, updated_messages


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
    app = application()

    logger.info("Welcome to the Burr-driven asynchronous chatbot!")
    logger.info("Enter 'exit' or 'quit' to end the conversation.")

    while True:
        user_message = input("You: ")
        if user_message.lower() in ["exit", "quit"]:
            print("Goodbye!")
            break

        # Run application
        action, result, state = await app.arun(
            halt_after=["response"], inputs={"user_input": user_message}
        )
        print(f"AI: {result['answer']}")


if __name__ == "__main__":
    asyncio.run(chat())
