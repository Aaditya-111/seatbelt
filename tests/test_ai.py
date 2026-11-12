import asyncio
import json

import httpx
import pytest

from seatbelt.service.ai import (
    AIOutputError,
    AIUnavailableError,
    OllamaPaymentInterpreter,
)


def test_interpreter_returns_valid_payment_proposal():
    expected = {
        "status": "ready",
        "payee": "shop-a",
        "amount": "25.00",
        "currency": "USD",
        "description": "conference tickets",
        "quantity": 2,
        "missing_fields": [],
        "clarification_question": None,
    }

    async def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "qwen2.5:3b"
        assert payload["stream"] is False
        assert payload["options"]["temperature"] == 0
        assert payload["format"]["type"] == "object"
        assert set(payload["format"]["required"]) == {
            "status",
            "payee",
            "amount",
            "currency",
            "description",
            "quantity",
            "missing_fields",
            "clarification_question",
        }
        assert payload["format"]["additionalProperties"] is False
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(expected)}},
        )

    interpreter = OllamaPaymentInterpreter(
        transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(
        interpreter.interpret("Buy two tickets from shop-a for 25 USD")
    )

    assert result.status == "ready"
    assert result.payee == "shop-a"
    assert result.amount == "25.00"
    assert result.quantity == 2


def test_interpreter_supports_clarification():
    expected = {
        "status": "needs_clarification",
        "payee": "shop-a",
        "amount": None,
        "currency": None,
        "description": "conference tickets",
        "quantity": 2,
        "missing_fields": ["amount", "currency"],
        "clarification_question": "What is the total price and currency?",
    }

    async def handler(request):
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(expected)}},
        )

    interpreter = OllamaPaymentInterpreter(
        transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(interpreter.interpret("Buy two tickets from shop-a"))

    assert result.status == "needs_clarification"
    assert result.missing_fields == ["amount", "currency"]
    assert result.clarification_question


def test_interpreter_rejects_invalid_model_output():
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "status": "ready",
                            "payee": "Customer",
                            "amount": "25.00",
                            "currency": "USD",
                            "description": "purchase",
                            "quantity": 1,
                            "missing_fields": [],
                            "clarification_question": None,
                            "execute_payment": True,
                        }
                    )
                }
            },
        )

    interpreter = OllamaPaymentInterpreter(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(AIOutputError):
        asyncio.run(interpreter.interpret("Buy something"))


def test_interpreter_rejects_invalid_ready_proposal():
    invalid = {
        "status": "ready",
        "payee": None,
        "amount": "25.00",
        "currency": "USD",
        "description": "purchase",
        "quantity": 1,
        "missing_fields": [],
        "clarification_question": None,
    }

    async def handler(request):
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(invalid)}},
        )

    interpreter = OllamaPaymentInterpreter(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(AIOutputError):
        asyncio.run(interpreter.interpret("Buy something"))


def test_interpreter_maps_ollama_connection_failure():
    async def handler(request):
        raise httpx.ConnectError("private connection detail")

    interpreter = OllamaPaymentInterpreter(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(AIUnavailableError):
        asyncio.run(interpreter.interpret("Buy tickets for 25 USD"))


@pytest.mark.parametrize("purchase_text", ["", "   "])
def test_interpreter_rejects_empty_request(purchase_text):
    interpreter = OllamaPaymentInterpreter()

    with pytest.raises(ValueError):
        asyncio.run(interpreter.interpret(purchase_text))





def test_interpreter_normalizes_numeric_amount():
    expected = {
        "status": "ready",
        "payee": "shop-a",
        "amount": 25.0,
        "currency": "USD",
        "description": "purchase",
        "quantity": 1,
        "missing_fields": [],
        "clarification_question": None,
    }

    async def handler(request):
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(expected)}},
        )

    interpreter = OllamaPaymentInterpreter(
        transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(interpreter.interpret("Buy an item for 25 USD"))

    assert result.status == "ready"
    assert result.amount == "25.0"


def test_interpreter_turns_placeholder_amount_into_clarification():
    expected = {
        "status": "ready",
        "payee": "shop-a",
        "amount": "Some amount",
        "currency": "USD",
        "description": "purchase",
        "quantity": 1,
        "missing_fields": [],
        "clarification_question": None,
    }

    async def handler(request):
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(expected)}},
        )

    interpreter = OllamaPaymentInterpreter(
        transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(interpreter.interpret("Buy an item from shop-a"))

    assert result.status == "needs_clarification"
    assert result.amount is None
    assert "amount" in result.missing_fields
    assert "amount" in result.clarification_question.lower()


def test_interpreter_rejects_non_object_json():
    async def handler(request):
        return httpx.Response(
            200,
            json={"message": {"content": "[]"}},
        )

    interpreter = OllamaPaymentInterpreter(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(AIOutputError):
        asyncio.run(interpreter.interpret("Buy an item"))
