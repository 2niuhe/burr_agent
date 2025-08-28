import os
import dotenv
from typing import List, Any, Optional, Union, AsyncGenerator
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
) -> Union[str, AsyncGenerator[str, None]]:
    """
    Send a prompt to the LLM and get the response.

    Args:
        messages: List of conversation messages
        system_msgs: Optional system messages to prepend
        stream: Whether to stream the response
        temperature: Sampling temperature for the response

    Returns:
        str: The generated response (when stream=False)
        AsyncGenerator[str, None]: Async generator yielding response chunks (when stream=True)
    """
    if not api_key:
        raise ValueError("LLM API key not set. Please set LLM_API_KEY")

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

        if temperature is not None:
            api_params["temperature"] = temperature

        if stream:
            # Use streaming response - return async generator
            response = await async_client.chat.completions.create(**api_params)

            async def stream_generator():
                async for chunk in response:
                    if chunk.choices[0].delta.content is not None:
                        yield chunk.choices[0].delta.content

            logger.info("Successfully obtained streaming API response")
            return stream_generator()
        else:
            # Use non-streaming response
            response = await async_client.chat.completions.create(**api_params)
            content = response.choices[0].message.content or ""
            logger.info("Successfully obtained API response")
            return content

    except Exception as e:
        error_message = f"Error calling API: {e}"
        logger.error(error_message)
        raise RuntimeError(error_message)


async def ask_tool(
    messages: List[Union[dict, Any]],
    system_msgs: Optional[List[Union[dict, Any]]] = None,
    timeout: int = 300,
    tools: Optional[List[dict]] = None,
    tool_choice: str = "auto",
    temperature: Optional[float] = None,
    **kwargs,
) -> ChatCompletionMessage | None:
    """
    Ask LLM using functions/tools and return the response.

    Args:
        messages: List of conversation messages
        system_msgs: Optional system messages to prepend
        timeout: Request timeout in seconds
        tools: List of tools to use
        tool_choice: Tool choice strategy
        temperature: Sampling temperature for the response
        **kwargs: Additional completion arguments

    Returns:
        ChatCompletionMessage: The model's response
    """
    if not api_key:
        raise ValueError("LLM API key not set. Please set LLM_API_KEY")

    # Combine system messages with user messages
    all_messages = []
    if system_msgs:
        all_messages.extend(system_msgs)
    all_messages.extend(messages)

    try:
        logger.info("Calling LLM API with tools")

        api_params = {"model": default_model, "messages": all_messages, "stream": False}

        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = tool_choice

        if temperature is not None:
            api_params["temperature"] = temperature

        # Add any additional kwargs
        api_params.update(kwargs)

        response = await async_client.chat.completions.create(**api_params)
        choice = response.choices[0]

        logger.info("Successfully obtained API response with tools")
        return choice.message

    except Exception as e:
        error_message = f"Error calling API with tools: {e}"
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
            response = await ask(example_messages, stream=False)
            print(f"Response: {response}")
        except Exception as e:
            print(f"Error: {e}")

    asyncio.run(test())
