import json
import re
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel

from logger import logger
from schema import Message
from utils.llm import ask

# Only tested with vllm server


async def ask_choice(
    messages: List[Message],
    choices: list[str],
    system_msgs: List[Message] = None,
    temperature: Optional[float] = None,
    **kwargs,
) -> str:
    extra_body = {
        "guided_choice": choices,
    }

    extra_body.update(kwargs)

    response = await ask(
        messages,
        system_msgs,
        tool_choice="none",
        stream=False,
        temperature=temperature,
        extra_body=extra_body,
    )

    if response:
        result = response.strip()
        if result in choices:
            return result
        else:
            # try to find the closest choice
            logger.warning(
                f"Invalid choice: {result}, trying to find the closest choice"
            )
            for choice in choices:
                if choice in result or result in choice:
                    return choice
            raise ValueError(f"Invalid choice: {result}")
    raise ValueError("No response from LLM")


async def ask_regex(
    messages: List[Message],
    pattern: str,
    system_msgs: List[Message] = None,
    temperature: Optional[float] = None,
    stop: Optional[List[str]] = None,
    **kwargs,
) -> str:
    extra_body = {
        "guide_regex": pattern,
    }

    if stop:
        extra_body["stop"] = stop

    extra_body.update(kwargs)
    response = await ask(
        messages,
        system_msgs,
        tool_choice="none",
        stream=False,
        temperature=temperature,
        extra_body=extra_body,
    )

    if response:
        return response.strip()
    raise ValueError("No response from LLM")


async def ask_json(
    messages: List[Message],
    schema: Union[Type[BaseModel], dict[str, Any]],
    system_msgs: List[Message] = None,
    temperature: Optional[float] = None,
    **kwargs,
) -> str:
    try:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            json_schema = schema.model_json_schema()
        else:
            json_schema = schema

        extra_body = {
            "guided_json": json_schema,
        }

        # response_format = {
        #     "type": "json_object",
        #     "json_schema": {
        #         "name": "response",
        #         "schema": json_schema,
        #         "strict": True,
        #     },
        # }

        extra_body.update(kwargs)

        response = await ask(
            messages,
            system_msgs,
            tool_choice="none",
            stream=False,
            temperature=temperature,
            extra_body=extra_body,
            # response_format=response_format,
            **kwargs,
        )
        if response:
            result = response.strip()
            return result
        else:
            raise ValueError("No response from LLM")
    except Exception as e:
        logger.error(f"Error asking JSON: {e}")
        raise e


def _parse_json_safety_to_model(
    json_str: str,
    model_class: Type[BaseModel],
) -> Optional[BaseModel]:
    # 首先尝试直接解析
    try:
        return model_class.model_validate_json(json_str)
    except Exception as e:
        logger.warning(f"Error parsing JSON to model: {e}")

    # 清理JSON字符串
    def clean_json_string(s: str) -> str:
        # 移除前后的空白字符
        s = s.strip()

        # 移除可能的markdown代码块标记
        if s.startswith("```json"):
            s = s[7:]
        elif s.startswith("```"):
            s = s[3:]
        if s.endswith("```"):
            s = s[:-3]

        # 再次清理空白字符
        s = s.strip()

        # 如果字符串不是以 { 或 [ 开头，尝试提取JSON部分
        if not s.startswith(("{", "[")):
            # 查找第一个 { 或 [
            json_start = -1
            for i, char in enumerate(s):
                if char in ("{", "["):
                    json_start = i
                    break
            if json_start != -1:
                s = s[json_start:]

        return s

    # 尝试解析清理后的字符串
    cleaned_json = clean_json_string(json_str)
    try:
        return model_class.model_validate_json(cleaned_json)
    except Exception as e:
        logger.warning(f"Error parsing cleaned JSON: {e}")

    # 尝试提取和修复JSON字符串
    def extract_and_fix_json(s: str) -> str:
        # 使用正则表达式提取JSON对象
        json_pattern = r"\{.*\}"
        match = re.search(json_pattern, s, re.DOTALL)
        if match:
            json_candidate = match.group(0)

            # 尝试修复常见的JSON问题
            # 1. 修复单引号为双引号
            json_candidate = re.sub(r"'([^']*)':", r'"\1":', json_candidate)
            json_candidate = re.sub(r":\s*'([^']*)'", r': "\1"', json_candidate)

            # 2. 修复未引用的键
            json_candidate = re.sub(r"(\w+):", r'"\1":', json_candidate)

            # 3. 移除多余的逗号
            json_candidate = re.sub(r",\s*}", "}", json_candidate)
            json_candidate = re.sub(r",\s*]", "]", json_candidate)

            return json_candidate

        # 如果没有找到对象，尝试数组
        array_pattern = r"\[.*\]"
        match = re.search(array_pattern, s, re.DOTALL)
        if match:
            return match.group(0)

        return s

    # 尝试解析修复后的JSON字符串
    try:
        fixed_json = extract_and_fix_json(cleaned_json)
        return model_class.model_validate_json(fixed_json)
    except Exception as e:
        logger.warning(f"Error parsing fixed JSON: {e}")

    # 最后尝试：使用标准json库解析然后转换为模型
    try:
        fixed_json = extract_and_fix_json(cleaned_json)
        parsed_data = json.loads(fixed_json)
        return model_class.model_validate(parsed_data)
    except Exception as e:
        logger.error(f"All JSON parsing attempts failed: {e}")

    # 如果最终解析失败，返回None
    return None


async def ask_json_parsed(
    messages: List[Message],
    schema: Optional[Dict[str, Any]] = None,
    system_msgs: List[Message] = None,
    temperature: Optional[float] = None,
    max_retries: int = 2,
    **kwargs,
) -> dict[str, Any]:
    retries = 0
    last_error = None

    while retries < max_retries:
        try:
            json_str = await ask_json(
                messages,
                schema=schema,
                system_msgs=system_msgs,
                temperature=temperature,
                **kwargs,
            )
            return json.loads(json_str)
        except Exception as e:
            last_error = e

            if retries < max_retries:
                retries += 1
                logger.warning(f"Attempt {retries}/{max_retries} failed: {e}")
            else:
                logger.error(
                    f"Failed to parse model after {max_retries} attempts. Last error: {last_error}"
                )
                raise last_error


async def ask_model_parsed(
    messages: List[Message],
    model_class: Type[BaseModel],
    system_msgs: List[Message] = None,
    temperature: Optional[float] = None,
    max_retries: int = 2,
    **kwargs,
) -> Optional[BaseModel]:
    """
    Ask LLM for JSON response and parse it into a Pydantic model with retries.

    Args:
        messages: Conversation messages
        model_class: Pydantic model class to parse into
        system_msgs: System messages
        temperature: LLM temperature
        max_retries: Maximum number of retry attempts
        **kwargs: Additional arguments to pass to ask()

    Returns:
        Parsed Pydantic model instance or None if parsing fails
    """
    retries = 0
    last_error = None

    while retries < max_retries:
        try:
            # First try to get structured JSON using ask_json
            json_response = await ask_json(
                messages, model_class, system_msgs, temperature, **kwargs
            )

            # Try to parse the JSON response into the model
            parsed_model = _parse_json_safety_to_model(json_response, model_class)
            if parsed_model is not None:
                return parsed_model
            else:
                raise ValueError("Failed to parse JSON response into model")

        except Exception as e:
            last_error = e

            if retries < max_retries:
                retries += 1
                logger.warning(f"Attempt {retries}/{max_retries} failed: {e}")

            else:
                logger.error(
                    f"Failed to parse model after {max_retries} attempts. Last error: {last_error}"
                )
                raise last_error
