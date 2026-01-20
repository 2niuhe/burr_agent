"""
Functional tests for LLM Structured Output

These tests use real LLM API calls (no mocks).

Usage:
  # Test compatibility mode (default)
  PYTHONPATH=. python tests/test_llm_structure_compatibility.py

  # Test strict mode (vLLM)
  LLM_STRUCT_MODE=strict PYTHONPATH=. python tests/test_llm_structure_compatibility.py
"""

import os
import pytest
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from schema import Message, Role

# Dynamic import based on environment variable
USE_STRICT_MODE = os.getenv("LLM_STRUCT_MODE", "compatibility") == "strict"

if USE_STRICT_MODE:
    print("Using STRICT mode (llm_structure)")
    from utils.llm_structure import ask_json, ask_choice, ask_model_parsed, ask_json_parsed
else:
    print("Using COMPATIBILITY mode (llm_structure_compatibility)")
    from utils.llm_structure_compatibility import ask_json, ask_choice, ask_model_parsed, ask_json_parsed



# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------
class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class SentimentResult(BaseModel):
    sentiment: Sentiment
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class Person(BaseModel):
    name: str
    age: int
    hobbies: List[str]


class BookReview(BaseModel):
    title: str
    author: str
    rating: int = Field(ge=1, le=5)
    summary: str
    recommended: bool


# Complex nested models for deep nesting test
class Address(BaseModel):
    street: str
    city: str
    country: str
    postal_code: str


class WorkExperience(BaseModel):
    company_name: str
    position: str
    years: int


class Employee(BaseModel):
    name: str
    age: int
    department: str
    address: Address
    experience: List[WorkExperience]
    skills: List[str]


class Company(BaseModel):
    name: str
    industry: str
    founded_year: int
    headquarters: Address
    employees: List[Employee]


# ---------------------------------------------------------------------------
# Tests: ask_json
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ask_json_returns_valid_json():
    """Test that ask_json returns valid JSON matching schema."""
    messages = [
        Message(role=Role.USER, content="Analyze the sentiment of: 'I love this product!'")
    ]
    
    result = await ask_json(messages, SentimentResult)
    
    # Should be valid JSON
    parsed = SentimentResult.model_validate_json(result)
    assert parsed.sentiment == Sentiment.POSITIVE
    assert 0.0 <= parsed.confidence <= 1.0
    assert len(parsed.reasoning) > 0


@pytest.mark.asyncio
async def test_ask_json_with_negative_sentiment():
    """Test sentiment analysis with negative text."""
    messages = [
        Message(role=Role.USER, content="Analyze the sentiment of: 'This is terrible, I hate it.'")
    ]
    
    result = await ask_json(messages, SentimentResult)
    parsed = SentimentResult.model_validate_json(result)
    
    assert parsed.sentiment == Sentiment.NEGATIVE


@pytest.mark.asyncio
async def test_ask_json_with_complex_model():
    """Test ask_json with a more complex nested model."""
    messages = [
        Message(role=Role.USER, content="Create a person profile for: John, 30 years old, likes reading and hiking")
    ]
    
    result = await ask_json(messages, Person)
    parsed = Person.model_validate_json(result)
    
    assert "john" in parsed.name.lower()
    assert parsed.age == 30
    assert len(parsed.hobbies) >= 2


@pytest.mark.asyncio
async def test_ask_model_parsed_with_deeply_nested_model():
    """Test ask_model_parsed with deeply nested model (Company -> Employee -> Address/WorkExperience)."""
    messages = [
        Message(
            role=Role.USER,
            content="""Create a tech company with the following details:
- Company: TechCorp, in the Software industry, founded in 2015
- Headquarters: 123 Main St, San Francisco, USA, 94102
- One employee: Alice, 28, Engineering department
  - Address: 456 Oak Ave, San Jose, USA, 95101
  - Experience: 3 years at StartupX as Developer, 2 years at BigTech as Senior Developer
  - Skills: Python, Go, Kubernetes"""
        )
    ]
    
    result = await ask_model_parsed(messages, Company)
    
    # Verify top-level company info
    assert result is not None
    assert "techcorp" in result.name.lower()
    assert result.industry.lower() in ["software", "technology", "tech"]
    assert result.founded_year == 2015
    
    # Verify headquarters (nested Address)
    assert result.headquarters is not None
    assert "san francisco" in result.headquarters.city.lower()
    assert result.headquarters.country.lower() in ["usa", "united states"]
    
    # Verify employees list
    assert len(result.employees) >= 1
    employee = result.employees[0]
    assert "alice" in employee.name.lower()
    assert employee.age == 28
    
    # Verify employee's nested address
    assert employee.address is not None
    assert "san jose" in employee.address.city.lower()
    
    # Verify employee's work experience (list of nested objects)
    assert len(employee.experience) >= 2
    
    # Verify skills list
    assert len(employee.skills) >= 3



