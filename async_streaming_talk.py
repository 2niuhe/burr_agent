import os
import asyncio
import json
from typing import Generator, Tuple, Optional, List, Dict, Any

from burr.core import ApplicationBuilder, State, action
from burr.core.action import streaming_action
from utils.mcp import connect_to_mcp, StreamableMCPClient, call_mcp_tool
from utils import llm

# Import global logger
from logger import logger

# Global MCP client and tool list
mcp_client: Optional[StreamableMCPClient] = None
mcp_tools: Optional[list] = None


@action(reads=[], writes=[])
def initialize_mcp_client(state: State) -> tuple[dict, State]:
    """Initialize MCP client and get tool list"""
    global mcp_client, mcp_tools
    # Note: In this synchronous version, we can't directly await connect_to_mcp()
    # The MCP client initialization should be handled outside of Burr actions
    # or we need to use a different approach for async initialization
    return state


@action(reads=[], writes=["user_input"])
def prompt(state: State, user_input: str) -> tuple[dict, State]:
    """Get input from the user."""
    return {"user_input": user_input}, state.update(user_input=user_input)


@streaming_action(reads=["user_input", "chat_history"], writes=["chat_history"])
def response(state: State) -> Generator[Tuple[dict, Optional[State]], None, Tuple[dict, State]]:
    """Stream call LLM and get response, then update conversation history."""
    # Add the user's latest message to the history
    new_user_message = {"role": "user", "content": state["user_input"]}
    state_with_user_message = state.append(chat_history=new_user_message)

    # Use global MCP tool list
    global mcp_tools
    tools = mcp_tools
    
    # Add debug information
    logger.info(f"MCP tools available: {tools}")
    
    # If there are tools, add a system message explaining tool usage
    if tools:
        tool_names = [tool["function"]["name"] for tool in tools]
        system_message = {
            "role": "system", 
            "content": f"You can use the following tools: {', '.join(tool_names)}. Please use these tools to help the user when needed."
        }
        state_with_user_message = state_with_user_message.append(chat_history=system_message)

    # First use non-streaming call to check if tool calls are needed
    llm_response = llm.get_llm_response_sync(
        state_with_user_message["chat_history"],
        tools
    )
    
    # Handle tool calls
    if llm_response["type"] == "tool_calls":
        logger.info(f"Tool calls detected: {llm_response['tool_calls']}")
        
        # Add tool call message to history
        tool_call_message = {
            "role": "assistant",
            "tool_calls": llm_response["tool_calls"]
        }
        state_with_tool_calls = state_with_user_message.append(chat_history=tool_call_message)
        
        # Execute tool calls
        for tool_call in llm_response["tool_calls"]:
            function_name = tool_call["function"]["name"]
            try:
                # Parse tool arguments
                import json
                function_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError as e:
                error_message = f"Error parsing tool arguments: {e}"
                logger.error(error_message)
                tool_result = error_message
            else:
                # Call tool
                logger.info(f"Calling tool: {function_name} with args: {function_args}")
                # Since we are in a synchronous function, we cannot directly call async functions
                # Here we use a simplified mock implementation
                # In a real application, this would require more complex handling
                if function_name == "add":
                    try:
                        result = float(function_args["a"]) + float(function_args["b"])
                        tool_result = str(result)
                    except Exception as e:
                        tool_result = f"Error in tool execution: {e}"
                else:
                    tool_result = f"Unknown tool: {function_name}"
                logger.info(f"Tool result: {tool_result}")
            
            # Add tool call result to message history
            tool_result_message = {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": function_name,
                "content": tool_result
            }
            
            # Update state to include tool result
            state_with_tool_calls = state_with_tool_calls.append(chat_history=tool_result_message)
        
        # Get final reply (based on tool call results)
        final_response = llm.get_llm_response_sync(state_with_tool_calls["chat_history"])
        final_content = final_response.get("content", "Sorry, I didn't understand your question.")
        
        # Stream output final reply
        full_response = ""
        for char in final_content:
            full_response += char
            yield {"answer": char}, None
            
        # Add final reply to history
        final_assistant_message = {"role": "assistant", "content": final_content}
        final_state = state_with_tool_calls.append(chat_history=final_assistant_message)
        yield {"answer": final_content}, final_state
    else:
        # Normal streaming response handling
        full_response = ""
        answer = llm_response.get("content", "")
        
        try:
            # Stream process response
            for content in llm.get_llm_response_sync_streaming(
                state_with_user_message["chat_history"],
                tools
            ):
                full_response += content
                # yield partial results with None state (no state update yet)
                yield {"answer": content}, None
                    
            # Add complete model response to history
            new_assistant_message = {"role": "assistant", "content": full_response}
            final_state = state_with_user_message.append(chat_history=new_assistant_message)
            
            # Yield final result with state update
            yield {"answer": full_response}, final_state
            
        except Exception as e:
            error_msg = f"Error calling API: {e}"
            logger.error(error_msg)
            # Yield error message with state update
            yield {"answer": error_msg}, state.update(chat_history=state["chat_history"])


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
    if not mcp_tools or not mcp_client: 
        mcp_client = await connect_to_mcp()
        if mcp_client:
            mcp_tools = mcp_client.get_tools_for_llm()
    
    app = application()

    logger.info("Welcome to the Burr-driven streaming chatbot!")
    logger.info("Enter 'exit' or 'quit' to end the conversation.")

    while True:
        try:
            user_message = input("You: ")
            if user_message.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break

            # Run application
            action, result_container = app.stream_result(
                halt_after=["response"],
                inputs={"user_input": user_message}
            )
            
            print("AI: ", end="", flush=True)
            for item in result_container:
                content = item.get("answer", "")
                print(content, end="", flush=True)
            print()  # New line
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    asyncio.run(chat())