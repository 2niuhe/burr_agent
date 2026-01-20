"""
LLM Structured Output - Compatibility Mode

For LLMs like DeepSeek that don't support strict schema-constrained decoding.
Strategy: Prompt injection + json_object mode + Pydantic validation + retry.
"""

import json
import re
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel, ValidationError

from logger import logger
from schema import Message, Role
from utils.llm import ask


def _generate_schema_instruction(schema: Dict[str, Any]) -> str:
    """Generate a prompt instruction from a JSON schema."""
    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
    return f"""You must output valid JSON that strictly matches this schema:
```json
{schema_str}
```
Do not include any text outside of the JSON object."""


def _parse_json_safety_to_model(json_str: str, model_class: Type[BaseModel]) -> Optional[BaseModel]:
    """Attempt to parse JSON string into Pydantic model with fallback strategies."""
    # Try direct parse
    try:
        return model_class.model_validate_json(json_str)
    except Exception:
        pass

    # Clean markdown fences
    s = json_str.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    
    try:
        return model_class.model_validate_json(s)
    except Exception:
        pass

    # Extract JSON object/array
    match = re.search(r"\{.*\}", s, re.DOTALL)
    if not match:
        match = re.search(r"\[.*\]", s, re.DOTALL)
    if match:
        try:
            return model_class.model_validate_json(match.group(0))
        except Exception:
            pass

    return None


def _append_instruction(msg_list: List[Message], instruction: str) -> None:
    """Append instruction to last user message or add new one."""
    if msg_list and msg_list[-1].role == Role.USER:
        msg_list[-1] = Message(
            role=Role.USER,
            content=(msg_list[-1].content or "") + "\n\n" + instruction,
        )
    else:
        msg_list.append(Message(role=Role.USER, content=instruction))


async def ask_json(
    messages: List[Message],
    schema: Union[Type[BaseModel], Dict[str, Any]],
    system_msgs: Optional[List[Message]] = None,
    temperature: Optional[float] = None,
    max_retries: int = 3,
    **kwargs,
) -> str:
    """Ask LLM for JSON response matching the given schema."""
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        json_schema = schema.model_json_schema()
    else:
        json_schema = schema

    msg_list = list(messages)
    _append_instruction(msg_list, _generate_schema_instruction(json_schema))
    response_format = {"type": "json_object"}

    last_error, response = None, None
    for attempt in range(max_retries):
        try:
            response = await ask(
                msg_list, system_msgs, tool_choice="none", stream=False,
                temperature=temperature, response_format=response_format, **kwargs,
            )
            if response:
                json.loads(response.strip())
                return response.strip()
            raise ValueError("No response from LLM")

        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}/{max_retries}: Invalid JSON - {e}")
            msg_list.append(Message(role=Role.ASSISTANT, content=response or ""))
            msg_list.append(Message(role=Role.USER, content=f"Invalid JSON: {e}. Please fix."))

        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                msg_list.append(Message(role=Role.USER, content=f"Error: {e}. Please retry."))

    raise ValueError(f"Failed after {max_retries} attempts. Last error: {last_error}")


async def ask_choice(
    messages: List[Message],
    choices: List[str],
    system_msgs: Optional[List[Message]] = None,
    temperature: Optional[float] = None,
    max_retries: int = 3,
    **kwargs,
) -> str:
    """Ask LLM to choose from options using JSON Schema + enum."""
    choice_schema = {
        "type": "object",
        "properties": {"choice": {"type": "string", "enum": choices}},
        "required": ["choice"]
    }
    choices_str = ", ".join(f'"{c}"' for c in choices)
    instruction = f"Choose ONE from: {choices_str}\nOutput JSON: {json.dumps(choice_schema)}"

    msg_list = list(messages)
    _append_instruction(msg_list, instruction)
    response_format = {"type": "json_object"}

    last_error, response = None, None
    for attempt in range(max_retries):
        try:
            response = await ask(
                msg_list, system_msgs, tool_choice="none", stream=False,
                temperature=temperature, response_format=response_format, **kwargs,
            )
            if response:
                choice = json.loads(response.strip()).get("choice")
                if choice in choices:
                    return choice
                raise ValueError(f"Choice '{choice}' not in {choices}")
            raise ValueError("No response from LLM")

        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            msg_list.append(Message(role=Role.ASSISTANT, content=response or ""))
            msg_list.append(Message(role=Role.USER, content=f"Invalid. Use one of: {choices_str}"))

    raise ValueError(f"Failed after {max_retries} attempts. Last error: {last_error}")


async def ask_model_parsed(
    messages: List[Message],
    model_class: Type[BaseModel],
    system_msgs: Optional[List[Message]] = None,
    temperature: Optional[float] = None,
    max_retries: int = 3,
    **kwargs,
) -> Optional[BaseModel]:
    """Ask LLM for JSON and parse into Pydantic model."""
    msg_list = list(messages)
    _append_instruction(msg_list, _generate_schema_instruction(model_class.model_json_schema()))
    response_format = {"type": "json_object"}

    last_error, response = None, None
    for attempt in range(max_retries):
        try:
            response = await ask(
                msg_list, system_msgs, tool_choice="none", stream=False,
                temperature=temperature, response_format=response_format, **kwargs,
            )
            if not response:
                raise ValueError("No response from LLM")

            parsed = _parse_json_safety_to_model(response, model_class)
            if parsed:
                return parsed

            try:
                model_class.model_validate_json(response)
            except ValidationError as ve:
                msg_list.append(Message(role=Role.ASSISTANT, content=response))
                msg_list.append(Message(role=Role.USER, content=f"Validation error: {ve}. Fix it."))
                last_error = ve
                continue

            raise ValueError("Failed to parse response")

        except Exception as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                msg_list.append(Message(role=Role.USER, content=f"Error: {e}. Please retry."))

    logger.error(f"Failed after {max_retries} attempts. Last error: {last_error}")
    return None


async def ask_json_parsed(
    messages: List[Message],
    schema: Optional[Dict[str, Any]] = None,
    system_msgs: Optional[List[Message]] = None,
    temperature: Optional[float] = None,
    max_retries: int = 3,
    **kwargs,
) -> Dict[str, Any]:
    """Ask LLM for JSON and return as dict."""
    json_str = await ask_json(
        messages, schema=schema or {}, system_msgs=system_msgs,
        temperature=temperature, max_retries=max_retries, **kwargs,
    )
    return json.loads(json_str)