# ---------------------------------------------------------------------------
# Tests: ask_choice
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ask_choice_returns_valid_option():
    """Test that ask_choice returns one of the valid options."""
    messages = [
        Message(role=Role.USER, content="Is 'Python' a programming language or a snake?")
    ]
    choices = ["programming language", "snake", "both"]
    
    result = await ask_choice(messages, choices)
    
    assert result in choices


@pytest.mark.asyncio
async def test_ask_choice_with_yes_no():
    """Test ask_choice with simple yes/no options."""
    messages = [
        Message(role=Role.USER, content="Is the sky blue on a clear day?")
    ]
    choices = ["yes", "no"]
    
    result = await ask_choice(messages, choices)
    
    assert result in choices
    assert result == "yes"


@pytest.mark.asyncio
async def test_ask_choice_with_multiple_options():
    """Test ask_choice with more options."""
    messages = [
        Message(role=Role.USER, content="What is the primary color in a red apple?")
    ]
    choices = ["red", "green", "yellow", "blue"]
    
    result = await ask_choice(messages, choices)
    
    assert result in choices
    assert result == "red"


# ---------------------------------------------------------------------------
# Tests: ask_model_parsed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ask_model_parsed_returns_pydantic_model():
    """Test that ask_model_parsed returns a Pydantic model instance."""
    messages = [
        Message(role=Role.USER, content="Analyze: 'This is okay, nothing special.'")
    ]
    
    result = await ask_model_parsed(messages, SentimentResult)
    
    assert result is not None
    assert isinstance(result, SentimentResult)
    assert isinstance(result.sentiment, Sentiment)


@pytest.mark.asyncio
async def test_ask_model_parsed_with_book_review():
    """Test ask_model_parsed with a book review model."""
    messages = [
        Message(
            role=Role.USER,
            content="Write a review for '1984' by George Orwell. Give it 5 stars and recommend it."
        )
    ]
    
    result = await ask_model_parsed(messages, BookReview)
    
    assert result is not None
    assert "1984" in result.title
    assert "orwell" in result.author.lower()
    assert result.rating == 5
    assert result.recommended is True


# ---------------------------------------------------------------------------
# Tests: ask_json_parsed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ask_json_parsed_returns_dict():
    """Test that ask_json_parsed returns a dictionary."""
    messages = [
        Message(role=Role.USER, content="Create a simple person: name=Alice, age=25")
    ]
    
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"}
        },
        "required": ["name", "age"]
    }
    
    result = await ask_json_parsed(messages, schema=schema)
    
    assert isinstance(result, dict)
    assert "name" in result
    assert "age" in result
    assert result["name"].lower() == "alice"
    assert result["age"] == 25


# ---------------------------------------------------------------------------
# Run tests directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio
    
    async def run_all():
        print("=" * 60)
        print("Running functional tests...")
        print("=" * 60)
        
        tests = [
            ("ask_json - positive sentiment", test_ask_json_returns_valid_json),
            ("ask_json - negative sentiment", test_ask_json_with_negative_sentiment),
            ("ask_json - complex model", test_ask_json_with_complex_model),
            ("ask_model_parsed - deeply nested", test_ask_model_parsed_with_deeply_nested_model),
            ("ask_choice - valid option", test_ask_choice_returns_valid_option),
            ("ask_choice - yes/no", test_ask_choice_with_yes_no),
            ("ask_choice - multiple options", test_ask_choice_with_multiple_options),
            ("ask_model_parsed - pydantic model", test_ask_model_parsed_returns_pydantic_model),
            ("ask_model_parsed - book review", test_ask_model_parsed_with_book_review),
            ("ask_json_parsed - dict", test_ask_json_parsed_returns_dict),
        ]

        
        passed = 0
        failed = 0
        
        for name, test_fn in tests:
            try:
                await test_fn()
                print(f"✅ {name}")
                passed += 1
            except Exception as e:
                print(f"❌ {name}: {e}")
                failed += 1
        
        print("\n" + "=" * 60)
        print(f"Results: {passed} passed, {failed} failed")
        print("=" * 60)
    
    asyncio.run(run_all())
