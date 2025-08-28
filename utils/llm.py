import os
from collections.abc import AsyncGenerator
from typing import Any, List, Optional, Union, Dict

import dotenv
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage

from logger import logger

dotenv.load_dotenv()

api_key = os.getenv("LLM_API_KEY")
base_url = os.getenv("LLM_BASE_URL")
default_model = os.getenv("LLM_MODEL")

assert all([api_key, base_url, default_model]), (
    "LLM API key, base URL, and model must be set"
)

async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)


async def ask(
    messages: List[Union[dict, Any]],
    system_msgs: Optional[List[Union[dict, Any]]] = None,
    stream: bool = True,
    temperature: Optional[float] = None,
    tools: Optional[List[dict]] = None,
    tool_choice: str = "auto",
    **kwargs,
) -> Union[str, ChatCompletionMessage, AsyncGenerator[Union[str, Dict[str, Any]], None]]:
    """
    Send a prompt to the LLM and get the response.

    Args:
        messages: List of conversation messages
        system_msgs: Optional system messages to prepend
        stream: Whether to stream the response
        temperature: Sampling temperature for the response
        tools: List of tools to use
        tool_choice: Tool choice strategy
        **kwargs: Additional completion arguments

    Returns:
        str: The generated response (when stream=False and no tools)
        ChatCompletionMessage: The model's response with tools (when stream=False and tools provided)
        AsyncGenerator: Async generator yielding response chunks (when stream=True)
            - For content: yields string chunks
            - For tools: yields dict with tool call information
    """

    # Combine system messages with user messages
    all_messages = []
    if system_msgs:
        all_messages.extend(system_msgs)
    all_messages.extend(messages)

    try:
        logger.info("Calling LLM API")

        api_params = {
            "model": default_model,
            "messages": all_messages,
            "stream": stream,
        }

        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = tool_choice

        if temperature is not None:
            api_params["temperature"] = temperature

        # Add any additional kwargs
        api_params.update(kwargs)

        if stream:
            # Use streaming response - return async generator
            response = await async_client.chat.completions.create(**api_params)

            if tools:
                # Handle streaming with tools
                async def stream_tools_generator():
                    final_tool_calls = {}
                    
                    async for chunk in response:
                        # Handle content streaming
                        if chunk.choices[0].delta.content is not None:
                            yield chunk.choices[0].delta.content
                        
                        # Handle tool calls streaming
                        for tool_call in chunk.choices[0].delta.tool_calls or []:
                            index = tool_call.index
                            
                            if index not in final_tool_calls:
                                final_tool_calls[index] = tool_call
                            else:
                                # Merge tool call information
                                if tool_call.function.arguments:
                                    final_tool_calls[index].function.arguments += tool_call.function.arguments
                                if tool_call.function.name:
                                    final_tool_calls[index].function.name = tool_call.function.name
                                if tool_call.id:
                                    final_tool_calls[index].id = tool_call.id
                            
                            # Yield tool call information
                            yield {
                                "type": "tool_call",
                                "tool_calls": list(final_tool_calls.values())
                            }

                logger.info("Successfully obtained streaming API response with tools")
                return stream_tools_generator()
            else:
                # Handle regular content streaming
                async def stream_content_generator():
                    async for chunk in response:
                        if chunk.choices[0].delta.content is not None:
                            yield chunk.choices[0].delta.content

                logger.info("Successfully obtained streaming API response")
                return stream_content_generator()
        else:
            # Use non-streaming response
            response = await async_client.chat.completions.create(**api_params)
            choice = response.choices[0]
            
            if tools:
                logger.info("Successfully obtained API response with tools")
                return choice.message
            else:
                content = choice.message.content or ""
                logger.info("Successfully obtained API response")
                return content

    except Exception as e:
        error_message = f"Error calling API: {e}"
        logger.error(error_message)
        raise RuntimeError(error_message)


if __name__ == "__main__":
    # This is an example showing how to run this module directly
    import asyncio

    async def test():
        example_messages = [
            {"role": "user", "content": "Hello, please introduce yourself."},
        ]
        try:
            # Test non-streaming
            response = await ask(example_messages, stream=False)
            print(f"Non-streaming response: {response}")
            
            # Test streaming
            print("\n--- Streaming response ---")
            stream_gen = await ask(example_messages, stream=True)
            async for chunk in stream_gen:
                print(f"Streaming chunk: {chunk}")
                
        except Exception as e:
            print(f"Error: {e}")

    asyncio.run(test())
