import os
import dotenv
import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncGenerator, Generator
from openai import AsyncOpenAI, OpenAI
from logger import logger
from utils.mcp import call_mcp_tool

dotenv.load_dotenv()

api_key = os.getenv("LLM_API_KEY")
base_url = os.getenv("LLM_BASE_URL")
default_model = os.getenv("LLM_MODEL")

assert all([api_key, base_url, default_model]), "LLM API key, base URL, and model must be set"

async_client = AsyncOpenAI(
    api_key=api_key,
    base_url=base_url
)

sync_client = OpenAI(
    api_key=api_key,
    base_url=base_url
)


async def get_llm_response_async(messages: list, tools: Optional[List[Dict]] = None, stream: bool = False) -> Dict[str, Any]:
    if not api_key:
        logger.error("LLM API key not set. Please set LLM_API_KEY")
        return {
            "type": "error",
            "content": "Error: LLM API key not set. Set LLM_API_KEY."
        }

    try:
        logger.info("Starting to call LLM API (async)")
        
        api_params = {
            "model": default_model,
            "messages": messages,
            "stream": False
        }
        
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"
            
        response = await async_client.chat.completions.create(**api_params)

        full_response = ""
        tool_calls = []

        choice = response.choices[0]

        if hasattr(choice, 'message') and hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                tool_calls.append({
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                })
        elif hasattr(choice, 'message') and hasattr(choice.message, 'content'):
            full_response = choice.message.content or ""

        print()
        logger.info("Successfully obtained API response")

        if tool_calls:
            return {
                "type": "tool_calls",
                "tool_calls": tool_calls
            }

        return {
            "type": "text",
            "content": full_response
        }
    except Exception as e:
        error_message = f"Error calling API: {e}"
        logger.error(error_message)
        print(error_message)
        return {
            "type": "error",
            "content": error_message
        }


async def get_llm_response_async_streaming(messages: list, tools: Optional[List[Dict]] = None) -> AsyncGenerator[str, None]:
    if not api_key:
        logger.error("LLM API key not set. Please set LLM_API_KEY")
        yield "Error: LLM API key not set. Set LLM_API_KEY."
        return

    try:
        logger.info("Starting to call LLM API (async streaming)")
        
        api_params = {
            "model": default_model,
            "messages": messages,
            "stream": True
        }
        
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"
            
        response = await async_client.chat.completions.create(**api_params)

        async for chunk in response:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
                
        logger.info("Successfully obtained streaming API response")
    except Exception as e:
        error_message = f"Error calling API: {e}"
        logger.error(error_message)
        yield error_message


def get_llm_response_sync(messages: list, tools: Optional[List[Dict]] = None, stream: bool = False) -> Dict[str, Any]:
    if not api_key:
        logger.error("LLM API key not set. Please set LLM_API_KEY")
        return {
            "type": "error",
            "content": "Error: LLM API key not set. Set LLM_API_KEY."
        }

    try:
        logger.info("Starting to call LLM API (sync)")
        
        api_params = {
            "model": default_model,
            "messages": messages,
            "stream": False
        }
        
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"
            
        response = sync_client.chat.completions.create(**api_params)

        full_response = ""
        tool_calls = []
        
        choice = response.choices[0]
        
        if hasattr(choice, 'message') and hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                tool_calls.append({
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                })
        elif hasattr(choice, 'message') and hasattr(choice.message, 'content'):
            full_response = choice.message.content or ""
                
        print()
        logger.info("Successfully obtained API response")
        
        if tool_calls:
            return {
                "type": "tool_calls",
                "tool_calls": tool_calls
            }
        
        return {
            "type": "text",
            "content": full_response
        }
    except Exception as e:
        error_message = f"Error calling API: {e}"
        logger.error(error_message)
        print(error_message)
        return {
            "type": "error",
            "content": error_message
        }


def get_llm_response_sync_streaming(messages: list, tools: Optional[List[Dict]] = None) -> Generator[str, None, None]:
    if not api_key:
        logger.error("LLM API key not set. Please set LLM_API_KEY")
        yield "Error: LLM API key not set. Set LLM_API_KEY."
        return

    try:
        logger.info("Starting to call LLM API (sync streaming)")
        
        api_params = {
            "model": default_model,
            "messages": messages,
            "stream": True
        }
        
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"
            
        response = sync_client.chat.completions.create(**api_params)

        for chunk in response:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
                
        logger.info("Successfully obtained streaming API response")
    except Exception as e:
        error_message = f"Error calling API: {e}"
        logger.error(error_message)
        yield error_message


if __name__ == '__main__':
    # This is an example showing how to run this module directly
    async def test():
        example_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, please introduce yourself."},
        ]
        response = await get_llm_response_async(example_messages)
        print(f"Response type: {response['type']}")
        if response['type'] == 'text':
            print(f"Response content: {response['content']}")
        elif response['type'] == 'tool_calls':
            print("Tool calls:")
            for tool_call in response['tool_calls']:
                print(f"  - {tool_call['function']['name']}")

    asyncio.run(test())